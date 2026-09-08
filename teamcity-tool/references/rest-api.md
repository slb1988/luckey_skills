# TeamCity REST API Reference

Base URL: `http://<host>:8111/app/rest`

## Authentication

Use a Bearer token stored in `.env` at the project root:

```bash
TOKEN=$(grep TEAMCITY_TOKEN /d/Github/ObsidianVault/.env | cut -d= -f2)
```

Pass as header: `-H "Authorization: Bearer $TOKEN"`

## Content-Type / Accept rules

| Operation | Content-Type | Accept |
|---|---|---|
| GET (JSON) | — | `application/json` |
| PUT parameter (plain value) | `text/plain` | `text/plain` |
| POST build/cancel (XML body) | `application/xml` | `application/json` |

Using `Accept: application/json` with a `text/plain` PUT body returns HTTP 406. Always match Accept to the response format you want.

## Common queries

### Inspect a build
```bash
curl -s "http://192.168.2.13:8111/app/rest/builds/id:<ID>?fields=id,number,status,state,agent(name),buildType(id,name),triggered,properties(property)" \
  -H "Accept: application/json" -H "Authorization: Bearer $TOKEN"
```

### List queued builds
```bash
curl -s "http://192.168.2.13:8111/app/rest/buildQueue?fields=build(id,buildType(id),waitReason,properties(property))" \
  -H "Accept: application/json" -H "Authorization: Bearer $TOKEN"
```

### List running builds
```bash
curl -s "http://192.168.2.13:8111/app/rest/builds?locator=running:true&fields=build(id,buildType(id),agent(name),percentageComplete)" \
  -H "Accept: application/json" -H "Authorization: Bearer $TOKEN"
```

### List builds on a specific agent in a time window
Use this to rule out (or find) concurrent builds when diagnosing machine-level conflicts (e.g. UBT mutex):
```bash
curl -s "http://192.168.2.13:8111/app/rest/builds?locator=agent:(id:<AGENT_ID>),sinceDate:(yyyyMMdd'T'HHmmss%2B0800),untilDate:(yyyyMMdd'T'HHmmss%2B0800)&fields=build(id,number,buildType(id,name),startDate,finishDate,status)" \
  -H "Accept: application/json" -H "Authorization: Bearer $TOKEN"
```
Note: date format is `yyyyMMdd'T'HHmmssZ` with the timezone offset URL-encoded (`+0800` → `%2B0800`). Find the agent id via the "List all agents" query below.
Note: 该窗口 locator 实测**不包含「排队后从未启动就被取消」的构建**（即使其 startDate 字段显示为取消时刻）——重建事件线时对已取消构建要按 id 单独查。

### Find who canceled a build
`canceledInfo` 的 `user` 必须显式请求子字段，否则返回空 `{}`：
```bash
curl -s "http://192.168.2.13:8111/app/rest/builds/id:<ID>?fields=id,status,statusText,canceledInfo(timestamp,user(username,name))" \
  -H "Accept: application/json" -H "Authorization: Bearer $TOKEN"
```
后端不会 cancel 在途评审链（代码明示「不做 cancel 在途链」）——评审链出现 Canceled 一律是人工/TC 侧操作，用此查询定位操作者。

### List all agents
```bash
curl -s "http://192.168.2.13:8111/app/rest/agents?fields=agent(id,name,connected,enabled,authorized,build(id,buildType(id)))" \
  -H "Accept: application/json" -H "Authorization: Bearer $TOKEN"
```

### Compatible agents for a queued build
```bash
curl -s "http://192.168.2.13:8111/app/rest/agents?locator=compatible:(build:(id:<QUEUE_ID>))&fields=agent(id,name,connected,enabled,authorized)" \
  -H "Accept: application/json" -H "Authorization: Bearer $TOKEN"
```

### Get build config parameters
```bash
curl -s "http://192.168.2.13:8111/app/rest/buildTypes/id:<BT_ID>/parameters" \
  -H "Accept: application/json" -H "Authorization: Bearer $TOKEN"
```

