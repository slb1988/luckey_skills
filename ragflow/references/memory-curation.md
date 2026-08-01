# RAGFlow Memory 人工提炼与验证

## 固定目标

当前维护的 Memory：

- 名称：`ragflow-tips`
- Memory ID：`c8ab35ca8cac11f19e4fdd2ab8bff472`
- Base URL：优先读取环境变量 `RAGFLOW_BASE_URL`；未设置时使用 `http://192.168.2.13:9386`
- Token：只从项目根目录 `.env` 的 `RAGFLOW_TOKEN` 读取，禁止输出、记录或写入 Memory

## 触发语义

当用户表达以下意图时执行本流程，而不是只口头答应：

- `ragflow remember ...`
- `remember memory ...`
- `记住 ...`
- `把这个写进 memory`
- `更新 ragflow memory`
- 明确要求以后按当前结论、经验或流程处理

如果用户只是在一般语句中使用“记住”但没有长期保存意图，先简短确认，不要误写。

## 人工提炼原则

不要把整段聊天原样复制为唯一内容。先结合当前会话上下文，人工提炼 1～5 条可长期复用的信息：

1. **Semantic**：稳定事实、参数关系、领域结论。
2. **Episodic**：发生过的故障、决策、实验和验证结果。
3. **Procedural**：可执行的步骤、排障顺序、工作约定。
4. **Raw**：RAGFlow 会自动保存本次提交的原始问答，作为来源追溯。

每条内容尽量满足：

- 独立阅读也能理解，写清作用域和对象；
- 保留关键专有名词、参数名、端点和错误码；
- 排障经验采用“症状 → 根因 → 操作 → 验证”结构；
- 新事实替代旧事实时明确写出“旧值失效、新值生效”；
- 区分已验证事实与推测，不把猜测写成结论；
- 不保存寒暄、一次性状态或无关上下文；
- 禁止保存密码、Token、Cookie、API Key、私钥等凭据。

写入 API 接收的是一轮 `user_input + agent_response`。将 `user_input` 写成简短的记忆主题，将人工提炼结果写入 `agent_response`，由 RAGFlow 再抽取 semantic / episodic / procedural。

## 强制执行流程

### 1. 形成写入草案

整理：

- `entries`：1～5 组人工提炼后的问答；
- `tests`：至少 2 个用户未来可能真实提出的查询；
- 每个测试包含用于判断结果正确性的 `expected_any` 关键词。

测试不能只复述写入句子，至少包含一种换一种问法的自然语言查询。

### 2. 写入前建立基线

对所有测试调用：

```text
GET /api/v1/messages/search
```

保存写入前的命中 ID、类型和内容。基线用于证明写入后结果发生了变化。

### 3. 写入 Memory

调用：

```text
POST /api/v1/messages
```

使用稳定的人工维护 Agent ID，并为本次操作生成新的 Session ID。RAGFlow 会异步执行：

```text
保存 Raw → LLM 抽取 → Embedding → 建立索引
```

### 4. 等待异步抽取

轮询检索，不要在 POST 成功后立即宣称完成。确认至少满足：

- 本次 Session 的 Raw 已出现；
- 至少一条新的 semantic / episodic / procedural 记录出现，或者任务明确只需 Raw；
- 新记录处于启用状态。

### 5. 重复验证实际影响

至少运行 2 个测试查询。每个查询验证：

- 写入后出现不在基线中的新命中；
- 新命中来自本次 Session；
- 命中内容包含预期结论，而不是只在数据库里存在；
- 记录新命中的排名和记忆类型。

如果第一次失败：

1. 降低验证阈值到 `0.1` 排除门槛问题；
2. 检查关键词与向量权重；
3. 检查抽取结果是否过于宽泛、遗漏专有词或变成错误英文表达；
4. 重新人工改写为更独立、明确的记忆；
5. 再写入并重复测试。

最多自动改写重试 2 次。仍失败时如实报告，不得声称已生效。

### 6. 汇报

最终只报告：

- 提炼并写入了哪些长期记忆；
- Raw / Semantic / Episodic / Procedural 新增情况；
- 测试查询、写入前后差异、新命中排名；
- 是否通过；若未通过，说明失败原因和建议。

不要显示 Token，也不要输出完整 embedding。

## 自动化脚本

使用：

```bash
python .claude/skills/ragflow/scripts/memory_remember.py --input <payload.json>
```

输入示例：

```json
{
  "entries": [
    {
      "topic": "请记住更新 chunk_method 返回 405 的排障方法。",
      "content": "症状：更新 chunk_method 返回 HTTP 405。根因：误用批量文档端点。操作：改用单文档 PUT 端点并重新解析索引。验证：使用相同问题比较召回结果。"
    }
  ],
  "tests": [
    {
      "query": "修改分块方式报 405 怎么处理？",
      "expected_any": ["批量", "单文档", "重新解析"]
    },
    {
      "query": "chunk_method 更新后还要做什么？",
      "expected_any": ["重新解析", "索引"]
    }
  ]
}
```

脚本负责读取 `.env`、执行基线检索、写入、轮询和输出 JSON 验证报告。人工提炼和失败后的语义改写仍由 Agent 完成。