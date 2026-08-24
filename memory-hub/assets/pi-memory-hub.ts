// Managed by memory-hub/scripts/install_hooks.py.
// EXTENSION_VERSION 由 install_hooks.py 解析并与已安装副本比对；修改本模板必须递增版本号，
// check 发现已安装版本不一致会报 outdated，需重新 install 发布。
import { appendFileSync, existsSync, mkdirSync, readFileSync, readdirSync, renameSync, statSync, unlinkSync, utimesSync, writeFileSync } from "node:fs";
import { spawn } from "node:child_process";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

const EXTENSION_VERSION = "5";
const memoryHook = __MEMORY_HOOK_JSON__;
// python 解释器路径由 install_hooks.py 在安装时注入（__PYTHON_JSON__），
// 不再硬编码 /usr/bin/python3——Windows 上该路径不存在，spawn 会 exit 127 静默失败。
const python = __PYTHON_JSON__;
const maxOutputBytes = 1024 * 1024;

// v5 回合级持久化（替代 v4 的「agent_end 只排程内存计时器」）：
//   agent_end ① 原子写 write-ahead marker（pi-pending-enqueues/<sessionId>.json）
//   → ② await capture --no-flush --json（enqueue 进本地 spool 即 durable，
//   回合结束不依赖任何内存计时器）→ ③ 确认 durable 才删 marker → ④ 排程防抖 flush。
//   进程被杀：spool 里的 job 由任意后续 flush 补传；marker 残留由下一次
//   session_start 的 catch-up 补传。丢失窗口压到「marker 落盘前的进程内微秒级」。
// flush 仍走 AFK 防抖（默认 5 分钟，MEMORY_HOOK_PI_CAPTURE_DELAY_MS），
// before_agent_start 取消挂起的 flush；hub 版本只在 flush 时产生，无版本 churn。
// session_shutdown 不等计时器：收敛在途 enqueue 后做最终 capture（enqueue+flush）。
const defaultFlushDelayMs = 5 * 60 * 1000;
const defaultEnqueueTimeoutMs = 10 * 1000;
const flushTimeoutMs = 120 * 1000;
const catchupBudgetMs = 30 * 1000;

function flushDelayMs(): number {
	const raw = process.env.MEMORY_HOOK_PI_CAPTURE_DELAY_MS;
	if (!raw) return defaultFlushDelayMs;
	const parsed = Number(raw);
	if (!Number.isFinite(parsed) || parsed < 0) return defaultFlushDelayMs;
	return Math.trunc(parsed);
}

function enqueueTimeoutMs(): number {
	const raw = process.env.MEMORY_HOOK_PI_ENQUEUE_TIMEOUT_MS;
	if (!raw) return defaultEnqueueTimeoutMs;
	const parsed = Number(raw);
	if (!Number.isFinite(parsed) || parsed <= 0) return defaultEnqueueTimeoutMs;
	return Math.trunc(parsed);
}

const stateDir =
	process.env.MEMORY_HOOK_STATE_DIR ?? join(homedir(), ".local", "state", "memory-hub-hook");
// write-ahead marker 目录：一个 marker 只代表「该 session 有一次 enqueue 尚未确认
// durable」，不登记所有 open session（避开 pi transcript lazy 落盘的冲突）。
const pendingDir = join(stateDir, "pi-pending-enqueues");

// 全链路留痕：每次与 Memory Hub 的交互追加一条 JSONL 到
// ${MEMORY_HOOK_STATE_DIR:-~/.local/state/memory-hub-hook}/pi-trace.jsonl。
// v5 事件名互斥：marker_write/marker_delete/marker_quarantine、enqueue_done、
// flush_schedule/flush_cancel/flush_done、catchup_scan/catchup_done、final_capture、
// session_start、search。写日志失败不影响主流程。
const traceFile = join(stateDir, "pi-trace.jsonl");
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

function markerPath(sessionId: string): string {
	return join(pendingDir, sessionId.replace(/[^A-Za-z0-9._-]/g, "_") + ".json");
}

