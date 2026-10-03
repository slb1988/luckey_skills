---
name: auto-server-frontend-deploy
description: Sync auto-server frontend code from Perforce and build for deployment. Use when publishing or deploying the auto-server frontend on dev@auto-server.
---

# Auto-Server Frontend Deploy

共性知识：[pyauto-shared](../pyauto-shared/SKILL.md)。先确认实际执行主机；下述“本机”仅指 auto-server 运行时，不是对当前会话位置的断言。

## Overview

发布 auto-server **前端**项目。从 Perforce 同步最新代码并构建。

## 使用方式

执行前用 `hostname`、`whoami`、`pwd` 核实当前是 `dev@auto-server`，并确认目标目录 `/data/py_automation/frontend`。仅在确认后的目标会话执行以下命令；异机先路由到 auto-server 运行时，无法确认则停止。主机别名或回环地址解析不是现场证明。

### 1. 同步代码 (Perforce)

从 P4 仓库拉取最新代码：

```bash
cd /data/py_automation/frontend && P4CHARSET=utf8 p4 -u admin_sun -p 192.168.2.13:1666 -c auto-server sync
```

- **用户**: `admin_sun`
- **P4 端口**: `192.168.2.13:1666`
- **客户端 (workspace)**: `auto-server`
- **工作目录**: `/data/py_automation/frontend`

### 2. 构建前端

```bash
cd /data/py_automation/frontend && npm run build
```

构建成功只说明产物就绪；完成下面的发布验证后才能声称线上生效。

## 发布验证与回执

- 核对 `npm run build` 退出码为 0，且目标目录的 `dist/index.html` 与其引用的资源确实存在。
- 按目标机实际 nginx 静态目录配置核对产物服务位置，再访问已确认的前端 URL，核验返回的首页/资源版本与本次产物一致；不要把后端健康检查当成前端生效证据。
- 回报执行主机、目录、同步结果/版本、构建结果、产物路径和访问验证结果。未完成访问核验时写“构建完成，线上生效未验证”，不要只返回“已发布”。

## AI Review Markdown 渲染

<memory category="common-patterns">
AI Review 的标题、评论和编译分析是分散在 `ReviewDetail.vue`、`components/CommentBubble.vue`
与 `components/AISummaryPanel.vue` 的独立展示面，但 Markdown 链接策略统一放在
`src/views/ai_review/markdown.ts`。新增展示面时应复用该入口；`[label](url)` 必须渲染为
带 `target="_blank"` 和安全 `rel` 的 `<a>`，避免 Jira 等外链覆盖当前 review 页面。
</memory>

## 注意事项

- 只在已核实的 `dev@auto-server` 会话执行；不要假定当前机器就是目标机
- **必须设置 `P4CHARSET=utf8`**，否则 P4 服务器会报 `Unicode server permits only unicode enabled clients` 导致同步静默失败
- 确保 P4 用户 `admin_sun` 有权限访问仓库
- 确保 Node.js 和 npm 依赖已安装（如未安装需先执行 `npm install`）
- 同步后务必重新 `npm run build`，代码更新不等于前端生效
