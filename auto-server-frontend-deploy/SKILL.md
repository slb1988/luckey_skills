---
name: auto-server-frontend-deploy
description: Sync auto-server frontend code from Perforce and build for deployment. Use when publishing or deploying the auto-server frontend on dev@auto-server.
---

# Auto-Server Frontend Deploy

## Overview

发布 auto-server **前端**项目。从 Perforce 同步最新代码并构建。

## 使用方式

在 `dev@auto-server` 上执行以下命令：

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

构建产物生成后即可完成前端发布。

## 注意事项

- 确保在 `dev@auto-server` 主机上执行（当前机器就是 auto-server，直接本地执行即可）
- **必须设置 `P4CHARSET=utf8`**，否则 P4 服务器会报 `Unicode server permits only unicode enabled clients` 导致同步静默失败
- 确保 P4 用户 `admin_sun` 有权限访问仓库
- 确保 Node.js 和 npm 依赖已安装（如未安装需先执行 `npm install`）
- 同步后务必重新 `npm run build`，代码更新不等于前端生效
