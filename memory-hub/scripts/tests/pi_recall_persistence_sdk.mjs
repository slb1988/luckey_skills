import assert from "node:assert/strict";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const [extensionPath, root] = process.argv.slice(2);
const packageDir = process.env.PI_CODING_AGENT_PACKAGE_DIR;
assert.ok(extensionPath && root && packageDir);
const { createAgentSession, DefaultResourceLoader, ModelRuntime, SessionManager, SettingsManager } =
  await import(pathToFileURL(join(packageDir, "dist/index.js")).href);
const state = process.env.MEMORY_HOOK_STATE_DIR;
const agentDir = join(root, "agent"), sessionDir = join(root, "sessions");
mkdirSync(agentDir); mkdirSync(sessionDir);
const type = "memory-hub-recall-v1";
const body = "严格测试驱动";
const errors = [], requests = [], passed = [];
const readJsonl = path => readFileSync(path, "utf8").trim().split("\n").filter(Boolean).map(line => JSON.parse(line));
const searches = () => readJsonl(process.env.HOOK_LOG).filter(e => e.argv[0] === "search").length;
const checkpoint = (name, expected) => {
  const text = JSON.stringify(requests.at(-1));
  assert.equal(text.split(body).length - 1, expected, name);
  assert.doesNotMatch(text, /fixture-recall\.md|contentHash|sourceSessionId|resultFile|memory-noise|昨天午饭/);
  if (expected) assert.ok(requests.at(-1).messages.some(m => m.role === "user" && JSON.stringify(m.content).includes(body)));
  passed.push(name);
};
globalThis.fetch = async () => { throw new Error("Network disabled for SDK tests"); };
const modelRuntime = await ModelRuntime.create({ authPath: join(agentDir, "auth.json"), modelsPath: null,
  modelsStorePath: join(agentDir, "models-store.json"), refreshOnCreate: false, allowModelNetwork: false });