interface PendingMarker {
	sessionId: string;
	transcriptPath: string;
	cwd: string;
	writtenAt?: string;
}

function writeMarker(target: CaptureTarget): void {
	try {
		mkdirSync(pendingDir, { recursive: true });
		// 同目录临时文件 + rename：kill 在中间态只会留下 .tmp 残影，不会产出半截 JSON。
		const temp = join(pendingDir, `.${process.pid}.${Date.now()}.tmp`);
		writeFileSync(
			temp,
			JSON.stringify({
				sessionId: target.sessionId,
				transcriptPath: target.transcriptPath,
				cwd: target.cwd,
				writtenAt: new Date().toISOString(),
			} satisfies PendingMarker) + "\n",
			"utf8",
		);
		renameSync(temp, markerPath(target.sessionId));
		trace("marker_write", { session_id: target.sessionId, cwd: target.cwd });
	} catch (error) {
		trace("marker_write", { session_id: target.sessionId, error: String(error) });
	}
}

// durable 结果（enqueued/already_present）与终态 skip（内容层面的永久跳过，
// durable 结果（enqueued/already_present）与真正终态的 skip 才允许删 marker。
// skipped_missing_file 可能是 transcript 临时不可用（挂载/同步延迟），删 marker
// 等于永久丢弃该 session——保留给下轮 catch-up 重试；skipped_no_fields/
// error/timeout 同理保留。只有 extraction 子 session（永不归档）与 capture
// opt-out 是确定的重试无意义。
function isDurableOutcome(outcome: string): boolean {
	return outcome === "enqueued" || outcome === "already_present";
}

function isTerminalSkipOutcome(outcome: string): boolean {
	return outcome === "skipped_extraction" || outcome === "skipped_capture_env";
}

function deleteMarker(sessionId: string, reason: string, expectedRaw?: string): void {
	try {
		const path = markerPath(sessionId);
		if (expectedRaw !== undefined) {
			// 代际比对（评审 P1）：catch-up 等待 enqueue 期间，活体 session 的
			// agent_end 可能已写入新一代 marker；只能删自己读过的那一代，
			// 否则活体 enqueue 一旦失败/被杀就失去 catch-up 兑底。
			let current: string;
			try {
				current = readFileSync(path, "utf8");
			} catch {
				return; // 已不存在
			}
			if (current !== expectedRaw) {
				trace("marker_delete", { session_id: sessionId, reason, skipped: "newer_generation" });
				return;
			}
		}
		unlinkSync(path);
		trace("marker_delete", { session_id: sessionId, reason });
	} catch {
		// 已不存在等情况不影响主流程
	}
}

function quarantineMarker(fileName: string, error: unknown): void {
	try {
		renameSync(join(pendingDir, fileName), join(pendingDir, fileName + ".corrupt"));
	} catch {
		// 隔离失败保留现场
	}
	trace("marker_quarantine", { file: fileName, error: String(error) });
}

interface HubResult {
	code: number;
	stdout: string;
	durationMs: number;
}

// 模块作用域：writeMarker 等模块级函数要引用；声明在扩展闭包里会让 tsc 报
// Cannot find name（Node type-stripping 会抹掉注解，e2e 测不出来）。
interface CaptureTarget {
	trigger: string;
	sessionId: string;
	transcriptPath: string;
	cwd: string;
}

