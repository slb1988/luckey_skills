// Fake memory_hook.py stand-in for the pi extension e2e harness.
// Spawned as `node fake_memory_hook.mjs <args...>` (the extension's `python` is
// rendered as process.execPath). Records every invocation as a JSON line in
// HOOK_LOG so the driver can assert call ordering/counts.
// v5 起扩展依赖严格 JSON 契约：capture --json 必须回一行 {"result": ...}，
// flush 必须回 {"flush": {...}}，否则扩展侧 outcome 判为 error。
// 忠实模拟脚本的早退分支：transcript 不存在 → skipped_missing_file；
// 首条消息是 extraction 签名 → skipped_extraction。
// FLUSH_BUSY_ONCE=1：首次 flush 报 busy（跨进程计数文件），之后正常——
// 驱动扩展的 busy 有界重试路径。FAKE_DELAY_MS：capture 响应延时（毫秒），
// 用于制造 catch-up 与活体 agent_end 的并发窗口（marker 代际竞态测试）。
import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

let stdin = "";
process.stdin.on("data", (chunk) => {
	stdin += chunk;
});
process.stdin.on("end", () => {
	const delay = Number(process.env.FAKE_DELAY_MS || 0);
	if (delay > 0) {
		setTimeout(respond, delay);
	} else {
		respond();
	}
});

function respond() {
	const args = process.argv.slice(2);
	const searchDelay = args[0] === "search" ? Number(process.env.FAKE_SEARCH_DELAY_MS || 0) : 0;
	if (searchDelay > 0) {
		setTimeout(() => respondNow(args), searchDelay);
		return;
	}
	respondNow(args);
}

function respondNow(args) {
	appendFileSync(
		process.env.HOOK_LOG,
		JSON.stringify({ argv: args, stdin }) + "\n",
	);
	if (args[0] === "capture" && args.includes("--json")) {
		let result = "enqueued";
		try {
			const hookPayload = JSON.parse(stdin);
			const transcript = hookPayload.transcript_path;
			if (!transcript || !existsSync(transcript)) {
				result = "skipped_missing_file";
			} else {
				const firstLine = readFileSync(transcript, "utf8").split("\n")[0] ?? "";
				if (firstLine.includes("You are the Skill extraction sub-agent.")) {
					result = "skipped_extraction";
				}
			}
		} catch {
			// 解析失败按正常入队处理
		}
		const payload = { result, job_id: 1, sha256: "abc123", session_id: "s", transcript_bytes: 42 };
		if (!args.includes("--no-flush")) {
			payload.flush = { busy: false, completed: 1, failed: 0, recovered: 0 };
		}
		console.log(JSON.stringify(payload));
	} else if (args[0] === "search") {
		if (args.includes("--json")) {
			let resultFile;
			if (args.includes("--write-result-file")) {
				const resultDir = join(process.env.MEMORY_HOOK_STATE_DIR, "recall-results", "pi", "fixture");
				mkdirSync(resultDir, { recursive: true });
				resultFile = join(resultDir, "fixture-recall.md");
				writeFileSync(resultFile, "# Memory Hub Recall Result\n\n## 本轮摘要\n\n- 识别结果：2/3\n");
			}
			console.log(JSON.stringify({
				project_id: args.includes("--project")
					? args[args.indexOf("--project") + 1]
					: "fixture",
				retrieval: {
					retrieval_id: "retrieval-e2e",
					query_hash: "a".repeat(64),
					policy_version: "v2-fts-top3-llm",
				},
				quality: { mode: "llm", candidates: 3, kept: 2, min_rating: 2 },
				result_file: resultFile,
				context: "[project:fixture]\n- 项目使用严格测试驱动；先跑小规模验证再全量修改。",
				facts: [
					{
						result_id: "memory-useful",
						source_type: "memory_document",
						summary: "项目验证约定",
						text: "项目使用严格测试驱动；先跑小规模验证再全量修改。",
					},
					{
						result_id: "memory-noise",
						source_type: "memory_document",
						summary: "无关生活记录",
						text: "昨天午饭吃了面。",
					},
				],
			}));
		} else {
			console.log("[project:fixture]\n- 项目使用严格测试驱动；先跑小规模验证再全量修改。");
		}
	} else if (args[0] === "flush") {
		let busy = false;
		if (process.env.FLUSH_BUSY_ONCE === "1") {
			const stateFile = process.env.HOOK_LOG + ".busy";
			if (!existsSync(stateFile)) {
				writeFileSync(stateFile, "1");
				busy = true;
			}
		}
		console.log(
			JSON.stringify({
				flush: { busy, completed: busy ? 0 : 1, failed: 0, recovered: 0 },
				status: {},
			}),
		);
	}
}
