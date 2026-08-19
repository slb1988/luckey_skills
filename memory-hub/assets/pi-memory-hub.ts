// Managed by memory-hub/scripts/install_hooks.py.
// EXTENSION_VERSION 由 install_hooks.py 解析并与已安装副本比对；修改本模板必须递增版本号，
// check 发现已安装版本不一致会报 outdated，需重新 install 发布。
import { appendFileSync, mkdirSync } from "node:fs";
import { spawn } from "node:child_process";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

const EXTENSION_VERSION = "2";
const memoryHook = __MEMORY_HOOK_JSON__;
const python = "/usr/bin/python3";
const maxOutputBytes = 1024 * 1024;

// 全链路留痕：每次与 Memory Hub 的交互（session_start / recall / search / capture）
// 追加一条 JSONL 到 ${MEMORY_HOOK_STATE_DIR:-~/.local/state/memory-hub-hook}/pi-trace.jsonl，
// 供离线分析检索与归档行为是否符合预期。写日志失败不影响主流程。
const traceFile = join(
	process.env.MEMORY_HOOK_STATE_DIR ?? join(homedir(), ".local", "state", "memory-hub-hook"),
	"pi-trace.jsonl",
);
const maxTraceField = 20000;

function clip(value: string): string {
	return value.length > maxTraceField
		? value.slice(0, maxTraceField) + `...[truncated ${value.length - maxTraceField} chars]`
		: value;
}

function trace(kind: string, data: Record<string, unknown>): void {
	try {
		mkdirSync(dirname(traceFile), { recursive: true });
		appendFileSync(
			traceFile,
			JSON.stringify({ ts: new Date().toISOString(), kind, ext_version: EXTENSION_VERSION, ...data }) + "\n",
			"utf8",
		);
	} catch {
		// 留痕失败不阻断 agent
	}
}

interface HubResult {
	code: number;
	stdout: string;
	durationMs: number;
}

function runHub(
	args: string[],
	payload: Record<string, unknown> | undefined,
	cwd: string,
	timeoutMs: number,
): Promise<HubResult> {
	return new Promise((resolve) => {
		const started = Date.now();
		const child = spawn(python, [memoryHook, ...args], {
			cwd,
			env: process.env,
			stdio: ["pipe", "pipe", "ignore"],
		});
		let stdout = "";
		let settled = false;
		const finish = (code: number) => {
			if (settled) return;
			settled = true;
			clearTimeout(timer);
			resolve({ code, stdout, durationMs: Date.now() - started });
		};
		const timer = setTimeout(() => {
			child.kill("SIGTERM");
			finish(124);
		}, timeoutMs);
		child.on("error", () => finish(127));
		child.on("close", (code) => finish(code ?? 1));
		child.stdout.on("data", (chunk: Buffer) => {
			if (stdout.length < maxOutputBytes) stdout += chunk.toString("utf8");
		});
		child.stdin.end(payload ? JSON.stringify(payload) : undefined);
	});
}

function recalledContext(stdout: string): string {
	try {
		const parsed = JSON.parse(stdout);
		const context = parsed?.hookSpecificOutput?.additionalContext;
		return typeof context === "string" ? context : "";
	} catch {
		return "";
	}
}

export default function memoryHubExtension(pi: ExtensionAPI) {
	pi.on("session_start", async (_event, ctx) => {
		trace("session_start", {
			session_id: ctx.sessionManager.getSessionId(),
			cwd: ctx.cwd,
		});
	});

	pi.on("before_agent_start", async (event, ctx) => {
		const sessionId = ctx.sessionManager.getSessionId();
		const result = await runHub(
			["recall", "--source", "pi"],
			{
				hook_event_name: "UserPromptSubmit",
				session_id: sessionId,
				transcript_path: ctx.sessionManager.getSessionFile(),
				cwd: ctx.cwd,
				prompt: event.prompt,
			},
			ctx.cwd,
			8000,
		);
		const context = recalledContext(result.stdout);
		trace("recall", {
			session_id: sessionId,
			cwd: ctx.cwd,
			prompt: clip(event.prompt ?? ""),
			exit_code: result.code,
			duration_ms: result.durationMs,
			injected: context.length > 0,
			context_chars: context.length,
			context: clip(context),
		});
		if (context) return { systemPrompt: `${event.systemPrompt}\n\n${context}` };
	});

	let capturing = false;

	async function captureSession(trigger: string, ctx: ExtensionContext) {
		const sessionId = ctx.sessionManager.getSessionId();
		const transcriptPath = ctx.sessionManager.getSessionFile();
		if (!transcriptPath) {
			trace("capture", { trigger, session_id: sessionId, cwd: ctx.cwd, skipped: "no_transcript" });
			return;
		}
		if (capturing) {
			// agent_end 与 session_shutdown 可能并发，重入互斥
			trace("capture", { trigger, session_id: sessionId, cwd: ctx.cwd, skipped: "reentrant" });
			return;
		}
		capturing = true;
		try {
			const result = await runHub(
				["capture", "--source", "pi"],
				{
					hook_event_name: "SessionEnd",
					session_id: sessionId,
					transcript_path: transcriptPath,
					cwd: ctx.cwd,
				},
				ctx.cwd,
				120000,
			);
			trace("capture", {
				trigger,
				session_id: sessionId,
				cwd: ctx.cwd,
				transcript_path: transcriptPath,
				exit_code: result.code,
				duration_ms: result.durationMs,
				stdout: clip(result.stdout.trim()),
			});
		} finally {
			capturing = false;
		}
	}

	pi.on("agent_end", async (_event, ctx) => {
		await captureSession("agent_end", ctx);
	});

	pi.on("session_shutdown", async (_event, ctx) => {
		await captureSession("session_shutdown", ctx);
	});

	pi.registerTool({
		name: "memory_search",
		label: "Memory Search",
		description: "Search durable memories captured from Claude Code, Codex, and Pi sessions.",
		parameters: Type.Object({
			query: Type.String({ description: "Semantic search query" }),
			limit: Type.Optional(Type.Number({ minimum: 1, maximum: 20 })),
		}),
		async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
			const limit = Math.max(1, Math.min(20, Math.trunc(params.limit ?? 10)));
			const result = await runHub(
				["search", params.query, "--limit", String(limit)],
				undefined,
				ctx.cwd,
				15000,
			);
			const text = result.code === 0 && result.stdout.trim()
				? result.stdout.trim()
				: "Memory Hub is unavailable or no matching memory was found.";
			trace("search", {
				session_id: ctx.sessionManager.getSessionId(),
				cwd: ctx.cwd,
				query: params.query,
				limit,
				exit_code: result.code,
				duration_ms: result.durationMs,
				result_chars: text.length,
				result: clip(text),
			});
			return {
				content: [{ type: "text", text }],
				details: { exitCode: result.code },
			};
		},
	});
}