modelRuntime.registerProvider("recall-sdk-test", {
  api: "anthropic-messages", baseUrl: "http://127.0.0.1:1", apiKey: "test-only",
  models: [{ id: "probe", name: "probe", input: ["text"], reasoning: false, contextWindow: 100000,
    maxTokens: 64, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
  streamSimple(model, context) {
    requests.push(structuredClone(context));
    const response = { role: "assistant", api: model.api, provider: model.provider, model: model.id,
      content: [{ type: "text", text: "ok" }], stopReason: "stop", timestamp: Date.now(),
      usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } } };
    return { async *[Symbol.asyncIterator]() { yield { type: "done", reason: "stop", message: response }; }, result: async () => response };
  },
});
const settingsManager = SettingsManager.inMemory({ compaction: { enabled: false, keepRecentTokens: 0 }, retry: { enabled: false } });
async function open(manager, cwd = root) {
  const resourceLoader = new DefaultResourceLoader({ cwd, agentDir, settingsManager,
    noExtensions: true, noSkills: true, noContextFiles: true, noPromptTemplates: true, noThemes: true,
    additionalExtensionPaths: [resolve(extensionPath)], agentsFilesOverride: () => ({ agentsFiles: [] }),
    extensionFactories: [pi => {
      pi.on("session_before_compact", (event, ctx) => {
        const lastUser = ctx.sessionManager.getBranch().findLast(e => e.type === "message" && e.message.role === "user");
        return { compaction: { summary: "Controlled summary without original recall.",
          firstKeptEntryId: lastUser.id, tokensBefore: event.preparation.tokensBefore } };
      });
    }],
  });
  await resourceLoader.reload();
  assert.deepEqual(resourceLoader.getExtensions().errors, []);
  const { session } = await createAgentSession({ cwd, agentDir, modelRuntime, model: modelRuntime.getModel("recall-sdk-test", "probe"),
    resourceLoader, settingsManager, sessionManager: manager, thinkingLevel: "off", tools: ["read"] });
  await session.bindExtensions({ onError: error => errors.push(error) });
  return session;
}
const markerPath = manager => join(state, "pi-bootstrap-done", manager.getSessionId() + ".json");
const persistMarker = (manager, extra) => writeFileSync(markerPath(manager), JSON.stringify({
  session_id: manager.getSessionId(), cwd: root, completed_at: new Date().toISOString(), ext_version: "41", outcome: "injected", ...extra,
}));
const ownEntries = manager => manager.getBranch().filter(e => e.type === "custom_message" && e.customType === type);
const child = '[chat-hub 可信逻辑说话人]\nprofile_id: "xiaoyingtao"\n[/chat-hub 可信逻辑说话人]\n继续任务';
const owner = '[chat-hub 可信逻辑说话人]\nprofile_id: "sunlaibing"\n[/chat-hub 可信逻辑说话人]\n继续任务';
let session;
try {
  let manager = SessionManager.create(root, sessionDir);
  session = await open(manager);
  await session.prompt("perform a concrete verification task"); checkpoint("first", 1);
  const file = session.sessionFile;
  assert.equal(readJsonl(file).filter(e => e.type === "custom_message" && e.customType === type).length, 1);
  const receipt = JSON.parse(readFileSync(markerPath(manager), "utf8"));
  assert.equal(receipt.delivery.content, ownEntries(manager)[0].content);
  await session.prompt("next task"); checkpoint("second", 1);
  await session.reload(); await session.prompt("after reload"); checkpoint("reload", 1);
  session.dispose();
  manager = SessionManager.open(file, sessionDir); session = await open(manager);
  await session.prompt("after disk resume"); checkpoint("resume", 1);
  await session.compact(); await session.prompt("after compaction"); checkpoint("compaction-replay", 1);
  assert.equal(ownEntries(manager).length, 2);
  assert.equal(searches(), 1, "normal lifecycle must not repeat retrieval");
  const liveLeaf = manager.getLeafId();
  session.dispose();
  const brancher = SessionManager.open(file, sessionDir);
  const fork = brancher.createBranchedSession(brancher.getLeafId());
  manager = SessionManager.open(fork, sessionDir); session = await open(manager);
  await session.prompt("continue copied branch"); checkpoint("branch-copy", 1);
  await session.prompt(child); checkpoint("speaker-isolation", 0);
  await session.prompt(owner); checkpoint("owner-restored", 1);
  manager.appendContextEdit(ownEntries(manager).at(-1).id, null);
  await session.prompt("after explicit context deletion"); checkpoint("explicit-delete", 0);
  await session.compact(); await session.prompt("deleted recall after compaction"); checkpoint("deleted-not-resurrected", 0);
  assert.equal(searches(), 1);
  session.dispose();

  manager = SessionManager.open(file, sessionDir);
  const firstUser = manager.getBranch().find(e => e.type === "message" && e.message.role === "user");
  manager.branch(firstUser.id);
  session = await open(manager);
  await session.prompt("different active branch before recall delivery"); checkpoint("abandoned-branch-not-restored", 0);
  assert.equal(searches(), 1);
  session.dispose();

  const otherCwd = join(root, "other-workspace"); mkdirSync(otherCwd);
  manager = SessionManager.open(file, sessionDir, otherCwd); manager.branch(liveLeaf);
  assert.ok(manager.buildSessionProjection().messages.some(m => m.customType === type));
  session = await open(manager, otherCwd);
  await session.prompt("different workspace"); checkpoint("cwd-isolation", 0);
  assert.equal(searches(), 1);
  session.dispose();

  manager = SessionManager.create(root, sessionDir);
  const saved = structuredClone(receipt.delivery);
  saved.details.sourceSessionId = manager.getSessionId(); saved.details.anchorId = null;
  persistMarker(manager, { delivery: saved });
  session = await open(manager);
  await session.prompt("recover prepared delivery without a persisted message"); checkpoint("receipt-gap-recovery", 1);
  assert.equal(ownEntries(manager).length, 1);
  assert.equal(searches(), 1);
  session.dispose();

  for (const mismatch of [false, true]) {
    manager = SessionManager.create(root, sessionDir);
    persistMarker(manager, { ext_version: "40" });
    const resultDir = join(state, "recall-results", "pi", "fixture"); mkdirSync(resultDir, { recursive: true });
    const resultFile = join(resultDir, "legacy-" + manager.getSessionId() + ".md");
    const context = "legacy approved " + body;
    const stats = { source: "server_stage_b_context", status: "completed", suppression_reason: null,
      scope: { current_project_id: "fixture", groups: ["user:sunlaibing"] } };
    writeFileSync(resultFile, [
      "# Memory Hub Recall Result", "## 客户端上下文与统计（JSON 审计）", "```json",
      JSON.stringify({ context_stats: stats, context }), "```",
      "## 原始用户 prompt（仅本地审计）", "```json",
      JSON.stringify({ source_ref: { session_id: mismatch ? "wrong-session" : manager.getSessionId(), session_file: manager.getSessionFile() } }), "```",
      "## 查询信息", "- project_id: `fixture`",
    ].join("\n"));
    const tracePath = join(state, "pi-trace.jsonl");
    writeFileSync(tracePath, readFileSync(tracePath, "utf8") + JSON.stringify({
      kind: "project_bootstrap", session_id: manager.getSessionId(), cwd: root, outcome: "injected", project_override: null,
      result_file: resultFile, result_chars: context.length, context_stats: stats,
    }) + "\n");
    session = await open(manager);
    await session.prompt("continue legacy session"); checkpoint(mismatch ? "legacy-mismatch-refused" : "legacy-backfill", mismatch ? 0 : 1);
    assert.equal(searches(), 1, "legacy migration must be local-only");
    session.dispose();
  }
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({ ok: true, passed, searches: searches(), model_requests: requests.length, real_llm_calls: 0 }));
  process.exit(0);
} finally { session?.dispose(); }
