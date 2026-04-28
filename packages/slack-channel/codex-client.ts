/**
 * Codex MCP client — `codex mcp-server` 를 자식 프로세스로 spawn 하고 stdio JSON-RPC 로 통신.
 *
 * 옵션 D 검증용 (새벽이 GPT-5.5 마이그레이션):
 *   Slack 메시지 → slack-channel 서버가 codex.ask(channelId, prompt) 호출
 *   → 첫 메시지면 codex(prompt), 후속이면 codex-reply(conversation_id, prompt) 분기
 *   → 응답 텍스트를 Slack 채널에 reply
 *
 * 라이프사이클
 * - start(): spawn → initialize 요청·응답 → notifications/initialized → tools/list 검증
 * - codex / codex-reply 도구 미발견 시 fatal throw (server.ts main() 의 catch 가 process.exit(1))
 * - codex 자식 exit → process.exit(1) (재시작 로직 없음, 별 라운드)
 * - stop(): SIGTERM
 *
 * conversation_id 추출
 * - MCP `tools/call` 응답의 result 객체에서 여러 후보 경로 탐색 (응답 메타 형식이 *추정* — Codex
 *   실제 응답 구조 첫 라이브 검증에서 조정 필요. README 에 명시).
 */

import { spawn, ChildProcess } from "child_process";
import { createInterface, Interface as ReadlineInterface } from "readline";

interface JsonRpcRequest {
  jsonrpc: "2.0";
  id: number;
  method: string;
  params?: unknown;
}

interface JsonRpcResponse {
  jsonrpc: "2.0";
  id: number;
  result?: any;
  error?: { code: number; message: string; data?: unknown };
}

interface JsonRpcNotification {
  jsonrpc: "2.0";
  method: string;
  params?: unknown;
}

const REQUEST_TIMEOUT_MS_DEFAULT = 60_000;

export interface CodexClientOptions {
  bin: string;            // codex 실행 파일 (기본 "codex")
  cwd: string;            // mcp-server 의 cwd (필수, 절대경로)
  requestTimeoutMs?: number;
  log: (...args: unknown[]) => void;  // 부모 server.ts 의 log 헬퍼
}

export class CodexClient {
  private child: ChildProcess | null = null;
  private rl: ReadlineInterface | null = null;
  private nextId = 1;
  private pending = new Map<number, { resolve: (r: JsonRpcResponse) => void; timer: NodeJS.Timeout }>();
  private conversationMap = new Map<string, string>();
  private initialized = false;
  private toolNames: string[] = [];
  private requestTimeout: number;
  private logFn: (...args: unknown[]) => void;
  private opts: CodexClientOptions;

  constructor(opts: CodexClientOptions) {
    this.opts = opts;
    this.logFn = opts.log;
    this.requestTimeout = opts.requestTimeoutMs ?? REQUEST_TIMEOUT_MS_DEFAULT;
  }

  /** spawn + initialize + tools/list 검증. 실패 시 throw. */
  async start(): Promise<void> {
    this.logFn(`[codex] spawn ${this.opts.bin} mcp-server (cwd=${this.opts.cwd})`);
    this.child = spawn(this.opts.bin, ["mcp-server"], {
      cwd: this.opts.cwd,
      stdio: ["pipe", "pipe", "inherit"],
    });

    this.child.on("error", (err) => {
      this.logFn(`[codex] spawn error: ${(err as Error).message}`);
    });
    this.child.on("exit", (code, signal) => {
      this.logFn(`[codex] process exited code=${code} signal=${signal}`);
      // codex 가 죽으면 우선은 server fatal 종료. 재시작 로직은 별 라운드.
      if (this.initialized) {
        process.exit(1);
      }
    });

    if (!this.child.stdout || !this.child.stdin) {
      throw new Error("[codex] stdio pipe 가 없습니다 (spawn 실패 가능).");
    }

    this.rl = createInterface({ input: this.child.stdout });
    this.rl.on("line", (line) => this.handleLine(line));

    // 1) initialize
    const initResp = await this.request("initialize", {
      protocolVersion: "2024-11-05",
      capabilities: {},
      clientInfo: { name: "slack-channel-codex-client", version: "1.1.0" },
    });
    if (initResp.error) {
      throw new Error(`[codex] initialize 실패: ${initResp.error.message}`);
    }
    this.logFn(`[codex] initialize OK — server: ${JSON.stringify(initResp.result?.serverInfo ?? {})}`);

    // 2) initialized 알림
    this.notify("notifications/initialized", {});

    // 3) tools/list 검증
    const listResp = await this.request("tools/list", {});
    if (listResp.error) {
      throw new Error(`[codex] tools/list 실패: ${listResp.error.message}`);
    }
    const tools = (listResp.result?.tools ?? []) as Array<{ name: string }>;
    this.toolNames = tools.map((t) => t.name);

    const required = ["codex", "codex-reply"];
    const missing = required.filter((n) => !this.toolNames.includes(n));
    if (missing.length > 0) {
      throw new Error(
        `[codex] 필수 도구 누락: ${missing.join(", ")}. ` +
        `받은 도구: ${this.toolNames.join(", ") || "(없음)"}`
      );
    }

    this.initialized = true;
    this.logFn(`[codex] connected. tools=[${this.toolNames.join(", ")}]`);
  }

