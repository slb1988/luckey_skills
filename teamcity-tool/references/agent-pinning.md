# Agent 名称策略、白名单与同机组

> 参数解析、隐式要求、队列诊断和安全重排统一见 [build-chain-parameters.md](build-chain-parameters.md)。
> 本文仅定义 Agent 选择策略，不把“匹配成功”当作工作区或构建已验证。

## 名称要求是策略，不是运行后反推的值

```kotlin
// Flow：字面正则下发给已声明 DefaultAgent 的前置任务
params {
    param("DefaultAgent", "^WinBuilder.*$")
    param("override.dep.*.DefaultAgent", "^WinBuilder.*$")
}

// WinBuilder 专属 Task；共享 Task 的默认值按自己的调用方选择
params {
    param("DefaultAgent", "^WinBuilder.*$")
}
requirements {
    matches("teamcity.agent.name", "%DefaultAgent%")
}
```

- `matches` 消费正则，`equals` 消费字面名称；`WinBuilder*` 的前缀策略写作 `^WinBuilder.*$`。
- 不用尚未确定的 `%teamcity.agent.name%` 决定 Agent requirement。选定 Agent 后，用它计算路径是另一件事。
- 新配置显式声明普通默认值，不依赖 `%reverse.dep.*.DefaultAgent|.*%` 作为通用 fallback 语法。
- `override.dep` 只更新接收方已声明的键；`reverse.dep` 保留表达式且可创建键。
  名称策略使用字面正则；目标 Agent 路径公式的延迟解析是合法的另一种用途，见主参考。

## 多个精确名称用一个 OR 正则

同一配置的所有 requirements（含继承的）按 **AND** 合并。
两个 `equals` 不能表达“WinBuilder1 或 WinBuilder4”。

| 意图 | `teamcity.agent.name` 的 `matches` 值 |
|---|---|
| 任意 WinBuilder 前缀 | `^WinBuilder.*$` |
| 只允许两台明确的机器 | `^(?:WinBuilder1|WinBuilder4)$` |
| 不按名称限制 | 不设名称 requirement；仍保留必要的能力/Pool 边界 |

```kotlin
requirements {
    matches("teamcity.agent.name", "^(?:WinBuilder1|WinBuilder4)$")
}
```

通过 REST 修改已有 requirement，而不是不断叠加新条件：

```http
PUT /app/rest/buildTypes/id:<BT_ID>/agent-requirements/<REQUIREMENT_ID>
Content-Type: application/json
Accept: application/json

{
  "type": "matches",
  "properties": {
    "property": [
      {"name": "property-name", "value": "teamcity.agent.name"},
      {"name": "property-value", "value": "^(?:WinBuilder1|WinBuilder4)$"}
    ]
  }
}
```

更新可能生成新的 `RQ_*` ID，使用返回值或重新读取集合，不复用旧 ID。
版本化配置还需确认变更已写回并被服务器应用。

## 单节点、同机组与可执行状态

`runOnSameAgent=true` 把相关任务绑定到同一台机器，其候选由各任务的要求取交集。
专属能力要求放在专属节点，共享任务仍可服务其他链；不能为了扩容而去掉正确性所需的 OS/工具要求。

配置级检查：

```text
GET /app/rest/agents?locator=compatible:(buildType:(id:<BT_ID>))&fields=agent(id,name,connected,enabled,authorized)
```

但配置页不包含某次 Flow 的完整触发上下文；验证运行中的链要查询具体 queued build 的候选，
并在其 Compatible Agents 页面查看隐式要求。REST 默认过滤、单节点与同机组范围也可能影响列表。

有候选但未启动时，检查连接、启用、授权、占用和依赖状态；不能直接归因为参数或旧快照。
Composite Flow 本身不占 Agent，它的 Agent 空白不能用于判定整条链失败。

## 名称、Pool、能力的职责

| 机制 | 描述什么 |
|---|---|
| 名称正则 | 用户明确要求的命名范围/机器白名单 |
| Agent Pool | 项目可使用的资源集合 |
| 能力 requirement | OS、runner、工具链等执行前提 |
| 同机 snapshot 关系 | 多个步骤对同一份本地状态的依赖 |

不需要特定名称时可优先用 Pool/能力表达策略；用户明确要求 `WinBuilder*` 时保留这一范围，
不要为消除“No agent”而擅自放宽到全部机器或启用被其他任务禁用的 Agent。
