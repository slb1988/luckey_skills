// Behavior e2e for the rendered pi-memory-hub.ts extension.
// v5 语义：agent_end 立即 enqueue-only（capture --no-flush --json，write-ahead
// marker 先落盘），flush 走 AFK 防抖；session_shutdown 收敛在途 enqueue 后做
// 最终 capture（enqueue+flush）；session_start 有界 catch-up 遗留 marker。
// Driven by test_pi_extension_e2e.py:
//   node pi_extension_e2e.mjs <extension.ts> <transcript.jsonl> <hook-log.jsonl>
// Env: MEMORY_HOOK_PI_CAPTURE_DELAY_MS 短延时（如 300），MEMORY_HOOK_STATE_DIR
// 指向临时目录，HOOK_LOG 为 fake hook 记录文件；CATCHUP_MARKER=1 时启用
// catch-up 场景（预置一个合法 marker + 一个半截损坏 marker）。
//
// 同步口径：fake hook 在 stdin end 时写 hook-log，扩展在子进程 close 后才写
// pi-trace；agent_end handler 自身 await enqueue，handler 返回后两者都已落盘。
import assert from "node:assert/strict";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { setTimeout as sleep } from "node:timers/promises";
import { pathToFileURL } from "node:url";

const [extensionPath, transcriptPath, hookLog] = process.argv.slice(2);
assert.ok(extensionPath && transcriptPath && hookLog, "usage: <extension.ts> <transcript> <hook-log>");

const delayMs = Number(process.env.MEMORY_HOOK_PI_CAPTURE_DELAY_MS);
assert.ok(delayMs > 0 && delayMs < 5000, "test expects a short flush delay, got %s", delayMs);

