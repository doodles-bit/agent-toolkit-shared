/**
 * slack-channel MCP 서버 — clone-able + 환경변수 기반.
 *
 * Compass 생태계의 architect/compass/dawn-dusk 등 여러 페르소나가 동일 코드베이스를
 * 공유하면서 환경변수로만 차이(채널 ID·리액션 이모지·터미널 트리거)를 분기하도록 설계.
 *
 * 동작
 * - Slack `conversations.history` 폴링 → 새 메시지를 메모리 큐에 적재.
 * - reply / get_pending_messages 도구 노출 (MCP).
 * - 메시지 수령 시 옵션으로 PowerShell 트리거(`//slack`) 발사 (Claude Code wt 탭 자가 알림).
 * - drainQueue 시 옵션 리액션(`SLACK_REACTION_EMOJI`, 기본 `triangular_ruler`) 발사.
 * - processedTs 영속화·15분 룩백·서버 락(server.lock) 그대로.
 *
 * 환경변수는 README.md 의 표 참조.
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  ListToolsRequestSchema,
  CallToolRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { WebClient } from "@slack/web-api";
import { appendFileSync, readFileSync, writeFileSync, unlinkSync, existsSync, mkdirSync, statSync } from "fs";
import { execFile, execSync } from "child_process";
import { join, dirname, basename } from "path";
import { fileURLToPath } from "url";
import { CodexClient } from "./codex-client.js";

// ── 세션 내 중복 방지 ──
const processedTs = new Set<string>();
interface ProcessedEntry {
  channel: string;
  ts: string;
  processedAt: number;
}
const processedEntries = new Map<string, ProcessedEntry>();

// ── 영속화 (processedTs) ──
const STATE_DIR = join(dirname(fileURLToPath(import.meta.url)), ".state");
const STATE_FILE = join(STATE_DIR, "processed-ts.json");
const STATE_TTL_MS = 24 * 60 * 60 * 1000;

function loadProcessedState() {
  try {
    if (!existsSync(STATE_FILE)) {
      log(`[state] ${STATE_FILE} 없음 — 신규 상태로 시작`);
      return;
    }
    const raw = readFileSync(STATE_FILE, "utf-8");
    const data = JSON.parse(raw);
    const entries: ProcessedEntry[] = Array.isArray(data?.processedTs) ? data.processedTs : [];
    const now = Date.now();
    let loaded = 0;
    let expired = 0;
    for (const e of entries) {
      if (!e?.ts) continue;
      if (typeof e.processedAt === "number" && now - e.processedAt > STATE_TTL_MS) {
        expired++;
        continue;
      }
      processedTs.add(e.ts);
      processedEntries.set(e.ts, e);
      loaded++;
    }
    log(`[state] loaded ${loaded} processed ts (expired ${expired} / total ${entries.length})`);
  } catch (err) {
    log(`[state] load failed: ${(err as Error).message}`);
  }
}

function saveProcessedState() {
  try {
    if (!existsSync(STATE_DIR)) mkdirSync(STATE_DIR, { recursive: true });
    const now = Date.now();
    for (const ts of [...processedEntries.keys()]) {
      const e = processedEntries.get(ts)!;
      if (now - e.processedAt > STATE_TTL_MS) {
        processedEntries.delete(ts);
        processedTs.delete(ts);
      }
    }
    const data = {
      version: 1,
      savedAt: now,
      processedTs: [...processedEntries.values()],
    };
    writeFileSync(STATE_FILE, JSON.stringify(data, null, 2), "utf-8");
  } catch (err) {
    log(`[state] save failed: ${(err as Error).message}`);
  }
}

function markProcessed(channel: string, ts: string) {
  processedTs.add(ts);
  processedEntries.set(ts, { channel, ts, processedAt: Date.now() });
  saveProcessedState();
}

// ── 로깅 ──
const LOG_FILE = join(dirname(fileURLToPath(import.meta.url)), "server.log");
function log(...args: unknown[]) {
  const ts = new Date().toISOString();
  const msg = args.map(a => typeof a === "string" ? a : JSON.stringify(a, null, 0)).join(" ");
  const line = `[${ts}] ${msg}\n`;
  console.error(line.trimEnd());
  try { appendFileSync(LOG_FILE, line); } catch {}
}

// ── 단일 인스턴스 락 ──
// 기본은 server.ts 옆의 `server.lock`. 다중 에이전트(예: architect 인스턴스 + saebyeok-codex
// Codex spawn) 가 같은 패키지를 동시에 띄우는 경우 lock 충돌로 한쪽이 다른 쪽을 kill 하므로
// SLACK_CHANNEL_LOCK_FILE 환경변수로 인스턴스별 다른 경로를 지정해 격리할 수 있다.
const LOCK_FILE =
  (process.env.SLACK_CHANNEL_LOCK_FILE || "").trim() ||
  join(dirname(fileURLToPath(import.meta.url)), "server.lock");

function isProcessAlive(pid: number): boolean {
  try { process.kill(pid, 0); return true; } catch { return false; }
}

function killProcess(pid: number) {
  try {
    if (process.platform === "win32") {
      execSync(`taskkill /PID ${pid} /F /T`, { stdio: "ignore" });
    } else {
      process.kill(pid, "SIGTERM");
    }
    log(`[lock] Killed previous instance (PID ${pid})`);
  } catch (err) {
    log(`[lock] Failed to kill PID ${pid}:`, (err as Error).message);
  }
}

function acquireLock() {
  if (existsSync(LOCK_FILE)) {
    try {
      const prevPid = parseInt(readFileSync(LOCK_FILE, "utf-8").trim(), 10);
      if (!isNaN(prevPid) && isProcessAlive(prevPid)) {
        log(`[lock] Previous instance running (PID ${prevPid}) — killing`);
        killProcess(prevPid);
      } else {
        log(`[lock] Stale lock file found (PID ${prevPid}) — overwriting`);
      }
    } catch (err) {
      log(`[lock] Error reading lock file:`, (err as Error).message);
    }
  }
  writeFileSync(LOCK_FILE, String(process.pid), "utf-8");
  log(`[lock] Acquired lock (PID ${process.pid})`);
}

function releaseLock() {
  try {
    if (existsSync(LOCK_FILE)) {
      const content = readFileSync(LOCK_FILE, "utf-8").trim();
      if (content === String(process.pid)) {
        unlinkSync(LOCK_FILE);
        log(`[lock] Released lock (PID ${process.pid})`);
      }
    }
  } catch {}
}

process.on("SIGTERM", () => { try { codex?.stop(); } catch {} releaseLock(); process.exit(0); });
process.on("SIGINT", () => { try { codex?.stop(); } catch {} releaseLock(); process.exit(0); });
process.on("exit", () => { try { codex?.stop(); } catch {} releaseLock(); });

// ── 환경변수 (Windows User scope fallback) ──
function resolveEnv(name: string): string {
  if (process.env[name]) return process.env[name]!;
  if (process.platform === "win32") {
    try {
      const val = execSync(
        `powershell.exe -Command "[System.Environment]::GetEnvironmentVariable('${name}', 'User')"`,
        { encoding: "utf-8" }
      ).trim();
      if (val) { log(`[config] ${name} loaded from Windows User env`); return val; }
    } catch {}
  }
  return "";
}

const BOT_TOKEN = resolveEnv("SLACK_BOT_TOKEN");
if (!BOT_TOKEN) {
  console.error("[slack-channel] SLACK_BOT_TOKEN 환경변수가 비어 있습니다.");
  process.exit(1);
}

// 채널 — SLACK_ALLOWED_CHANNELS (콤마 구분) 우선, 없으면 SLACK_CHANNEL_ID 단일 fallback
const POLL_CHANNELS: string[] = (process.env.SLACK_ALLOWED_CHANNELS || "")
  .split(",").map(c => c.trim()).filter(Boolean);
if (POLL_CHANNELS.length === 0) {
  const single = (process.env.SLACK_CHANNEL_ID || "").trim();
  if (single) POLL_CHANNELS.push(single);
}
if (POLL_CHANNELS.length === 0) {
  console.error(
    "[slack-channel] SLACK_ALLOWED_CHANNELS 또는 SLACK_CHANNEL_ID 중 하나는 필수."
  );
  process.exit(1);
}

const ALLOWED_USERS = new Set(
  (process.env.SLACK_ALLOWED_USERS || "").split(",").map(u => u.trim()).filter(Boolean)
);
const POLL_INTERVAL_MS = Math.max(
  1000,
  Number(process.env.SLACK_POLL_INTERVAL_MS) || 3000
);

const REACTION_EMOJI = (process.env.SLACK_REACTION_EMOJI || "triangular_ruler").trim();
const SLACK_CHANNEL_LABEL = process.env.SLACK_CHANNEL_LABEL || "(unspecified)";

const AGENT_NAME = process.env.AGENT_NAME || "slack-channel";
const AGENT_VERSION = process.env.AGENT_VERSION || "1.0.0";

// ── 트리거 (옵션 — 비활성 가능) ──
const TRIGGER_SCRIPT_PATH = (process.env.TRIGGER_SCRIPT_PATH || "").trim();
const TRIGGER_WINDOW = (process.env.TRIGGER_WINDOW || "").trim();
const TRIGGER_KEY = (process.env.TRIGGER_KEY || "//slack").trim();
const TRIGGER_DEBOUNCE_MS = Math.max(
  500,
  Number(process.env.TRIGGER_DEBOUNCE_MS) || 3000
);
const TRIGGER_ENABLED =
  process.platform === "win32" && TRIGGER_SCRIPT_PATH && TRIGGER_WINDOW;

let lastTriggerTs = 0;

// ── Codex MCP client (옵션 — CODEX_ENABLED=true 일 때만 spawn) ──
const CODEX_ENABLED = (process.env.CODEX_ENABLED || "false").toLowerCase() === "true";
const CODEX_BIN = process.env.CODEX_BIN || "codex";
const CODEX_CWD = (process.env.CODEX_CWD || "").trim();
const CODEX_REQUEST_TIMEOUT_MS = Math.max(
  10_000,
  Number(process.env.CODEX_REQUEST_TIMEOUT_MS) || 60_000
);

let codex: CodexClient | null = null;

function triggerAgent() {
  if (!TRIGGER_ENABLED) return;
  const now = Date.now();
  if (now - lastTriggerTs < TRIGGER_DEBOUNCE_MS) return;
  lastTriggerTs = now;

  execFile(
    "powershell.exe",
    ["-File", TRIGGER_SCRIPT_PATH, "-WindowTitle", TRIGGER_WINDOW, "-Key", TRIGGER_KEY],
    { timeout: 5_000 },
    (err) => {
      if (err) log(`[trigger] Failed:`, (err as Error).message);
      else log(`[trigger] Sent ${TRIGGER_KEY} to ${TRIGGER_WINDOW}`);
    }
  );
}

// ── Instructions (옵션 — 환경변수·파일·기본값) ──
function loadInstructions(): string {
  const file = (process.env.AGENT_INSTRUCTIONS_FILE || "").trim();
  if (file) {
    try {
      if (existsSync(file)) return readFileSync(file, "utf-8").trim();
      log(`[config] AGENT_INSTRUCTIONS_FILE 지정됐으나 파일 없음: ${file}`);
    } catch (err) {
      log(`[config] AGENT_INSTRUCTIONS_FILE 읽기 실패: ${(err as Error).message}`);
    }
  }
  const direct = process.env.AGENT_INSTRUCTIONS;
  if (direct && direct.trim()) return direct.trim();
  return [
    `Slack ${SLACK_CHANNEL_LABEL} 채널의 메시지가 <channel> 태그로 도착합니다.`,
    "",
    "중요 규칙:",
    "- 사용자는 이 터미널을 볼 수 없습니다. 응답은 reply 도구로만 전달.",
    "- Slack 메시지를 받으면 반드시 reply 도구로 응답. 예외 없음.",
    "- chat_id 와 thread_ts 를 그대로 reply 에 전달.",
    "- 한국어로 응답.",
  ].join("\n");
}

// ── Slack Web API ──
const web = new WebClient(BOT_TOKEN);
let botUserId = "";

// ── 메시지 큐 ──
interface QueuedMessage {
  content: string;
  meta: Record<string, string>;
  timestamp: number;
}
const messageQueue: QueuedMessage[] = [];
const QUEUE_MAX = 50;

// ── 폴링 상태 ──
const lastSeenTs: Record<string, string> = {};
let pollErrors = 0;

// ── MCP Server ──
const mcp = new Server(
  { name: AGENT_NAME, version: AGENT_VERSION },
  {
    capabilities: {
      experimental: { "claude/channel": {} },
      tools: {},
    },
    instructions: loadInstructions(),
  }
);

mcp.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "reply",
      description: "Slack 채널에 메시지를 보냅니다. 반드시 chat_id 를 포함하세요.",
      inputSchema: {
        type: "object" as const,
        properties: {
          chat_id: { type: "string", description: "Slack 채널 또는 DM ID" },
          text: { type: "string", description: "보낼 메시지 텍스트" },
          thread_ts: { type: "string", description: "스레드 타임스탬프 (스레드 답장 시)" },
        },
        required: ["chat_id", "text"],
      },
    },
    {
      name: "get_pending_messages",
      description: "큐에 남아있는 미처리 메시지를 조회합니다. 조회 후 큐를 비웁니다.",
      inputSchema: { type: "object" as const, properties: {} },
    },
    {
      name: "upload_file",
      description:
        "파일을 Slack 채널에 첨부합니다. 절대 경로의 파일을 읽어 filesUploadV2 로 전송합니다. 이미지·문서·로그 등 모든 형식 지원.",
      inputSchema: {
        type: "object" as const,
        properties: {
          chat_id: { type: "string", description: "Slack 채널 또는 DM ID" },
          file_path: { type: "string", description: "업로드할 파일의 절대 경로" },
          comment: { type: "string", description: "동반 텍스트 (Slack initial_comment 로 매핑)" },
          thread_ts: { type: "string", description: "스레드에 첨부할 경우 부모 메시지 ts" },
        },
        required: ["chat_id", "file_path"],
      },
    },
  ],
}));

// 큐 드레인 시점에 읽음 리액션 발사. SLACK_REACTION_EMOJI 가 비어있으면 건너뜀.
async function addReadReaction(channel: string, ts: string) {
  if (!REACTION_EMOJI) return;
  try {
    await web.reactions.add({ channel, name: REACTION_EMOJI, timestamp: ts });
    log(`[reaction] ${REACTION_EMOJI} added ch=${channel} ts=${ts}`);
  } catch (err: any) {
    const code = err?.data?.error || err?.code || (err as Error).message;
    if (code === "already_reacted") {
      log(`[reaction] ${REACTION_EMOJI} already present ch=${channel} ts=${ts}`);
      return;
    }
    log(`[reaction] ${REACTION_EMOJI} failed ch=${channel} ts=${ts}: ${code}`);
  }
}

function drainQueue(): string {
  if (messageQueue.length === 0) return "";

  const messages = [...messageQueue];
  messageQueue.length = 0;

  for (const m of messages) {
    void addReadReaction(m.meta.chat_id, m.meta.ts);
  }

  const formatted = messages
    .map(
      (m) =>
        `<channel source="slack-channel" source="slack" chat_id="${m.meta.chat_id}" user="${m.meta.user}" ts="${m.meta.ts}"${m.meta.thread_ts ? ` thread_ts="${m.meta.thread_ts}"` : ""}>\n${m.content}\n</channel>`
    )
    .join("\n\n");
  return `\n\n📬 큐에서 ${messages.length}건 수신:\n\n${formatted}`;
}

mcp.setRequestHandler(CallToolRequestSchema, async (req) => {
  if (req.params.name === "reply") {
    const { chat_id, text, thread_ts } = req.params.arguments as {
      chat_id: string;
      text: string;
      thread_ts?: string;
    };
    await web.chat.postMessage({
      channel: chat_id,
      text,
      thread_ts,
      unfurl_links: false,
      unfurl_media: false,
    });
    const pending = drainQueue();
    return { content: [{ type: "text", text: `Sent to ${chat_id}${pending}` }] };
  }
  if (req.params.name === "get_pending_messages") {
    const status = `[polling: ${POLL_INTERVAL_MS / 1000}s, errors: ${pollErrors}, queue: ${messageQueue.length}]`;
    if (messageQueue.length === 0) {
      return { content: [{ type: "text", text: `큐에 미처리 메시지 없음. ${status}` }] };
    }
    const pending = drainQueue();
    return { content: [{ type: "text", text: `${pending}\n${status}` }] };
  }
  if (req.params.name === "upload_file") {
    const { chat_id, file_path, comment, thread_ts } = req.params.arguments as {
      chat_id: string;
      file_path: string;
      comment?: string;
      thread_ts?: string;
    };

    if (!chat_id || !file_path) {
      return {
        isError: true,
        content: [{ type: "text", text: "chat_id 와 file_path 둘 다 필수입니다." }],
      };
    }
    if (!existsSync(file_path)) {
      return {
        isError: true,
        content: [{ type: "text", text: `파일 없음: ${file_path}` }],
      };
    }
    let size: number;
    try {
      size = statSync(file_path).size;
    } catch (err) {
      return {
        isError: true,
        content: [{ type: "text", text: `파일 읽기 실패: ${(err as Error).message}` }],
      };
    }
    const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;
    if (size > MAX_UPLOAD_BYTES) {
      return {
        isError: true,
        content: [
          {
            type: "text",
            text: `파일 크기 초과 ${(size / 1024 / 1024).toFixed(1)}MB > 50MB (Slack 자체 한도와 별개의 클라이언트 sanity check)`,
          },
        ],
      };
    }

    // SDK 의 FilesUploadV2Arguments 가 channel/thread destination union 타입이라
    // thread_ts 분기에서 strict TS inference 가 까다로움. 옵션 객체를 동적으로 빌드.
    const opts: Record<string, unknown> = {
      channel_id: chat_id,
      file: file_path,
      filename: basename(file_path),
    };
    if (comment) opts.initial_comment = comment;
    if (thread_ts) opts.thread_ts = thread_ts;

    log(`[upload] ${file_path} (${(size / 1024).toFixed(1)} KB) → ${chat_id}${thread_ts ? ` thread=${thread_ts}` : ""}`);
    try {
      const result = await web.filesUploadV2(opts as unknown as Parameters<typeof web.filesUploadV2>[0]);
      const summary = formatUploadResult(result, chat_id);
      log(`[upload] OK ${summary}`);
      return { content: [{ type: "text", text: summary }] };
    } catch (err: any) {
      const reason = err?.data?.error || err?.code || (err as Error).message || "unknown";
      log(`[upload] 실패 ${file_path} → ${chat_id}: ${reason}`);
      return {
        isError: true,
        content: [{ type: "text", text: `Slack 업로드 실패: ${reason}` }],
      };
    }
  }
  throw new Error(`Unknown tool: ${req.params.name}`);
});

// filesUploadV2 응답에서 file_id / permalink 추출. V2 응답 구조가 SDK 버전마다 약간 다를 수
// 있어 (`files: [{ files: [{ id, permalink }] }]` vs `files: [{ id, permalink }]`) 두 경로
// 모두 시도하고 안 보이면 단순 success 메시지.
function formatUploadResult(result: unknown, chat_id: string): string {
  const r = result as { files?: any[] };
  const files = Array.isArray(r?.files) ? r.files : [];
  const flat: any[] = [];
  for (const entry of files) {
    if (Array.isArray(entry?.files)) flat.push(...entry.files);
    else flat.push(entry);
  }
  if (flat.length === 0) return `Uploaded to ${chat_id}`;
  const ids = flat.map((f) => f?.id).filter(Boolean);
  const permalinks = flat.map((f) => f?.permalink).filter(Boolean);
  const parts = [`Uploaded to ${chat_id}`];
  if (ids.length > 0) parts.push(`file_id=${ids.join(",")}`);
  if (permalinks.length > 0) parts.push(permalinks[0]);
  return parts.join(" — ");
}

// ── 텍스트 정리 ──
function cleanText(text: string): string {
  if (botUserId) {
    text = text.replace(new RegExp(`<@${botUserId}>\\s*`, "g"), "").trim();
  }
  return text;
}

// ── 세션 푸시 ──
const RETRY_MAX = 5;
const RETRY_DELAY_MS = 1000;

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

async function pushToSession(channel: string, msg: any) {
  const text = cleanText(msg.text || "");
  if (!text) return;

  if (processedTs.has(msg.ts)) {
    log(`[poll] Skipping already-processed message ts=${msg.ts} (from persistent state)`);
    return;
  }
  markProcessed(channel, msg.ts);

  const meta: Record<string, string> = {
    source: "slack",
    chat_id: channel,
    user: msg.user,
    ts: msg.ts,
  };
  if (msg.thread_ts) meta.thread_ts = msg.thread_ts;

  // Codex 모드 분기 — codex 자식 프로세스에 위임하고 응답을 Slack 채널 본문에 reply.
  // 큐·트리거·Claude Code MCP 노출은 사용 안 함 (호출자 자체가 자율 응답).
  if (CODEX_ENABLED && codex) {
    void addReadReaction(channel, msg.ts);
    try {
      const reply = await codex.ask(channel, text);
      log(`[poll] Codex reply (len=${reply.length}) → Slack ${channel}`);
      await web.chat.postMessage({
        channel,
        text: reply,
        unfurl_links: false,
        unfurl_media: false,
      });
    } catch (err) {
      log(`[poll] Codex 호출 실패: ${(err as Error).message}`);
      // 페르소나 텍스트는 호출 측 (AGENTS.md 등) 책임. 시스템 fallback 만 plain 으로.
      try {
        await web.chat.postMessage({
          channel,
          text: `(시스템 알림) 응답 생성에 실패했습니다. 잠시 후 다시 시도해 주세요.`,
          unfurl_links: false,
          unfurl_media: false,
        });
      } catch {}
    }
    return;
  }

  // 기본 동작 — Claude Code MCP 모드 (PR #5 동작 그대로)
  if (messageQueue.length >= QUEUE_MAX) messageQueue.shift();
  messageQueue.push({ content: text, meta, timestamp: Date.now() });
  log(`[poll] Queued message from ${msg.user} ts=${msg.ts} (queue: ${messageQueue.length})`);

  triggerAgent();

  for (let attempt = 1; attempt <= RETRY_MAX; attempt++) {
    try {
      await mcp.notification({
        method: "notifications/claude/channel",
        params: { content: text, meta },
      });
      log(`[poll] Pushed message from ${msg.user} ts=${msg.ts} (attempt ${attempt})`);
      return;
    } catch (err) {
      log(`[poll] Push failed (attempt ${attempt}/${RETRY_MAX}):`, err);
      if (attempt < RETRY_MAX) await sleep(RETRY_DELAY_MS * attempt);
    }
  }
  log(`[poll] Push failed after ${RETRY_MAX} attempts, staying in queue`);
}

// ── 폴링 ──
async function pollChannel(channel: string) {
  try {
    const oldest = lastSeenTs[channel];
    const result = await web.conversations.history({
      channel,
      oldest,
      limit: 20,
      inclusive: false,
    });

    if (!result.ok || !result.messages?.length) return;

    const messages = result.messages.reverse();

    for (const msg of messages) {
      if (msg.bot_id || msg.subtype) continue;
      if (ALLOWED_USERS.size > 0 && !ALLOWED_USERS.has(msg.user!)) continue;
      await pushToSession(channel, msg);
    }

    const latestTs = messages.at(-1)?.ts;
    if (latestTs) lastSeenTs[channel] = latestTs;

    if (pollErrors > 0) {
      log(`[poll] Recovered after ${pollErrors} errors`);
      pollErrors = 0;
    }
  } catch (err) {
    pollErrors++;
    log(`[poll] Error polling ${channel} (${pollErrors}):`, err);
  }
}

async function pollAll() {
  for (const channel of POLL_CHANNELS) {
    await pollChannel(channel);
  }
}

// ── 시작 ──
async function main() {
  acquireLock();
  loadProcessedState();

  // Codex 모드 — 자식 프로세스 spawn + initialize + tools/list 검증
  if (CODEX_ENABLED) {
    if (!CODEX_CWD) {
      console.error(
        "[slack-channel] CODEX_ENABLED=true 인데 CODEX_CWD 가 비어 있음. " +
        "saebyeok-codex 같은 cwd 절대경로 필요."
      );
      process.exit(1);
    }
    codex = new CodexClient({
      bin: CODEX_BIN,
      cwd: CODEX_CWD,
      requestTimeoutMs: CODEX_REQUEST_TIMEOUT_MS,
      log,
    });
    try {
      await codex.start();
      log(`[slack] Codex MCP server connected (agent mode, cwd=${CODEX_CWD})`);
    } catch (err) {
      log(`[slack] Codex 시작 실패: ${(err as Error).message}`);
      process.exit(1);
    }
  } else {
    log(`[slack] Claude Code MCP mode (CODEX_ENABLED=false)`);
  }

  try {
    const auth = await web.auth.test();
    botUserId = (auth.user_id as string) || "";
    log(`[slack] Bot user ID: ${botUserId}`);
  } catch (e) {
    log("[slack] Failed to get bot user ID:", e);
  }

  const LOOKBACK_SEC = 15 * 60;
  const lookbackTs = ((Date.now() / 1000) - LOOKBACK_SEC).toFixed(6);
  for (const channel of POLL_CHANNELS) {
    lastSeenTs[channel] = lookbackTs;
    log(`[poll] Channel ${channel} initialized — lastSeenTs=${lookbackTs} (15min lookback)`);
  }

  setInterval(pollAll, POLL_INTERVAL_MS);
  log(
    `[poll] Polling started (interval: ${POLL_INTERVAL_MS / 1000}s, channels: ${POLL_CHANNELS.join(",")}, ` +
    `reaction: ${REACTION_EMOJI || "(off)"}, trigger: ${TRIGGER_ENABLED ? `${TRIGGER_WINDOW}` : "(off)"}, ` +
    `codex: ${CODEX_ENABLED ? "on" : "off"})`
  );

  const transport = new StdioServerTransport();
  await mcp.connect(transport);
  log(`[slack] MCP channel server running — agent=${AGENT_NAME} v${AGENT_VERSION}`);
}

main().catch((e) => {
  log("[slack] Fatal:", e);
  process.exit(1);
});
