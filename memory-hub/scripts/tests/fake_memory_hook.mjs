// Fake memory_hook.py stand-in for the pi extension e2e harness.
// Spawned as `node fake_memory_hook.mjs <args...>` (the extension's `python` is
// rendered as process.execPath). Records every invocation as a JSON line in
// HOOK_LOG so the driver can assert call ordering/counts.
import { appendFileSync } from "node:fs";

let stdin = "";
process.stdin.on("data", (chunk) => {
	stdin += chunk;
});
process.stdin.on("end", () => {
	appendFileSync(
		process.env.HOOK_LOG,
		JSON.stringify({ argv: process.argv.slice(2), stdin }) + "\n",
	);
});
