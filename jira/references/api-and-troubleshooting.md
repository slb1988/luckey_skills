# Jira API 与排障

## 环境变量

在调用项目根目录的 `.env` 中配置，不要把真实值写进 Skill：

```dotenv
JIRA_BASE_URL=https://jira.example.internal
JIRA_TOKEN=<personal-access-token>
JIRA_BOX_ID=ITER-33
```

认证头：

```http
Authorization: Bearer <JIRA_TOKEN>
Accept: application/json
```

脚本不会打印或缓存 Token。

## 使用的只读接口

| 目的 | 接口 |
|---|---|
| 验证身份和时区 | `GET /rest/api/2/myself` |
| 动态发现 Sprint、Rank、Start/End 字段 ID | `GET /rest/api/2/field` |
| 查询 Box 中当前用户任务 | `POST /rest/api/2/search` |
| 可选 Sprint 元数据 | Sprint 字段中的 ACTIVE 条目；必要时 `GET /rest/agile/1.0/sprint/{id}` |

BigPicture Box 通过 Jira 已注册的 JQL 函数查询：

```jql
issue in box("ITER-33") AND assignee = currentUser()
```

Box URL 中的 `ITER-33` 是稳定 ID；页面显示名（例如 SPxx）不一定是 Jira Sprint 名。Sprint JQL 名称通常又是另一套值，因此不要把三者互换。

## 已验证的坑

### 1. 不直接依赖 BigPicture SPA 私有接口

PAT 可以正常访问 Jira 核心 REST，但 `/rest/softwareplant-bigpicture/1.0/...` 在部分 Data Center/Server 组合下会返回插件内部 500。每日待办只需要 Box 范围，因此优先走 Jira 核心搜索接口和 `box()` JQL，避免抓 SPA、下载前端 chunk 或调用未公开私有接口。

### 2. `resolution is EMPTY` 不能代表未完成

此实例存在状态已经“完成”、resolution 仍为空的工单。始终用 `statusCategory.key` 判断完成态；JQL 过滤时用 `statusCategory != Done`。

### 3. 日期为空要如实报告

BigPicture 可能维护自己的排期，Jira 映射的 `Start date`、`End date`、`duedate` 也可能全为空。核心 API 查不到日期时，只能给出建议排期，并明确它不是 Jira 既有计划。

### 4. Sprint 历史是字符串数组

Jira Server 的 Sprint 字段常返回：

```text
com.atlassian.greenhopper.service.sprint.Sprint@[...id=21,name=Sprint 20,...state=ACTIVE...]
```

脚本解析 `id/name/state/startDate/endDate`，并以除当前 ACTIVE Sprint 外的历史数量估算跨 Sprint 次数。

### 5. URL 与首选网络入口

用户给出的 URL 主要用于提取 Box ID。只要 `.env` 已配置 `JIRA_BASE_URL`，脚本就优先使用该地址，不会被粘贴链接中的旧 host 覆盖。显式 `--base-url` 的优先级最高。

## 常见错误

### `JIRA_TOKEN is missing`

确认项目根 `.env` 存在非空 `JIRA_TOKEN`，或在当前进程环境中导出该变量。

### HTTP 401/403

- Token 失效、没有 Jira 浏览权限，或没有目标 Box 权限。
- 用 `/rest/api/2/myself` 单独验证；不要回显 Token。

### `box()` JQL 验证失败

- 优先使用 URL 中的 Box ID，而不是页面显示名。
- 确认 BigPicture 插件可用，且当前用户有 Box 浏览权限。
- 不要自动退化成“所有未完成任务”，否则会把个人历史 backlog 混入当前迭代。

### 当天缓存存在但用户要求最新状态

只有用户明确要求刷新时使用 `--refresh`。脚本覆盖同一缓存文件，并保留已记录的 `daily_plan` 中仍存在的工单 Key。

## 安全约束

- `assets/cache/` 只保存在本机并由 `.gitignore` 排除。
- 不把 `.env`、Token、Cookie、Authorization header 或缓存 JSON 打包进 Skill。
- 报错信息只包含 HTTP 状态、接口路径和 Jira 返回摘要，不包含认证头。
