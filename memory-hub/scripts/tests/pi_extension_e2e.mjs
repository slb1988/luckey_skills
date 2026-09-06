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
const scoreGateMode = process.env.SCORE_GATE === "1";
const scoreAllZeroMode = process.env.SCORE_ALL_ZERO === "1";
const extractionBootstrapMode = process.env.EXTRACTION_BOOTSTRAP === "1";
const skillBootstrapMode = process.env.SKILL_BOOTSTRAP === "1";
const projectDirectiveMode = process.env.PROJECT_DIRECTIVE === "1";
const multilinePromptMode = process.env.MULTILINE_PROMPT === "1";
const recallCancelMode = process.env.RECALL_CANCEL === "1";
const personaManualMode = process.env.PERSONA_MANUAL === "1";
const personaOversizeMode = process.env.PERSONA_OVERSIZE === "1";
const personaAutoEnabled = process.env.MEMORY_HOOK_PI_PERSONA_CARD === "1";
const personaFailureMode = process.env.FAKE_PERSONA_CARD_FAIL === "1";

writeFileSync(transcriptPath, JSON.stringify({ type: "message", role: "user", text: "hello" }) + "\n");

const handlers = new Map();
const tools = new Map();
const commands = new Map();
const pi = {
	on(event, fn) {
		handlers.set(event, fn);
	},
	registerTool(tool) {
		tools.set(tool.name, tool);
	},
	registerCommand(name, command) {
		commands.set(name, command);
	},
};