### Get agent requirements
```bash
curl -s "http://192.168.2.13:8111/app/rest/buildTypes/id:<BT_ID>/agent-requirements" \
  -H "Accept: application/json" -H "Authorization: Bearer $TOKEN"
```

## Modifying build config parameters

### PUT (update or create) a parameter
```bash
curl -s -X PUT "http://192.168.2.13:8111/app/rest/buildTypes/id:<BT_ID>/parameters/<PARAM_NAME>" \
  -H "Content-Type: text/plain" -H "Accept: text/plain" \
  -H "Authorization: Bearer $TOKEN" \
  -d 'new-value'
```

### POST (add) a new parameter
```bash
curl -s -X POST "http://192.168.2.13:8111/app/rest/buildTypes/id:<BT_ID>/parameters" \
  -H "Content-Type: application/json" -H "Accept: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"name":"PARAM_NAME","value":"value"}'
```

## Users, groups and permissions

### Inspect auth settings (guest login, modules)
```bash
curl -s "http://192.168.2.13:8111/app/rest/server/authSettings" \
  -H "Accept: application/json" -H "Authorization: Bearer $TOKEN"
```
`allowGuest:false` = guest login disabled; `perProjectPermissions:true` = per-project roles enabled.

### List groups and a group's roles
```bash
curl -s "http://192.168.2.13:8111/app/rest/userGroups" \
  -H "Accept: application/json" -H "Authorization: Bearer $TOKEN"
curl -s "http://192.168.2.13:8111/app/rest/userGroups/key:<GROUP_KEY>/roles" \
  -H "Accept: application/json" -H "Authorization: Bearer $TOKEN"
```
Known groups on auto-server: `ADMIN`, `ADVANCED_USER`, `ALL_USERS_GROUP` (contains every user), `COMMON_USER` (查看+运行), `CREATE` (修改创建).

### Grant a role to a group (e.g. make project visible to all users)
```bash
curl -s -X POST "http://192.168.2.13:8111/app/rest/userGroups/key:ALL_USERS_GROUP/roles" \
  -H "Content-Type: application/xml" -H "Accept: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '<role roleId="PROJECT_VIEWER" scope="p:<PROJECT_ID>"/>'
```
Role ids: `PROJECT_VIEWER`, `PROJECT_DEVELOPER`, `PROJECT_ADMIN`, `AGENT_MANAGER`, `SYSTEM_ADMIN`. Scope `g` = global, `p:<PROJECT_ID>` = per project.

## Build queue management

### Cancel a queued or running build
```bash
curl -s -X POST "http://192.168.2.13:8111/app/rest/builds/id:<ID>" \
  -H "Content-Type: application/xml" -H "Accept: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '<buildCancelRequest comment="reason" readdIntoQueue="false"/>'
```

### Trigger a build
```bash
curl -s -X POST "http://192.168.2.13:8111/app/rest/buildQueue" \
  -H "Content-Type: application/xml" -H "Accept: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '<build><buildType id="<BT_ID>"/></build>'
```

## Chain 诊断与验证

完整顺序见 [build-chain-parameters.md](build-chain-parameters.md)，不要从“有候选但未启动”直接推断旧快照并取消构建。

- `buildTypes/.../agent-requirements` 是显式要求；隐式参数/runner 要求还需查具体 queued build 的 Compatible Agents 页面：
  `/viewQueued.html?itemId=<BUILD_ID>&tab=queuedBuildCompatibilityTab`（Web UI 路径，不在 `/app/rest` 下）。
- 递归读取每个实际 build 的 `snapshot-dependencies(build(id,buildType(id)))`，区分单节点兼容性和同机组交集。
- 任务实际启动后读取 `startProperties`；service message 改动再看 `resultingProperties`。只输出白名单字段并脱敏，不把排队状态的公式当成实际执行值。
- 核实实际 build 的 `versionedSettingsRevision(version)` 以及 `/projects/id:<PROJECT>/versionedSettings/status`，而不只看当前配置页。
- 临时 echo-only 链的 REST 创建/子资源设置、参数断言以及业务平台安全重排见上述参考。