  /** Slack 메시지 처리 — 첫 메시지면 codex, 후속이면 codex-reply. 응답 텍스트 반환. */
  async ask(channelId: string, prompt: string): Promise<string> {
    if (!this.initialized) throw new Error("[codex] 아직 initialize 안 됨");

    const existing = this.conversationMap.get(channelId);
    let resp: JsonRpcResponse;

    if (existing) {
      this.logFn(`[codex] codex-reply (conv=${existing}) ch=${channelId} prompt-len=${prompt.length}`);
      resp = await this.request("tools/call", {
        name: "codex-reply",
        arguments: { conversation_id: existing, prompt },
      });
    } else {
      this.logFn(`[codex] codex (new conv) ch=${channelId} prompt-len=${prompt.length}`);
      resp = await this.request("tools/call", {
        name: "codex",
        arguments: { prompt },
      });
    }

    if (resp.error) {
      throw new Error(`[codex] tools/call 실패: ${resp.error.message}`);
    }

    const text = this.extractText(resp.result);
    if (!existing) {
      const newConv = this.extractConversationId(resp.result);
      if (newConv) {
        this.conversationMap.set(channelId, newConv);
        this.logFn(`[codex] conversation 시작 ch=${channelId} conv=${newConv}`);
      } else {
        this.logFn(
          `[codex] 응답에서 conversation_id 못 찾음 — 다음 메시지가 다시 새 대화로 처리될 수 있음. ` +
          `result keys: ${Object.keys(resp.result ?? {}).join(", ")}`
        );
      }
    }
    return text;
  }

  /** SIGTERM. 자식 codex 도 함께 정리. */
  stop(): void {
    if (this.child && !this.child.killed) {
      try {
        this.child.kill("SIGTERM");
        this.logFn(`[codex] sent SIGTERM`);
      } catch (err) {
        this.logFn(`[codex] kill 실패: ${(err as Error).message}`);
      }
    }
    if (this.rl) {
      try { this.rl.close(); } catch {}
    }
    // 보류 요청 모두 취소
    for (const { timer, resolve } of this.pending.values()) {
      clearTimeout(timer);
      resolve({
        jsonrpc: "2.0",
        id: -1,
        error: { code: -1, message: "codex client stopped" },
      });
    }
    this.pending.clear();
  }

  // ── 내부 ──

  private handleLine(line: string): void {
    const trimmed = line.trim();
    if (!trimmed) return;
    let msg: any;
    try {
      msg = JSON.parse(trimmed);
    } catch {
      this.logFn(`[codex] 비-JSON 출력: ${trimmed.slice(0, 200)}`);
      return;
    }
    if (typeof msg.id === "number" && this.pending.has(msg.id)) {
      const entry = this.pending.get(msg.id)!;
      this.pending.delete(msg.id);
      clearTimeout(entry.timer);
      entry.resolve(msg as JsonRpcResponse);
      return;
    }
    // notification 또는 미매칭 응답 — 로깅만
    if (msg.method) {
      this.logFn(`[codex] 알림 method=${msg.method}`);
    } else {
      this.logFn(`[codex] 매칭 안 된 메시지 id=${msg.id}`);
    }
  }

  private request(method: string, params: unknown): Promise<JsonRpcResponse> {
    return new Promise((resolve, reject) => {
      if (!this.child?.stdin) {
        reject(new Error("[codex] stdin 닫힘"));
        return;
      }
      const id = this.nextId++;
      const timer = setTimeout(() => {
        if (this.pending.has(id)) {
          this.pending.delete(id);
          reject(new Error(`[codex] ${method} (id=${id}) 타임아웃 (${this.requestTimeout}ms)`));
        }
      }, this.requestTimeout);
      this.pending.set(id, { resolve, timer });

      const req: JsonRpcRequest = { jsonrpc: "2.0", id, method, params };
      this.child.stdin.write(JSON.stringify(req) + "\n", (err) => {
        if (err) {
          clearTimeout(timer);
          this.pending.delete(id);
          reject(new Error(`[codex] write 실패: ${err.message}`));
        }
      });
    });
  }

  private notify(method: string, params: unknown): void {
    if (!this.child?.stdin) return;
    const note: JsonRpcNotification = { jsonrpc: "2.0", method, params };
    this.child.stdin.write(JSON.stringify(note) + "\n");
  }

  /**
   * MCP tools/call 응답의 content 배열에서 텍스트 추출.
   * 표준: { content: [{ type: "text", text: "..." }, ...] }
   */
  private extractText(result: any): string {
    const content = result?.content;
    if (Array.isArray(content)) {
      const texts = content
        .filter((c: any) => c?.type === "text" && typeof c.text === "string")
        .map((c: any) => c.text as string);
      if (texts.length > 0) return texts.join("\n");
    }
    return JSON.stringify(result ?? null);
  }

  /**
   * conversation_id 추출. *추정* — 실제 Codex 응답 구조는 라이브 검증 후 조정 필요.
   * 후보 경로 (가장 가능성 높은 순):
   *   result._meta.conversationId / conversation_id
   *   result.conversationId / conversation_id
   *   result.structuredContent.conversationId / conversation_id
   *   result.content[i].text 안 JSON 파싱 (마지막 fallback)
   */
  private extractConversationId(result: any): string | undefined {
    if (!result) return undefined;
    const candidates: unknown[] = [
      result?._meta?.conversationId,
      result?._meta?.conversation_id,
      result?.conversationId,
      result?.conversation_id,
      result?.structuredContent?.conversationId,
      result?.structuredContent?.conversation_id,
    ];
    for (const c of candidates) {
      if (typeof c === "string" && c.trim()) return c.trim();
    }
    // 최후 fallback — content text 가 JSON 형태면 안에서 탐색
    const content = result?.content;
    if (Array.isArray(content)) {
      for (const c of content) {
        if (c?.type === "text" && typeof c.text === "string") {
          try {
            const parsed = JSON.parse(c.text);
            const inner =
              parsed?.conversation_id ??
              parsed?.conversationId ??
              parsed?._meta?.conversation_id;
            if (typeof inner === "string" && inner.trim()) return inner.trim();
          } catch {}
        }
      }
    }
    return undefined;
  }
}
