/**
 * image-canvas MCP 서버
 *
 * OpenAI gpt-image-2 기반 이미지 생성 도구를 stdio MCP 로 노출한다.
 * 단일 페르소나에 종속되지 않는 plain 패키지 — prompt 의 톤·페르소나는 호출 측 CLAUDE.md
 * 가 자연스럽게 얹는다.
 *
 * 환경변수
 *   OPENAI_API_KEY            (필수) — 부모 프로세스에서 상속
 *   IMAGE_CANVAS_OUTPUT_DIR   (필수) — 생성 PNG 가 저장될 절대경로
 *
 * 도구
 *   generate_image(prompt, size?, n?, reference_images?) → 저장된 파일들의 절대 경로 (줄단위)
 *
 *   reference_images 가 비어있거나 미지정이면 텍스트→이미지 (`openai.images.generate`).
 *   채워지면 image-to-image 모드로 분기 (`openai.images.edit`) — gpt-image-2 가 reference
 *   image 입력을 native 지원 (최대 16장, 마스크 불필요).
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  ListToolsRequestSchema,
  CallToolRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import {
  existsSync,
  mkdirSync,
  writeFileSync,
  createReadStream,
  statSync,
} from "fs";
import { resolve, basename, extname } from "path";
import { createHash } from "crypto";
import OpenAI, { toFile } from "openai";

// ── 환경 검증 ──

const OUTPUT_DIR = process.env.IMAGE_CANVAS_OUTPUT_DIR;
if (!OUTPUT_DIR) {
  console.error(
    "[image-canvas] IMAGE_CANVAS_OUTPUT_DIR 환경변수가 비어 있습니다."
  );
  process.exit(1);
}
if (!process.env.OPENAI_API_KEY) {
  console.error(
    "[image-canvas] OPENAI_API_KEY 환경변수가 비어 있습니다 (User scope 등록 필요)."
  );
  process.exit(1);
}
const OUTPUT_DIR_ABS = resolve(OUTPUT_DIR);
if (!existsSync(OUTPUT_DIR_ABS)) {
  mkdirSync(OUTPUT_DIR_ABS, { recursive: true });
}

// ── OpenAI 클라이언트 ──

const openai = new OpenAI(); // OPENAI_API_KEY 자동 사용

const MODEL = "gpt-image-2";
const DEFAULT_SIZE = "1024x1024";
// gpt-image-2 지원 size (정사각형·세로·가로·auto. 2K/4K 지원은 향후 별도 마이그레이션)
const SUPPORTED_SIZES = new Set([
  "1024x1024",
  "1024x1536",
  "1536x1024",
  "auto",
]);
const MAX_N = 10;

// ── reference_images 가드 ──
// gpt-image-2 가 image-to-image 입력으로 받는 첨부 이미지 정책:
//   - 최대 16장 (모델 한도)
//   - png / jpg / jpeg / webp 지원
//   - 50MB 상한 (sanity check; 실 한도는 OpenAI API 측 결정 — 그쪽에서 reject 시 isError 흡수)
const MAX_REF_IMAGES = 16;
const ALLOWED_REF_EXT = new Set([".png", ".jpg", ".jpeg", ".webp"]);
const MAX_REF_BYTES = 50 * 1024 * 1024;

interface RefOk {
  ok: true;
  abs: string;
  ext: string;
  size: number;
}
interface RefFail {
  ok: false;
  reason: string;
}

function validateReferenceImage(p: string): RefOk | RefFail {
  const abs = resolve(p); // 상대 경로는 server.ts cwd 기준
  if (!existsSync(abs)) return { ok: false, reason: `파일 없음: ${abs}` };
  const ext = extname(abs).toLowerCase();
  if (!ALLOWED_REF_EXT.has(ext)) {
    return {
      ok: false,
      reason: `지원하지 않는 확장자 ${ext || "(없음)"} (${[...ALLOWED_REF_EXT]
        .sort()
        .join(", ")} 만)`,
    };
  }
  let sz = 0;
  try {
    sz = statSync(abs).size;
  } catch (err) {
    return {
      ok: false,
      reason: `stat 실패: ${(err as Error).message}`,
    };
  }
  if (sz > MAX_REF_BYTES) {
    return {
      ok: false,
      reason: `파일 크기 초과 ${(sz / 1024 / 1024).toFixed(1)}MB > ${MAX_REF_BYTES / 1024 / 1024}MB`,
    };
  }
  return { ok: true, abs, ext, size: sz };
}

// ── 파일명 ──

function timestampStem(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}-` +
    `${pad(d.getUTCHours())}${pad(d.getUTCMinutes())}${pad(d.getUTCSeconds())}`
  );
}

function shortHash(seed: string): string {
  return createHash("sha1").update(seed).digest("hex").slice(0, 6);
}

function buildFilename(prompt: string, idx: number, total: number): string {
  const stem = timestampStem();
  const hash = shortHash(`${prompt}|${idx}|${Date.now()}|${Math.random()}`);
  const suffix = total > 1 ? `_${idx + 1}` : "";
  return `${stem}_${hash}${suffix}.png`;
}

// ── MCP 서버 ──

const mcp = new Server(
  { name: "image-canvas", version: "1.1.0" },
  {
    capabilities: { tools: {} },
    instructions: [
      "OpenAI gpt-image-2 로 PNG 이미지를 생성해 IMAGE_CANVAS_OUTPUT_DIR 에 저장한다.",
      "도구는 generate_image 한 개. 프롬프트는 호출 측이 자유롭게 작성한다.",
      "reference_images 가 채워지면 reference 기반 image-to-image 모드로 자동 분기.",
    ].join("\n"),
  }
);

mcp.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "generate_image",
      description:
        "프롬프트로 이미지를 생성해 출력 디렉토리에 PNG 로 저장하고 절대 경로를 반환합니다. reference_images 가 있으면 reference 기반 image-to-image 모드.",
      inputSchema: {
        type: "object" as const,
        properties: {
          prompt: {
            type: "string",
            description: "그릴 이미지에 대한 자연어 설명",
          },
          size: {
            type: "string",
            description:
              "이미지 크기. 1024x1024(기본) | 1024x1536 | 1536x1024 | auto",
          },
          n: {
            type: "number",
            description: "생성 매수. 1~10 (기본 1)",
          },
          reference_images: {
            type: "array",
            description:
              "참고 이미지 절대 경로 배열 (1~16장). 비어있거나 미지정이면 텍스트→이미지. 채워지면 reference 기반 image-to-image. 지원 확장자: png/jpg/jpeg/webp.",
            items: { type: "string" },
          },
        },
        required: ["prompt"],
      },
    },
  ],
}));

mcp.setRequestHandler(CallToolRequestSchema, async (req) => {
  if (req.params.name !== "generate_image") {
    return {
      isError: true,
      content: [
        { type: "text", text: `지원하지 않는 도구: ${req.params.name}` },
      ],
    };
  }

  const args = (req.params.arguments as Record<string, unknown>) || {};
  const prompt = (args.prompt as string | undefined)?.trim();
  if (!prompt) {
    return {
      isError: true,
      content: [{ type: "text", text: "prompt 가 비어 있습니다." }],
    };
  }

  const size = (args.size as string | undefined) || DEFAULT_SIZE;
  if (!SUPPORTED_SIZES.has(size)) {
    return {
      isError: true,
      content: [
        {
          type: "text",
          text: `지원하지 않는 size: ${size}. 사용 가능: ${[...SUPPORTED_SIZES].join(", ")}`,
        },
      ],
    };
  }

  let n = Number(args.n ?? 1);
  if (!Number.isFinite(n) || n < 1) n = 1;
  if (n > MAX_N) n = MAX_N;
  n = Math.floor(n);

  // reference_images 검증
  const rawRefs = args.reference_images;
  const refs: string[] = Array.isArray(rawRefs)
    ? rawRefs.filter((x): x is string => typeof x === "string")
    : [];
  if (refs.length > MAX_REF_IMAGES) {
    return {
      isError: true,
      content: [
        {
          type: "text",
          text: `reference_images ${refs.length} 장 — 최대 ${MAX_REF_IMAGES} 장까지 지원`,
        },
      ],
    };
  }
  const validated: RefOk[] = [];
  for (const r of refs) {
    const v = validateReferenceImage(r);
    if (!v.ok) {
      return {
        isError: true,
        content: [
          {
            type: "text",
            text: `reference_images 가드 실패 (${r}): ${v.reason}`,
          },
        ],
      };
    }
    validated.push(v);
  }

  const sizeTyped = size as
    | "1024x1024"
    | "1024x1536"
    | "1536x1024"
    | "auto";

  try {
    let response;
    if (validated.length === 0) {
      // 텍스트→이미지
      response = await openai.images.generate({
        model: MODEL,
        prompt,
        size: sizeTyped,
        n,
      });
    } else {
      // image-to-image
      const uploadables = await Promise.all(
        validated.map((v) =>
          toFile(createReadStream(v.abs), basename(v.abs))
        )
      );
      const imageField =
        uploadables.length === 1 ? uploadables[0] : uploadables;
      console.error(
        `[image-canvas] edit 분기: reference_images=${validated.length}장`
      );
      response = await openai.images.edit({
        model: MODEL,
        image: imageField,
        prompt,
        size: sizeTyped,
        n,
      });
    }

    const data = response.data ?? [];
    if (data.length === 0) {
      return {
        isError: true,
        content: [
          { type: "text", text: "OpenAI 응답에 이미지가 없습니다." },
        ],
      };
    }

    const savedPaths: string[] = [];
    for (let i = 0; i < data.length; i++) {
      const b64 = data[i].b64_json;
      if (!b64) {
        console.error(
          `[image-canvas] data[${i}] 에 b64_json 이 없습니다. 건너뜁니다.`
        );
        continue;
      }
      const filename = buildFilename(prompt, i, data.length);
      const absPath = resolve(OUTPUT_DIR_ABS, filename);
      writeFileSync(absPath, Buffer.from(b64, "base64"));
      savedPaths.push(absPath);
    }

    if (savedPaths.length === 0) {
      return {
        isError: true,
        content: [
          { type: "text", text: "저장된 이미지가 없습니다 (b64_json 누락)." },
        ],
      };
    }

    return {
      content: [{ type: "text", text: savedPaths.join("\n") }],
    };
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    console.error(`[image-canvas] 호출 실패:`, msg);
    return {
      isError: true,
      content: [{ type: "text", text: `이미지 처리 실패: ${msg}` }],
    };
  }
});

// ── 시작 ──

const transport = new StdioServerTransport();
await mcp.connect(transport);
console.error(
  `[image-canvas] MCP 서버 시작 — 출력 디렉토리: ${OUTPUT_DIR_ABS}`
);
