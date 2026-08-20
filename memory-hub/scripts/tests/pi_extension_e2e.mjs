// Behavior e2e for the rendered pi-memory-hub.ts extension (AFK-debounced capture).
// Driven by test_pi_extension_e2e.py, which renders the template with this repo's
// fake hook and runs:
//   node pi_extension_e2e.mjs <extension.ts> <transcript.jsonl> <hook-log.jsonl>
// Env: MEMORY_HOOK_PI_CAPTURE_DELAY_MS must be a short test delay (e.g. 300),
// MEMORY_HOOK_STATE_DIR must point at a scratch dir so pi-trace.jsonl stays local.
//
// 同步口径：fake hook 在 stdin end 时写 hook-log，扩展在子进程 close 后才写
// pi-trace；「等待捕获完成」必须等 trace 落盘（唯一权威信号），等 hook-log 会
// 抢跑在扩展释放 capturing 锁之前，导致后续 shutdown 被 reentrant 跳过。
import assert from "node:assert/strict";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { setTimeout as sleep } from "node:timers/promises";
import { pathToFileURL } from "node:url";

const [extensionPath, transcriptPath, hookLog] = process.argv.slice(2);
assert.ok(extensionPath && transcriptPath && hookLog, "usage: <extension.ts> <transcript> <hook-log>");

const delayMs = Number(process.env.MEMORY_HOOK_PI_CAPTURE_DELAY_MS);
assert.ok(delayMs > 0 && delayMs < 5000, "test expects a short capture delay, got %s", delayMs);

writeFileSync(transcriptPath, JSON.stringify({ type: "message", role: "user", text: "hello" }) + "\n");

const handlers = new Map();
const pi = {
	on(event, fn) {
		handlers.set(event, fn);
	},
	registerTool() {},
};

const ctx = {
	cwd: process.cwd(),
	sessionManager: {
		getSessionId: () => "sess-e2e",
		getSessionFile: () => transcriptPath,
	},
};

const traceFile = `${process.env.MEMORY_HOOK_STATE_DIR}/pi-trace.jsonl`;

function readJsonl(file) {
	if (!existsSync(file)) return [];
	return readFileSync(file, "utf8")
		.split("\n")
		.filter(Boolean)
		.map((line) => JSON.parse(line));
}

function hookCalls(kind) {
	return readJsonl(hookLog).filter((entry) => kind === undefined || entry.argv[0] === kind);
}

function traceEntries(kind) {
	return readJsonl(traceFile).filter((entry) => kind === undefined || entry.kind === kind);
}

function capturesWithTrigger(trigger) {
	return traceEntries("capture").filter((entry) => entry.trigger === trigger && !entry.skipped);
}

async function waitFor(predicate, what, timeoutMs = 5000) {
	const deadline = Date.now() + timeoutMs;
	while (Date.now() < deadline) {
		if (predicate()) return;
		await sleep(25);
	}
	assert.fail(`timed out waiting for ${what}`);
}

try {
	const mod = await import(pathToFileURL(resolve(extensionPath)).href);
	assert.equal(typeof mod.default, "function", "extension must export a default function");
	mod.default(pi);
	for (const event of ["session_start", "before_agent_start", "agent_end", "session_shutdown"]) {
		assert.ok(handlers.has(event), `extension must register ${event}`);
	}

	// 1. prompt → 不再自动 recall（v4 起按需检索由 memory_search 工具完成），也不 capture
	await handlers.get("session_start")({}, ctx);
	await handlers.get("before_agent_start")({ prompt: "hello", systemPrompt: "sys" }, ctx);
	assert.equal(hookCalls("recall").length, 0, "before_agent_start must not auto-recall");
	assert.equal(hookCalls("capture").length, 0);

	// 2. agent_end → capture is scheduled, NOT fired immediately
	await handlers.get("agent_end")({}, ctx);
	assert.equal(hookCalls("capture").length, 0, "agent_end must not capture synchronously");
	await sleep(delayMs / 2);
	assert.equal(hookCalls("capture").length, 0, "capture must wait for the AFK delay");
	assert.equal(traceEntries("capture_schedule").length, 1);

	// 3. after the idle delay → exactly one capture, triggered as agent_end_idle
	await waitFor(() => capturesWithTrigger("agent_end_idle").length === 1, "idle capture");
	assert.equal(hookCalls("capture").length, 1);
	assert.equal(capturesWithTrigger("agent_end_idle")[0].exit_code, 0);

	// 4. user returns from AFK (new prompt) before the delay elapses → pending capture canceled
	await handlers.get("agent_end")({}, ctx);
	await sleep(delayMs / 2);
	await handlers.get("before_agent_start")({ prompt: "more work", systemPrompt: "sys" }, ctx);
	assert.ok(
		traceEntries("capture_cancel").some((entry) => entry.reason === "prompt"),
		"before_agent_start must cancel the pending capture",
	);
	await sleep(delayMs * 2);
	assert.equal(hookCalls("capture").length, 1, "canceled capture must not fire");

	// 5. next agent_end re-arms the timer → capture fires after a fresh idle delay
	await handlers.get("agent_end")({}, ctx);
	await waitFor(() => capturesWithTrigger("agent_end_idle").length === 2, "re-armed idle capture");
	assert.equal(hookCalls("capture").length, 2);

	// 6. agent_end then shutdown before the delay → shutdown captures immediately, timer canceled
	await handlers.get("agent_end")({}, ctx);
	await handlers.get("session_shutdown")({}, ctx);
	assert.equal(hookCalls("capture").length, 3, "session_shutdown must capture without waiting");
	assert.ok(
		traceEntries("capture_cancel").some((entry) => entry.reason === "shutdown"),
		"shutdown must cancel the pending timer",
	);
	assert.equal(capturesWithTrigger("session_shutdown").length, 1, "shutdown capture must be traced");
	await sleep(delayMs * 2);
	assert.equal(hookCalls("capture").length, 3, "canceled shutdown timer must not fire later");

	console.log(
		JSON.stringify({
			ok: true,
			recalls: hookCalls("recall").length,
			captures: hookCalls("capture").length,
			schedules: traceEntries("capture_schedule").length,
			cancels: traceEntries("capture_cancel").length,
		}),
	);
} catch (error) {
	// 失败时 dump 现场，供 Python 侧的断言消息呈现
	console.error("--- hook-log ---");
	console.error(existsSync(hookLog) ? readFileSync(hookLog, "utf8") : "<missing>");
	console.error("--- pi-trace ---");
	console.error(existsSync(traceFile) ? readFileSync(traceFile, "utf8") : "<missing>");
	throw error;
}
