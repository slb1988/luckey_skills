// Managed by memory-hub/scripts/install_hooks.py.
import { spawn } from "node:child_process";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

const memoryHook = __MEMORY_HOOK_JSON__;
const python = "/usr/bin/python3";
const maxOutputBytes = 1024 * 1024;

interface HubResult {
	code: number;
	stdout: string;
}

function runHub(
	args: string[],
	payload: Record<string, unknown> | undefined,
	cwd: string,
	timeoutMs: number,
): Promise<HubResult> {
	return new Promise((resolve) => {
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
			resolve({ code, stdout });
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
	pi.on("before_agent_start", async (event, ctx) => {
		const result = await runHub(
			["recall", "--source", "pi"],
			{
				hook_event_name: "UserPromptSubmit",
				session_id: ctx.sessionManager.getSessionId(),
				transcript_path: ctx.sessionManager.getSessionFile(),
				cwd: ctx.cwd,
				prompt: event.prompt,
			},
			ctx.cwd,
			8000,
		);
		const context = recalledContext(result.stdout);
		if (context) return { systemPrompt: `${event.systemPrompt}\n\n${context}` };
	});

	let capturing = false;

	async function captureSession(ctx: ExtensionContext) {
		if (capturing) return; // agent_end 与 session_shutdown 可能并发，重入互斥
		const transcriptPath = ctx.sessionManager.getSessionFile();
		if (!transcriptPath) return;
		capturing = true;
		try {
			await runHub(
				["capture", "--source", "pi"],
				{
					hook_event_name: "SessionEnd",
					session_id: ctx.sessionManager.getSessionId(),
					transcript_path: transcriptPath,
					cwd: ctx.cwd,
				},
				ctx.cwd,
				120000,
			);
		} finally {
			capturing = false;
		}
	}

	pi.on("agent_end", async (_event, ctx) => {
		await captureSession(ctx);
	});

	pi.on("session_shutdown", async (_event, ctx) => {
		await captureSession(ctx);
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
			return {
				content: [{ type: "text", text }],
				details: { exitCode: result.code },
			};
		},
	});
}