const stateDir = process.env.MEMORY_HOOK_STATE_DIR;
assert.ok(stateDir, "MEMORY_HOOK_STATE_DIR required");
const pendingDir = join(stateDir, "pi-pending-enqueues");
const traceFile = join(stateDir, "pi-trace.jsonl");
const catchupMode = process.env.CATCHUP_MARKER === "1";
const busyOnce = process.env.FLUSH_BUSY_ONCE === "1";

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

	if (catchupMode) {
		// catch-up 场景：session_start 前预置遗留 marker——合法可补传、半截损坏、
		// transcript 已消失（应保留 marker）、extraction 子 session（应终态删除）
		mkdirSync(pendingDir, { recursive: true });
		writeFileSync(
			join(pendingDir, "sess-old.json"),
			JSON.stringify({
				sessionId: "sess-old",
				transcriptPath,
				cwd: process.cwd(),
				writtenAt: new Date().toISOString(),
			}) + "\n",
		);
		writeFileSync(join(pendingDir, "sess-corrupt.json"), "{半截");
		writeFileSync(
			join(pendingDir, "sess-missing.json"),
			JSON.stringify({
				sessionId: "sess-missing",
				transcriptPath: join(process.cwd(), "missing-transcript.jsonl"),
				cwd: process.cwd(),
				writtenAt: new Date().toISOString(),
			}) + "\n",
		);
		const extractTranscript = join(process.cwd(), "extract-transcript.jsonl");
		writeFileSync(
			extractTranscript,
			JSON.stringify({
				type: "user",
				message: { content: "You are the Skill extraction sub-agent. Analyze." },
			}) + "\n",
		);
		writeFileSync(
			join(pendingDir, "sess-extract.json"),
			JSON.stringify({
				sessionId: "sess-extract",
				transcriptPath: extractTranscript,
				cwd: process.cwd(),
				writtenAt: new Date().toISOString(),
			}) + "\n",
		);

		await handlers.get("session_start")({}, ctx);
		await waitFor(() => traceEntries("catchup_done").length === 1, "catchup done");

		// 遗留 session 被 enqueue-only 补传（old 成功、missing 早退、extract 终态跳过）
		const catchupCalls = hookCalls("capture").filter((entry) => entry.argv.includes("--no-flush"));
		assert.equal(catchupCalls.length, 3, "all three leftover markers must be attempted");
		// 确认 durable / 终态跳过的 marker 删除；transcript 缺失的 marker 必须保留
		// （可能是临时不可用，删了等于永久丢 session——评审 P1）
		assert.ok(!existsSync(join(pendingDir, "sess-old.json")), "confirmed marker must be deleted");
		assert.ok(!existsSync(join(pendingDir, "sess-extract.json")), "extraction marker must be deleted");
		assert.ok(existsSync(join(pendingDir, "sess-missing.json")), "missing-transcript marker must be retained");
		assert.ok(existsSync(join(pendingDir, "sess-corrupt.json.corrupt")), "corrupt marker must be quarantined");
		// 全部 settle 后恰好一次 flush
		await waitFor(() => traceEntries("flush_done").length === 1, "catchup flush");
		assert.equal(hookCalls("flush").length, 1, "catch-up must flush exactly once");
		const scan = traceEntries("catchup_scan")[0];
		assert.equal(scan.scanned, 3);
		assert.equal(scan.quarantined, 1);
		const done = traceEntries("catchup_done")[0];
		assert.equal(done.confirmed, 2);
		assert.equal(done.kept, 1);
		console.log(JSON.stringify({ ok: true, mode: "catchup", captures: hookCalls("capture").length, flushes: hookCalls("flush").length }));
	} else if (process.env.GENRACE === "1") {
		// marker 代际竞态（评审 P1）：遗留 marker 属于当前活体 session；catch-up 的
		// enqueue 还在途时 agent_end 已写入新一代 marker——catch-up 只能删自己读过的
		// 那一代（应跳过），活体自己的 enqueue 确认后才删除。
		mkdirSync(pendingDir, { recursive: true });
		writeFileSync(
			join(pendingDir, "sess-e2e.json"),
			JSON.stringify({
				sessionId: "sess-e2e",
				transcriptPath,
				cwd: process.cwd(),
				writtenAt: "2026-01-01T00:00:00.000Z",
			}) + "\n",
		);
		await handlers.get("session_start")({}, ctx);
		await sleep(50); // 让 catch-up 抢先进 enqueue（fake 延时 500ms）
		await handlers.get("agent_end")({}, ctx); // 写新一代 marker + 自己的 enqueue
		await waitFor(() => traceEntries("catchup_done").length === 1, "catchup done");
		assert.ok(
			traceEntries("marker_delete").some((entry) => entry.skipped === "newer_generation"),
			"catch-up must not delete the newer live marker generation",
		);
		assert.ok(
			!existsSync(join(pendingDir, "sess-e2e.json")),
			"live agent_end deletes its own confirmed marker",
		);
		assert.equal(hookCalls("capture").length, 2, "catch-up enqueue + live enqueue");
		console.log(JSON.stringify({ ok: true, mode: "genrace", captures: hookCalls("capture").length }));
	} else {
		// 主流程：回合级持久化 + 防抖 flush + shutdown 收敛
		await handlers.get("session_start")({}, ctx);
		await waitFor(() => traceEntries("catchup_scan").length === 1, "catchup scan");
		assert.equal(traceEntries("catchup_scan")[0].scanned, 0);
		assert.equal(hookCalls("capture").length, 0, "session_start must not capture without markers");
		// 无 marker 也冲刷一次 spool 积压（评审 P2）；busyOnce 模式下首轮 busy+重试
		await waitFor(
			() => traceEntries("flush_done").some((entry) => entry.outcome === "completed"),
			"startup flush",
			10000,
		);
		const startupFlushes = busyOnce ? 2 : 1;
		assert.equal(hookCalls("flush").length, startupFlushes, "session_start must drain the spool once");
		if (busyOnce) {
			assert.ok(
				traceEntries("flush_done").some((entry) => entry.outcome === "busy"),
				"busy outcome must be traced before the retry",
			);
		}
		const completedFlushes = () =>
			traceEntries("flush_done").filter((entry) => entry.outcome === "completed").length;

		// 首轮 prompt 阻塞一次 project bootstrap 并注入 system prompt；后续 prompt
		// 不重复检索。超时/失败时同样只尝试一次并 fail-open。
		const firstStart = await handlers.get("before_agent_start")(
			{ prompt: "start work", systemPrompt: "base-system" },
			ctx,
		);
		const bootstrapTimedOut = process.env.FAKE_SEARCH_DELAY_MS !== undefined;
		if (bootstrapTimedOut) {
			assert.equal(firstStart, undefined, "bootstrap timeout must continue without injection");
			assert.equal(traceEntries("project_bootstrap")[0].outcome, "timeout");
			assert.equal(hookCalls("search").length, 0, "timed-out child is killed before fake logs");
		} else {
			assert.match(firstStart.systemPrompt, /^base-system\n\n# Memory Hub/);
			assert.match(firstStart.systemPrompt, /严格测试驱动/);
			assert.equal(traceEntries("project_bootstrap")[0].outcome, "injected");
			assert.equal(hookCalls("search").length, 1, "first prompt must search project memory once");
			assert.match(
				hookCalls("search")[0].argv[1],
				new RegExp(process.cwd().split(/[\\/]/).at(-1)),
				"bootstrap query must include the cwd project hint",
			);
		}
		const secondStart = await handlers.get("before_agent_start")(
			{ prompt: "continue", systemPrompt: "base-system" },
			ctx,
		);
		assert.equal(secondStart, undefined);
		assert.equal(
			traceEntries("project_bootstrap").length,
			1,
			"later prompts must not repeat bootstrap search",
		);

		// agent_end → enqueue 立即触发并 await 完成（handler 返回即 durable）
		await handlers.get("agent_end")({}, ctx);
		const firstCapture = hookCalls("capture");
		assert.equal(firstCapture.length, 1, "agent_end must enqueue immediately");
		assert.ok(firstCapture[0].argv.includes("--no-flush"), "agent_end enqueue must be --no-flush");
		assert.ok(firstCapture[0].argv.includes("--json"), "agent_end enqueue must use strict contract");
		assert.equal(traceEntries("enqueue_done")[0].outcome, "enqueued");
		assert.equal(traceEntries("marker_write").length, 1, "write-ahead marker must be traced");
		assert.equal(traceEntries("marker_delete").length, 1, "confirmed durable marker must be deleted");
		assert.equal(traceEntries("flush_schedule").length, 1);
		assert.equal(
			hookCalls("flush").length,
			startupFlushes,
			"agent_end enqueue must not flush synchronously beyond the startup drain",
		);

		// 新 prompt 取消挂起 flush；取消后期满不再触发
		await handlers.get("before_agent_start")({ prompt: "more work", systemPrompt: "sys" }, ctx);
		assert.ok(
			traceEntries("flush_cancel").some((entry) => entry.reason === "prompt"),
			"before_agent_start must cancel the pending flush",
		);
		await sleep(delayMs * 2);
		assert.equal(hookCalls("flush").length, startupFlushes, "canceled flush must not fire");

		// 下一次 agent_end 重新排程 → 空闲到期后恰好再一次 flush。
		// 权威信号是 flush_done 落盘（扩展在子进程 close 后才写 trace）；
		// 等 hook-log 会抢跑——fake 在 stdin end 时就写日志，close 之前。
		await handlers.get("agent_end")({}, ctx);
		assert.equal(hookCalls("capture").length, 2);
		await waitFor(
			() => completedFlushes() === 2,
			"idle flush done",
			10000,
		);
		assert.equal(hookCalls("flush").length, startupFlushes + 1);

		// agent_end 后立即 shutdown：timer 取消，最终 capture 带 flush（非 --no-flush）
		await handlers.get("agent_end")({}, ctx);
		assert.equal(hookCalls("capture").length, 3);
		await handlers.get("session_shutdown")({}, ctx);
		assert.ok(
			traceEntries("flush_cancel").some((entry) => entry.reason === "shutdown"),
			"shutdown must cancel the pending flush timer",
		);
		const captures = hookCalls("capture");
		assert.equal(captures.length, 4, "session_shutdown must run the final capture");
		assert.ok(!captures[3].argv.includes("--no-flush"), "final capture must include flush");
		assert.ok(captures[3].argv.includes("--json"));
		assert.equal(traceEntries("final_capture").length, 1);
		assert.equal(traceEntries("final_capture")[0].outcome, "enqueued");
		await sleep(delayMs * 2);
		assert.equal(hookCalls("flush").length, startupFlushes + 1, "canceled shutdown timer must not fire later");

		console.log(
			JSON.stringify({
				ok: true,
				mode: busyOnce ? "main-busy" : "main",
				captures: hookCalls("capture").length,
				flushes: hookCalls("flush").length,
				enqueues: traceEntries("enqueue_done").length,
				markerDeletes: traceEntries("marker_delete").length,
				cancels: traceEntries("flush_cancel").length,
			}),
		);
	}
} catch (error) {
	// 失败时 dump 现场，供 Python 侧的断言消息呈现
	console.error("--- hook-log ---");
	console.error(existsSync(hookLog) ? readFileSync(hookLog, "utf8") : "<missing>");
	console.error("--- pi-trace ---");
	console.error(existsSync(traceFile) ? readFileSync(traceFile, "utf8") : "<missing>");
	throw error;
}