function runHub(
	args: string[],
	payload: Record<string, unknown> | undefined,
	cwd: string,
	timeoutMs: number,
	killOnTimeout = true,
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
			if (killOnTimeout) {
				child.kill("SIGTERM");
			} else {
				// enqueue 超时兜底：不杀子进程（它可能即将完成落盘），脱离引用让
				// pi 进程可自由退出；marker 未删，下次 session_start catch-up 幂等重试。
				child.unref();
				child.stdout.destroy();
			}
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

function lastJsonLine(stdout: string): Record<string, unknown> | null {
	const lines = stdout.trim().split("\n");
	for (let index = lines.length - 1; index >= 0; index--) {
		const line = lines[index].trim();
		if (!line.startsWith("{")) continue;
		try {
			return JSON.parse(line) as Record<string, unknown>;
		} catch {
			// 继续向上找
		}
	}
	return null;
}

export default function memoryHubExtension(pi: ExtensionAPI) {
	// capture opt-out（auto-skill extraction 子 session 等）：不写 marker、不
	// enqueue、不排程 flush、不 catch-up；memory_search 检索不受影响。
	const skipCapture = process.env.MEMORY_HUB_SKIP_CAPTURE === "1";

	interface PendingFlush {
		timer: ReturnType<typeof setTimeout>;
		trigger: string;
	}

	let pendingFlush: PendingFlush | null = null;
	let flushing = false;
	let flushAgain = false;
	let catchupRunning = false;
	let lastCwd = process.cwd();
	const inFlightEnqueues = new Set<Promise<string>>();

	function captureTarget(ctx: ExtensionContext, trigger: string): CaptureTarget | null {
		const sessionId = ctx.sessionManager.getSessionId();
		const transcriptPath = ctx.sessionManager.getSessionFile();
		if (!transcriptPath) {
			trace("enqueue_skip", { trigger, session_id: sessionId, cwd: ctx.cwd, reason: "no_transcript" });
			return null;
		}
		return { trigger, sessionId, transcriptPath, cwd: ctx.cwd };
	}

	function capturePayload(target: CaptureTarget): Record<string, unknown> {
		return {
			hook_event_name: "SessionEnd",
			session_id: target.sessionId,
			transcript_path: target.transcriptPath,
			cwd: target.cwd,
		};
	}

	// enqueue-only：capture --no-flush --json，await 但有上限；超时不杀子进程
	// （它可能即将完成落盘），由 marker + catch-up 兜底。
	function enqueueSession(target: CaptureTarget): Promise<string> {
		const promise = (async (): Promise<string> => {
			const result = await runHub(
				["capture", "--source", "pi", "--no-flush", "--json"],
				capturePayload(target),
				target.cwd,
				enqueueTimeoutMs(),
				false,
			);
			let outcome = "error";
			let parsed: Record<string, unknown> | null = null;
			if (result.code === 124) {
				outcome = "timeout";
			} else {
				parsed = lastJsonLine(result.stdout);
				if (parsed && typeof parsed.result === "string") {
					outcome = parsed.result;
				} else if (result.code === 127) {
					outcome = "error_spawn";
				}
			}
			trace("enqueue_done", {
				trigger: target.trigger,
				session_id: target.sessionId,
				cwd: target.cwd,
				outcome,
				exit_code: result.code,
				duration_ms: result.durationMs,
				job_id: parsed?.job_id,
				sha256: parsed?.sha256,
				transcript_bytes: parsed?.transcript_bytes,
			});
			return outcome;
		})();
		inFlightEnqueues.add(promise);
		const done = () => inFlightEnqueues.delete(promise);
		promise.then(done, done);
		return promise;
	}

	// flush 请求不得丢弃：与在途 flush 重叠时折叠为「结束后补跑一次」；
	// 子进程报 busy（另一进程持有 flush.lock）时有界重试。否则首批 claim 之后
	// 入队的 job 没有任何后续上传尝试（评审 P2）。
	async function runFlush(trigger: string): Promise<void> {
		if (flushing) {
			flushAgain = true;
			trace("flush_done", { trigger, outcome: "coalesced" });
			return;
		}
		flushing = true;
		try {
			let busyRetries = 0;
			let currentTrigger = trigger;
			for (;;) {
				flushAgain = false;
				const result = await runHub(["flush"], undefined, lastCwd, flushTimeoutMs);
				const parsed = lastJsonLine(result.stdout);
				const flush = parsed?.flush as Record<string, unknown> | undefined;
				const busy = flush?.busy === true;
				const outcome = busy ? "busy" : result.code === 0 ? "completed" : "failed";
				trace("flush_done", {
					trigger: currentTrigger,
					outcome,
					exit_code: result.code,
					duration_ms: result.durationMs,
					completed: flush?.completed,
					failed: flush?.failed,
					recovered: flush?.recovered,
				});
				if (busy && busyRetries < 3) {
					busyRetries++;
					await new Promise((resolve) => setTimeout(resolve, 1000));
					continue;
				}
				if (flushAgain) {
					// 在途期间又有 flush 请求：补跑一次覆盖其后入队的 job
					currentTrigger = `${currentTrigger}_coalesced`;
					continue;
				}
				break;
			}
		} finally {
			flushing = false;
		}
	}

	function cancelPendingFlush(reason: string): void {
		if (!pendingFlush) return;
		clearTimeout(pendingFlush.timer);
		trace("flush_cancel", { reason, trigger: pendingFlush.trigger });
		pendingFlush = null;
	}

	function scheduleFlush(trigger: string): void {
		cancelPendingFlush("reschedule");
		const delayMs = flushDelayMs();
		if (delayMs <= 0) {
			void runFlush(trigger);
			return;
		}
		const timer = setTimeout(() => {
			pendingFlush = null;
			void runFlush(`${trigger}_idle`);
		}, delayMs);
		// 计时器不得拖住 pi 进程退出；退出由 session_shutdown 的最终 capture 兜底
		timer.unref();
		pendingFlush = { timer, trigger };
		trace("flush_schedule", { trigger, delay_ms: delayMs });
	}

	// session_start catch-up：有界扫描遗留 marker → 逐个 enqueue-only 确认 →
	// 全部 settle 后只发起一次 flush。后台执行，不阻塞新会话开始。
	// 扫描不设数量上限（固定前缀会让后面的 marker 永久饥饿，评审 P2）：
	// 按 mtime 升序处理，保留的 marker 触戳到队尾轮换；总成本由时间预算约束。
	async function catchupPending(): Promise<void> {
		interface ScannedMarker {
			name: string;
			raw: string;
			marker: PendingMarker;
		}
		const started = Date.now();
		const markers: ScannedMarker[] = [];
		let quarantined = 0;
		try {
			mkdirSync(pendingDir, { recursive: true });
			const names = readdirSync(pendingDir)
				.filter((name) => name.endsWith(".json"))
				.map((name) => {
					try {
						return { name, mtime: statSync(join(pendingDir, name)).mtimeMs };
					} catch {
						return { name, mtime: 0 };
					}
				})
				.sort((a, b) => a.mtime - b.mtime);
			for (const { name } of names) {
				const raw = readFileSync(join(pendingDir, name), "utf8");
				try {
					const parsed = JSON.parse(raw) as Partial<PendingMarker>;
					if (
						typeof parsed.sessionId === "string" &&
						typeof parsed.transcriptPath === "string" &&
						typeof parsed.cwd === "string"
					) {
						markers.push({ name, raw, marker: parsed as PendingMarker });
					} else {
						throw new Error("bad marker shape");
					}
				} catch (error) {
					quarantineMarker(name, error);
					quarantined++;
				}
			}
		} catch (error) {
			trace("catchup_scan", { error: String(error) });
			return;
		}
		trace("catchup_scan", { scanned: markers.length, quarantined });
		if (markers.length === 0) return;
		let confirmed = 0;
		let kept = 0;
		let deferred = 0;
		for (const { raw, marker } of markers) {
			if (Date.now() - started > catchupBudgetMs) {
				deferred++;
				continue;
			}
			const outcome = await enqueueSession({
				trigger: "session_start_catchup",
				sessionId: marker.sessionId,
				transcriptPath: marker.transcriptPath,
				cwd: marker.cwd,
			});
			if (isDurableOutcome(outcome) || isTerminalSkipOutcome(outcome)) {
				deleteMarker(marker.sessionId, outcome, raw);
				confirmed++;
			} else {
				kept++;
				// 触戳到队尾：下一轮扫描先处理其他遗留 marker，轮流不重不漏
				try {
					utimesSync(markerPath(marker.sessionId), new Date(), new Date());
				} catch {
					// 被并发删除等，忽略
				}
			}
		}
		await runFlush("session_start_catchup");
		trace("catchup_done", { scanned: markers.length, confirmed, kept, deferred, quarantined });
	}

	pi.on("session_start", async (_event, ctx) => {
		lastCwd = ctx.cwd;
		trace("session_start", {
			session_id: ctx.sessionManager.getSessionId(),
			cwd: ctx.cwd,
		});
		// 运行中守卫而非一次性开关：catch-up 可能因 enqueue 超时保留 marker、或超过
		// 扫描上限遗留 marker——长驻进程的后续 session_start（如进程内 /new）必须重试。
		if (!skipCapture && !catchupRunning) {
			catchupRunning = true;
			void catchupPending().finally(() => {
				catchupRunning = false;
			});
		}
	});

	pi.on("before_agent_start", async (_event, _ctx) => {
		// 用户回到键盘、会话继续生长：取消挂起的 flush，等下一轮空闲再计时。
		// enqueue/marker 在 agent_end 已完成，无需也不应撤销。
		cancelPendingFlush("prompt");
	});

	pi.on("agent_end", async (_event, ctx) => {
		lastCwd = ctx.cwd;
		if (skipCapture) return;
		const target = captureTarget(ctx, "agent_end");
		if (!target) return;
		// write-ahead：marker 先落盘，再 enqueue——进程在任意点被杀，
		// 下次 session_start 的 catch-up 都能幂等补传。
		writeMarker(target);
		const outcome = await enqueueSession(target);
		if (isDurableOutcome(outcome) || isTerminalSkipOutcome(outcome)) {
			deleteMarker(target.sessionId, outcome);
		}
		scheduleFlush("agent_end");
	});

	pi.on("session_shutdown", async (_event, ctx) => {
		cancelPendingFlush("shutdown");
		if (skipCapture) return;
		// 收敛在途 enqueue：每个都有超时上限，allSettled 本身有界；
		// 超时未完成的由各自 marker 兜底，不阻塞退出。
		if (inFlightEnqueues.size > 0) {
			await Promise.allSettled([...inFlightEnqueues]);
		}
		const target = captureTarget(ctx, "session_shutdown");
		if (!target) return;
		// 最终 capture：enqueue+flush 一体。flush 遇锁占用会得 busy——trace 区分
		// durable（本地已入队）与 uploaded；留在 queued 的 job 由下次 flush 补传。
		const result = await runHub(
			["capture", "--source", "pi", "--json"],
			capturePayload(target),
			target.cwd,
			flushTimeoutMs,
		);
		const parsed = lastJsonLine(result.stdout);
		const outcome = typeof parsed?.result === "string" ? parsed.result : "error";
		const flush = parsed?.flush as Record<string, unknown> | undefined;
		trace("final_capture", {
			session_id: target.sessionId,
			cwd: target.cwd,
			outcome,
			flush: flush ? (flush.busy === true ? "busy" : "attempted") : "skipped",
			exit_code: result.code,
			duration_ms: result.durationMs,
			job_id: parsed?.job_id,
			sha256: parsed?.sha256,
		});
		if (isDurableOutcome(outcome) || isTerminalSkipOutcome(outcome)) {
			deleteMarker(target.sessionId, outcome);
		}
	});

	pi.registerTool({
		name: "memory_search",
		label: "Memory Search",
		description:
			"Search durable memories captured from Claude Code, Codex, and Pi sessions. " +
			"Use proactively when the current context is insufficient: references to past work " +
			"(上次/之前/继续), unfamiliar project names or past decisions, user preferences, or facts " +
			"not present in this session. Compose a focused keyword query instead of guessing; " +
			"on empty or irrelevant results, retry with different keywords or a larger limit.",
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
