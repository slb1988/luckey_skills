# Mermaid authoring reference

Standalone `.mmd` files contain raw Mermaid text. They do not contain Markdown fences or surrounding prose.

## Selection and defaults

| Need | Syntax | Default direction |
| --- | --- | --- |
| Workflow, decision tree, dependencies, data flow | `flowchart` | `LR` for short process; `TD` for hierarchy, long labels, or 10+ nodes |
| Calls, handoffs, protocol behavior | `sequenceDiagram` | time runs top to bottom |
| Lifecycle and allowed transitions | `stateDiagram-v2` | automatic |
| Topic hierarchy or brainstorming | `mindmap` | radial |
| Dates and delivery plan | `gantt` | time runs left to right |
| Event history | `timeline` | time runs left to right |

Prefer a `flowchart` with `subgraph` boundaries for architecture diagrams because it is broadly supported and easy to edit.

## Flowchart template

```mermaid
flowchart LR
  input["AI 输出"] --> inspect{"包含分支或依赖？"}
  inspect -->|否| prose["保留简短文字"]
  inspect -->|是| model["提取结论、依据与动作"]
  model --> diagram["生成 .mmd"]
  diagram --> validate{"语法校验通过？"}
  validate -->|否| fix["修复语法"]
  fix --> validate
  validate -->|是| review["在 Mermaid Code 中查看"]
```

Useful shapes:

```text
step["过程"]
decision{"判断"}
data[("数据")]
terminal(["开始或结束"])
external[["外部系统"]]
```

Use explicit edge labels for branches: `decision -->|是| next`. Use dotted arrows such as `-.->` only for secondary or inferred relationships. A visible return edge should explain the feedback condition.

## Architecture or data-flow template

```mermaid
flowchart LR
  subgraph client["客户端"]
    user["用户"] --> app["应用"]
  end

  subgraph service["服务层"]
    api["API"] --> worker["任务处理"]
  end

  store[("数据存储")]
  app -->|请求| api
  worker -->|读写| store
  worker -->|结果| app
```

Boundaries should represent ownership, trust zones, deployment units, or stages. Do not group merely to add color.

## Sequence template

```mermaid
sequenceDiagram
  autonumber
  actor U as 用户
  participant A as AI Agent
  participant M as Mermaid Code

  U->>A: 描述需要梳理的流程
  A->>A: 生成并校验 .mmd
  A->>M: 打开文件或发送临时预览
  M-->>U: 展示可视化结果
  alt 需要调整
    U->>A: 指出要修改的节点或关系
    A->>M: 更新文件
  else 已清晰
    M-->>U: 保留可编辑源文件
  end
```

Use `->>` for a call, `-->>` for a response, `Note over A,M:` for a short constraint, and `loop`, `alt`/`else`, `opt`, or `par` only when the control structure matters.

## State template

```mermaid
stateDiagram-v2
  [*] --> Draft
  Draft --> Validating: 保存
  Validating --> Draft: 校验失败
  Validating --> Reviewed: 校验通过
  Reviewed --> Draft: 需要修改
  Reviewed --> [*]: 确认完成
```

States are nouns or durable conditions; transition labels are events or guards. If the main concern is work steps rather than valid transitions, use a flowchart instead.

## Mind map template

```mermaid
mindmap
  root((AI 思路梳理))
    目标
      要解决的问题
      成功标准
    依据
      已知事实
      假设
    决策
      选项
      取舍
    行动
      下一步
      验证方式
```

Mind-map structure is indentation-sensitive. Use it for hierarchy, not for ordered execution.

## Readability and syntax safety

- Use ASCII IDs such as `validate` and put Chinese or punctuation in quoted labels: `validate["校验结果"]`.
- Avoid reserved or ambiguous bare words. In particular, quote labels containing `end`, colons, brackets, parentheses, or Markdown-like punctuation.
- Define each node once when possible, then connect by ID.
- Keep labels short: one idea per node, usually under 16 Chinese characters or 8 English words.
- Use at most two or three visual classes. Semantics come before styling.
- Do not invent relationships. Mark uncertain items explicitly as `假设` or with a dotted edge.
- Prefer several small diagrams over a single wall-sized graph.
- Validate with the current Mermaid CLI because renderers embedded in other products may support different Mermaid versions.

Official syntax index: <https://mermaid.js.org/intro/syntax-reference.html>

A validated standalone example is available at [examples/ai-workflow.mmd](examples/ai-workflow.mmd).