const selectCalls = [];
const selectResolvers = [];
const widgetCalls = [];
const statusCalls = [];
const notifyCalls = [];
// v25：模拟 pi TUI 的 onTerminalInput 监听注册表，测试用其手动喂按键。
const terminalInputHandlers = new Set();
const ctx = {
	cwd: process.cwd(),
	hasUI: scoreGateMode || scoreAllZeroMode || recallCancelMode,
	mode: "tui",
	ui: {
		setWidget(key, lines) {
			widgetCalls.push({ key, lines });
		},
		setStatus(key, value) {
			statusCalls.push({ key, value });
		},
		notify(message, level) {
			notifyCalls.push({ message, level });
		},
		select(title, options) {
			selectCalls.push({ title, options });
			return new Promise((resolveChoice) => selectResolvers.push(resolveChoice));
		},
		onTerminalInput(handler) {
			terminalInputHandlers.add(handler);
			return () => terminalInputHandlers.delete(handler);
		},
	},
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
	assert.ok(commands.has("memory-card"), "extension must register /memory-card");
	assert.ok(tools.has("memory_persona_card"), "extension must register memory_persona_card");

	if (personaManualMode) {
		// Default-off only governs automatic first-turn injection. Manual command/tool remain usable.
		await handlers.get("session_start")({}, ctx);
		const firstStart = await handlers.get("before_agent_start")(
			{ prompt: "manual persona test", systemPrompt: "base-system" },
			ctx,
		);
		assert.match(firstStart.systemPrompt, /严格测试驱动/);
		assert.equal(hookCalls("persona-card").length, 0, "default-off bootstrap must not request a card");
		await commands.get("memory-card").handler("person-manual", ctx);
		assert.equal(hookCalls("persona-card").length, 1);
		assert.match(notifyCalls.at(-1).message, /canonical persona card/);
		const toolResult = await tools.get("memory_persona_card").execute(
			"persona-tool",
			{ person_id: "person-tool" },
			undefined,
			undefined,
			ctx,
		);
		assert.match(toolResult.content[0].text, /canonical persona card/);
		assert.equal(toolResult.details.personId, "person-tool");
		assert.equal(hookCalls("persona-card").length, 2);
		assert.deepEqual(
			hookCalls("persona-card").map((entry) => entry.argv[entry.argv.indexOf("--person-id") + 1]),
			["person-manual", "person-tool"],
		);
		assert.deepEqual(
			traceEntries("memory_persona_card").map((entry) => entry.trigger),
			["command", "tool"],
		);
		console.log(JSON.stringify({ ok: true, mode: "persona-manual" }));
	} else if (personaOversizeMode) {
		await handlers.get("session_start")({}, ctx);
		const firstStart = await handlers.get("before_agent_start")(
			{ prompt: "oversized persona test", systemPrompt: "base-system" },
			ctx,
		);
		const personaPrefix = firstStart.systemPrompt.split("# Memory Hub：")[0];
		assert.equal((personaPrefix.match(/P/g) || []).length, 2500, "bootstrap card must be capped at 2500");
		await commands.get("memory-card").handler("", ctx);
		assert.equal(notifyCalls.at(-1).message.length, 2500, "command card must be capped at 2500");
		const toolResult = await tools.get("memory_persona_card").execute(
			"persona-tool",
			{},
			undefined,
			undefined,
			ctx,
		);
		assert.equal(toolResult.content[0].text.length, 2500, "tool card must be capped at 2500");
		assert.equal(toolResult.details.truncated, true);
		assert.ok(traceEntries("memory_persona_card").every((entry) => entry.truncated === true));
		console.log(JSON.stringify({ ok: true, mode: "persona-oversize" }));
	} else if (catchupMode) {
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
	} else if (recallCancelMode) {
		// v25 取消语义：before_agent_start 的预热检索可被 Esc/Ctrl+C 中断
		//（fake search 延时 500ms，远晚于取消触发时机；子进程被杀则 fake 不会落
		// hook-log，hookCalls("search") 恒为 0）；memory_search 工具接 pi abort
		// signal，Esc 中断 agent 回合时同步杀子进程。
		await handlers.get("session_start")({}, ctx);

		// 第一轮：Ctrl+C 取消但不吞键（放行给 pi 的 clear/双击退出语义）
		const ctrlCStartPromise = handlers.get("before_agent_start")(
			{ prompt: "cancel bootstrap with ctrl+c", systemPrompt: "base-system" },
			ctx,
		);
		await waitFor(
			() => widgetCalls.some((entry) => entry.key === "memory-hub-recall"),
			"recall progress widget",
		);
		assert.equal(terminalInputHandlers.size, 1, "recall must register exactly one cancel listener");
		for (const handler of [...terminalInputHandlers]) {
			assert.equal(handler("a"), undefined, "unrelated keys must pass through");
			assert.equal(handler("\x03"), undefined, "ctrl+c must pass through to pi (not consumed)");
		}
		const ctrlCStart = await ctrlCStartPromise;
		assert.equal(ctrlCStart, undefined, "cancelled bootstrap must not inject memory");
		assert.equal(traceEntries("project_bootstrap")[0].outcome, "cancelled");
		assert.equal(traceEntries("recall_cancel").at(-1).key, "ctrl_c");
		assert.equal(hookCalls("search").length, 0, "cancelled child must be killed before the fake logs");
		assert.ok(
			notifyCalls.some((entry) => /手动跳过/.test(entry.message)),
			"cancel must notify the manual skip",
		);
		assert.ok(
			statusCalls.some((entry) => String(entry.value).includes("记忆召回已跳过")),
			"cancel must update the recall status",
		);
		assert.equal(terminalInputHandlers.size, 0, "cancel listener must be removed after recall");
		assert.ok(
			existsSync(join(stateDir, "pi-bootstrap-done", "sess-e2e.json")),
			"cancel counts as attempted and must not retry this session",
		);

		// 第二轮（新 session id）：Esc 取消且吞键（不触发内建 double-esc 选择器）
		const escCtx = {
			...ctx,
			sessionManager: {
				getSessionId: () => "sess-e2e-esc",
				getSessionFile: () => transcriptPath,
			},
		};
		const escStartPromise = handlers.get("before_agent_start")(
			{ prompt: "cancel bootstrap with escape", systemPrompt: "base-system" },
			escCtx,
		);
		await waitFor(() => terminalInputHandlers.size === 1, "second recall listener");
		for (const handler of [...terminalInputHandlers]) {
			assert.deepEqual(handler("\x1b"), { consume: true }, "escape must be consumed during recall");
		}
		const escStart = await escStartPromise;
		assert.equal(escStart, undefined, "escape-cancelled bootstrap must not inject memory");
		assert.equal(traceEntries("project_bootstrap").at(-1).outcome, "cancelled");
		assert.equal(traceEntries("recall_cancel").at(-1).key, "escape");
		assert.equal(hookCalls("search").length, 0, "escape-cancelled child must also be killed before logging");
		assert.equal(terminalInputHandlers.size, 0, "second listener must be removed");

		// memory_search 工具：agent 回合内 Esc → pi abort signal → 杀子进程（130）
		const searchTool = tools.get("memory_search");
		assert.ok(searchTool, "memory_search tool must be registered");
		const toolAbort = new AbortController();
		const toolPromise = searchTool.execute(
			"tool-call",
			{ query: "cancel tool search", limit: 5 },
			toolAbort.signal,
			undefined,
			ctx,
		);
		await sleep(50); // 等子进程起来（fake search 延时 500ms 才响应）
		toolAbort.abort();
		const toolResult = await toolPromise;
		assert.equal(toolResult.details.exitCode, 130, "aborted tool search must resolve with 130");
		assert.match(toolResult.content[0].text, /cancelled/);
		assert.equal(hookCalls("search").length, 0, "aborted tool child must be killed before logging");
		console.log(JSON.stringify({ ok: true, mode: "recall-cancel" }));
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
		const firstPrompt = extractionBootstrapMode
			? "You are the Skill extraction sub-agent. Analyze this session."
			: skillBootstrapMode
				? [
					'<skill name="memory-hub" location="D:\\skills\\memory-hub\\SKILL.md">',
					"skill body",
					"</skill>",
					"修改 pi extension",
				].join("\n")
				: multilinePromptMode
				? [
					"fix [Skill conflicts] D:\\skills\\teamcity-tool\\SKILL.md",
					"Implicit keys need to be on a single line at line 13, column 1:",
					"",
					"  the PLN_FlowAiReview AI-review pipeline (Sync/Unshelve)",
					"  ^",
				].join("\n")
				: [
			"You are working inside Orca, a multi-agent IDE.",
			"编排说明 ".repeat(900),
			"=== TASK ===",
			projectDirectiveMode
				? "project:maindev start work with exact question"
				: "start work with exact question",
		].join("\n");
		const firstStart = await handlers.get("before_agent_start")(
			{ prompt: firstPrompt, systemPrompt: "base-system" },
			ctx,
		);
		assert.equal(selectCalls.length, 0, "v18 must not expose internal recall scoring UI");
		assert.ok(
			widgetCalls.every((entry) => entry.key !== "memory-hub-score"),
			"v19 must not restore the player scoring widget",
		);
		if (extractionBootstrapMode) {
			assert.equal(firstStart, undefined, "extraction bootstrap must not inject memory");
			assert.equal(hookCalls("search").length, 0, "extraction bootstrap must not search");
			assert.equal(traceEntries("project_bootstrap")[0].outcome, "skipped_extraction");
			assert.ok(existsSync(join(stateDir, "pi-bootstrap-done", "sess-e2e.json")));
			console.log(JSON.stringify({ ok: true, mode: "extraction-bootstrap" }));
			process.exit(0);
		}
		if (skillBootstrapMode) {
			// 展开后的 <skill …> 注入块与裸 /skill: 命令都必须跳过首轮检索
			assert.equal(firstStart, undefined, "skill invocation must not inject memory");
			assert.equal(hookCalls("search").length, 0, "skill invocation must not search");
			assert.equal(traceEntries("project_bootstrap")[0].outcome, "skipped_skill_invocation");
			assert.ok(existsSync(join(stateDir, "pi-bootstrap-done", "sess-e2e.json")));
			const rawCtx = {
				...ctx,
				sessionManager: {
					getSessionId: () => "sess-e2e-raw-skill",
					getSessionFile: () => transcriptPath,
				},
			};
			const rawStart = await handlers.get("before_agent_start")(
				{ prompt: "/skill:memory-hub 修改 pi extension", systemPrompt: "base-system" },
				rawCtx,
			);
			assert.equal(rawStart, undefined, "raw /skill: command must not inject memory");
			assert.equal(hookCalls("search").length, 0, "raw /skill: command must not search");
			assert.equal(traceEntries("project_bootstrap").at(-1).outcome, "skipped_skill_invocation");
			assert.ok(existsSync(join(stateDir, "pi-bootstrap-done", "sess-e2e-raw-skill.json")));
			console.log(JSON.stringify({ ok: true, mode: "skill-bootstrap" }));
			process.exit(0);
		}
		const bootstrapTimedOut = process.env.FAKE_SEARCH_DELAY_MS !== undefined;
		if (bootstrapTimedOut) {
			if (personaAutoEnabled && !personaFailureMode) {
				assert.match(firstStart.systemPrompt, /^base-system\n\n# 关于 测试用户/);
				assert.doesNotMatch(firstStart.systemPrompt, /严格测试驱动/);
				assert.equal(hookCalls("persona-card").length, 1);
			} else {
				assert.equal(firstStart, undefined, "bootstrap timeout must continue without injection");
			}
			assert.equal(traceEntries("project_bootstrap")[0].outcome, "timeout");
			assert.equal(hookCalls("search").length, 0, "timed-out child is killed before fake logs");
		} else {
			if (personaAutoEnabled && !personaFailureMode) {
				assert.match(firstStart.systemPrompt, /^base-system\n\n# 关于 测试用户/);
				assert.match(firstStart.systemPrompt, /canonical persona card/);
				assert.ok(
					firstStart.systemPrompt.indexOf("canonical persona card") < firstStart.systemPrompt.indexOf("# Memory Hub："),
					"persona card must precede task-specific recall",
				);
				assert.equal(hookCalls("persona-card").length, 1);
				assert.equal(traceEntries("memory_persona_card")[0].outcome, "injected");
			} else {
				assert.match(firstStart.systemPrompt, /^base-system\n\n# Memory Hub/);
				assert.doesNotMatch(firstStart.systemPrompt, /canonical persona card/);
				if (personaFailureMode) {
					assert.equal(hookCalls("persona-card").length, 1);
					assert.equal(traceEntries("memory_persona_card")[0].outcome, "error");
					assert.equal(traceEntries("project_bootstrap")[0].persona_outcome, "error");
				} else {
					assert.equal(hookCalls("persona-card").length, 0, "default bootstrap must not request a card");
				}
			}
			assert.match(firstStart.systemPrompt, /严格测试驱动/);
			assert.equal(
				traceEntries("project_bootstrap")[0].outcome,
				"injected",
			);
			assert.equal(hookCalls("search").length, 1, "first prompt must search project memory once");
			if (!projectDirectiveMode && !multilinePromptMode) {
				assert.match(
					hookCalls("search")[0].argv[1],
					new RegExp(process.cwd().split(/[\\/]/).at(-1)),
					"bootstrap query must include the cwd project hint",
				);
			}
			if (multilinePromptMode) {
				const structuredQuery = hookCalls("search")[0].argv[1];
				assert.match(
					structuredQuery,
					/任务: fix \[Skill conflicts\]/,
					"v23: first line must become the 任务 intent",
				);
				assert.match(
					structuredQuery,
					/\n上下文:\nImplicit keys need/,
					"v23: pasted error block must stay in 上下文 behind a newline boundary",
				);
				assert.match(
					structuredQuery,
					/PLN_FlowAiReview/,
					"v23: context payload must be preserved for retrieval",
				);
				assert.equal(
					traceEntries("project_bootstrap")[0].prompt_source,
					"user_prompt",
				);
			}
			if (!multilinePromptMode) {
				assert.match(
					hookCalls("search")[0].argv[1],
					/start work with exact question/,
					"bootstrap query must include the first user prompt",
				);
				assert.doesNotMatch(
					hookCalls("search")[0].argv[1],
					/Orca|编排说明/,
					"bootstrap query must exclude the orchestration preamble",
				);
				assert.equal(traceEntries("project_bootstrap")[0].prompt_source, "orca_task");
			}
			if (projectDirectiveMode) {
				const bootstrapSearch = hookCalls("search")[0];
				assert.deepEqual(
					bootstrapSearch.argv.slice(
						bootstrapSearch.argv.indexOf("--project"),
						bootstrapSearch.argv.indexOf("--project") + 2,
					),
					["--project", "maindev"],
				);
				assert.match(bootstrapSearch.argv[1], /^maindev 任务: start work/);
				assert.doesNotMatch(bootstrapSearch.argv[1], /project:maindev/);
				assert.equal(traceEntries("project_bootstrap")[0].project_override, "maindev");
			}
			assert.ok(hookCalls("search")[0].argv.includes("6"), "bootstrap must keep a small result budget");
			assert.ok(hookCalls("search")[0].argv.includes("4000"), "bootstrap must cap injected characters");
			assert.equal(hookCalls("feedback").length, 0, "backend LLM judgments replace player feedback");
			if (ctx.hasUI) {
				assert.ok(widgetCalls.some((entry) => entry.key === "memory-hub-recall"));
				assert.ok(
					statusCalls.every((entry) => !String(entry.value).includes("记忆识别中")),
					"the progress widget must not be duplicated in the bottom status bar",
				);
				assert.match(notifyCalls[0].message, /已识别 2\/3 条历史记忆/);
				assert.match(notifyCalls[0].message, /项目验证约定/);
				assert.match(notifyCalls[0].message, /详情文件：.*recall-results/);
				assert.ok(existsSync(join(stateDir, "recall-results", "pi", "fixture", "fixture-recall.md")));
				assert.doesNotMatch(firstStart.systemPrompt, /recall-results|fixture-recall\.md/);
				assert.ok(statusCalls.some((entry) => String(entry.value).includes("记忆 2\/3")));
			}
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
		assert.ok(existsSync(join(stateDir, "pi-bootstrap-done", "sess-e2e.json")));
		// 模拟 Pi 进程重启/恢复同一 session：新扩展实例的内存 Set 为空，仍必须靠
		// durable done marker 跳过，不得再次检索或弹评分。
		const resumedHandlers = new Map();
		mod.default({
			on(event, fn) {
				resumedHandlers.set(event, fn);
			},
			registerTool() {},
			registerCommand() {},
		});
		const searchesBeforeResume = hookCalls("search").length;
		const selectsBeforeResume = selectCalls.length;
		const resumedStart = await resumedHandlers.get("before_agent_start")(
			{ prompt: "resume after restart", systemPrompt: "base-system" },
			ctx,
		);
		assert.equal(resumedStart, undefined);
		assert.equal(hookCalls("search").length, searchesBeforeResume);
		assert.equal(selectCalls.length, selectsBeforeResume);
		assert.ok(traceEntries("project_bootstrap_skip").some((entry) => entry.outcome === "already_completed"));

		const searchTool = tools.get("memory_search");
		assert.ok(searchTool, "memory_search tool must be registered");
		const searchesBeforeTool = hookCalls("search").length;
		const toolResult = await searchTool.execute(
			"tool-call",
			{ query: "SyncStaticMeshAssetMetaDT", limit: 7, project: "maindev" },
			undefined,
			undefined,
			ctx,
		);
		assert.equal(hookCalls("search").length, searchesBeforeTool + 1);
		const toolSearch = hookCalls("search").at(-1);
		assert.deepEqual(
			toolSearch.argv.slice(toolSearch.argv.indexOf("--project"), toolSearch.argv.indexOf("--project") + 2),
			["--project", "maindev"],
		);
		assert.equal(toolResult.details.project, "maindev");
		assert.deepEqual(toolResult.details.quality, {
			mode: "llm",
			candidates: 3,
			kept: 2,
			min_rating: 2,
		});
		assert.doesNotMatch(toolResult.content[0].text, /recall-results|fixture-recall\.md/);
		assert.ok(toolSearch.argv.includes("--write-result-file"));
		assert.deepEqual(
			toolSearch.argv.slice(toolSearch.argv.indexOf("--session-id"), toolSearch.argv.indexOf("--session-id") + 2),
			["--session-id", "sess-e2e"],
		);
		if (ctx.hasUI) {
			assert.match(notifyCalls.at(-1).message, /已识别 2\/3 条历史记忆/);
		}

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
				mode: personaFailureMode
					? "persona-failure"
					: personaAutoEnabled
						? "persona-auto"
						: scoreAllZeroMode
							? "score-all-zero"
							: scoreGateMode
								? "score-gate"
								: busyOnce
									? "main-busy"
									: "main",
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
