---
name: auto-server-deploy
description: Full-stack deploy of the auto-server frontend and backend on dev@auto-server. Syncs both from Perforce, builds the frontend, and restarts the backend with full log rotation. Use when publishing both frontend and backend together.
---

# Auto-Server Full-Stack Deploy

## 概述

在 `dev@auto-server` 上一键部署 auto-server **前端 + 后端**。先部署后端（同步→停服→归档→轮转→启动），再部署前端（同步→构建），最后自动验证。

## 快速开始

```bash
/home/dev/.pi/skills/auto-server-deploy/scripts/deploy.sh
```

## 部署流程

### 后端（5 步）

| 步骤 | 操作 | 说明 |
|------|------|------|
| B1 | P4 同步 | `export P4CHARSET=utf8 && p4 sync` |
| B2 | 停止服务 | ss -tlnp 精准抓取 5000 端口 python PID → pgrep manage.py/flask 兜底 → 去重 → 逐个 kill -9 并记录命令行 → 端口 + 进程双重验证 |
| B3 | 归档日志 | `mv flask_*.log ./tmp/` |
| B4 | 轮转 app.log | `mv logs/app.log logs/app.log.{N}`（自动递增） |
| B5 | 启动服务 | `nohup python3 manage.py runserver --host 0.0.0.0 --port 5000 &` |

### 前端（2 步）

| 步骤 | 操作 | 说明 |
|------|------|------|
| F1 | P4 同步 | `export P4CHARSET=utf8 && p4 sync` |
| F2 | 构建 | `npm run build` |

## P4 配置

| 参数 | 值 |
|------|-----|
| 用户 | `admin_sun` |
| 服务器 | `192.168.2.13:1666` |
| 客户端 | `auto-server` |
| 字符集 | `utf8`（**必须**，Unicode 服务器） |

## 注册自定义环境变量（防 p4 覆盖）

后端进程需要自定义环境变量时（如 AI Review 的独立 P4 账号），**必须写在本 skill 的 `scripts/deploy.sh` B5 启动前**，不能写进后端工作区：

| 位置 | p4 sync 是否覆盖 | 原因 |
|------|------------------|------|
| `~/.pi/skills/auto-server-deploy/scripts/deploy.sh` | 永不 ✅ | 在 client view（`//depot/pyAutomation/... → /data/py_automation/...`）之外 |
| backend 工作区 `start.sh` / `deploy.sh` / `setup_env.sh` | 会覆盖 ❌ | 均为 depot 文件，sync 还原 |
| backend `server/config/*.py` | 会覆盖 ❌ | 全部在 depot 中 |

> 已注册实例：B5 启动前 `export AI_REVIEW_P4USER=AutoServer AI_REVIEW_P4PASSWD=...`（AI Review 专用账号与业务 P4 账号 CyanCookCI 分离）。
> `p4 sync` 会跳过本工作区 opened-for-edit 的文件——本地打开未提交的修改不会被覆盖。

## 配置选择与 AI_REVIEW 环境变量链

`server/__init__.py` 按环境变量 `Env` 选择配置类：

| Env | 配置类 | P4 默认 |
|-----|--------|---------|
| 未设置 / dev | DevConfig | `P4PORT=''`（P4 功能不可用） |
| `prod` | ProdConfig | `P4PORT=192.168.2.236:1666`、`P4USER=CyanCookCI` |

- **`Env=prod` 来自 `~/.bashrc`，不在 deploy.sh 里**。若在未继承 bashrc 的 shell（cron 等）里跑部署，后端会静默回落到 DevConfig → P4 全不可用。
- `config/base.py` 用 `os.getenv` 读 `AI_REVIEW_P4PORT/P4USER/P4PASSWD/P4CLIENT`（空值回落默认）；`ai_review/vcs/p4_adapter.py` 自动提交路径取值链为 `AI_REVIEW_P4PORT or P4PORT`。

## 日志管理（后端）

| 操作 | 说明 |
|------|------|
| flask 日志归档 | `flask_{PID}.log` → `tmp/` |
| app.log 轮转 | `logs/app.log` → `logs/app.log.{N}`（N 自动递增，永不覆盖） |

## 目录结构

```
/data/py_automation/
├── backend/               ← Flask 后端
│   ├── manage.py
│   ├── venv/
│   ├── python3_pid.log
│   ├── flask_{PID}.log
│   ├── logs/
│   │   ├── app.log
│   │   └── app.log.{N}
│   └── tmp/
│       └── flask_*.log
└── frontend/              ← Vite 前端
    ├── package.json
    └── dist/              ← 构建产物
```

## 部署后验证

脚本会自动输出：

```
--- 验证后端 ---
  后端 PID: 1234567  |  HTTP: 200
  前端 dist: /data/py_automation/frontend/dist/
  ✅ 前端构建产物已就绪
```

也可手动验证：

```bash
# 后端
curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/

# 前端
ls /data/py_automation/frontend/dist/
```

## 停服原理

### Flask debug 进程模型

```
nohup python3 manage.py runserver &
    │
    ├── PID_A  (nohup wrapper) ── exec python3 ── 立即退出
    ├── PID_B  (Flask reloader, 监控文件变更)
    └── PID_C  (Flask worker, 实际监听 :5000)
```

Flask 以 debug/reloader 模式运行时 fork 出两个 python 进程：reloader 父进程监控文件、worker 子进程绑定端口。`$!` 捕获的是 nohup 包装壳 PID（已退出），写入 `python3_pid.log` 的 PID 与实际 worker PID 无对应关系。

### 为什么不能用 PID 文件停服

| 陷阱 | 现象 | 根源 |
|------|------|------|
| nohup 包装壳 | `python3_pid.log` 存的是已退出 PID | `$!` 返回 nohup fork 的 bash 子进程，非 python |
| reloader 子进程 | 杀 reloader 父进程后 worker 变孤儿继续占端口 | Flask 给 worker 设了独立进程组 |
| 手动重启 | PID 文件过期，实际进程 PID 完全不同 | 人工 `nohup python3 ... &` 不更新 PID 文件 |

### 正确的停服锚点：端口

**端口是唯一真相来源**。不管进程树多复杂、PID 文件多过期，`ss -tlnp` 直接从内核 socket 表读出谁在 listen :5000。

| 来源 | 命令 | 作用 |
|------|------|------|
| 端口精准抓取 | `ss -tlnp \| grep :5000 \| grep -oP 'pid=\K\d+'` | 从内核确认谁在占用端口 |
| 语言过滤 | `ps -p $pid -o comm= \| grep -qi python` | 排除非 python 进程误杀 |
| 进程树兜底 | `pgrep -af "manage.py runserver\|flask run"` | 覆盖改了端口或未绑定成功的进程 |

> `pgrep -f "manage.py"` 不可用——会匹配 `vim manage.py`、`cat manage.py` 等非 python 进程。必须用 `manage.py runserver` 锁定命令行。

## 注意事项

- **P4 字符集**：必须设置 `P4CHARSET=utf8`，服务器为 Unicode 模式
- 部署顺序：先停后端 → 部署后端 → 部署前端，减少停机时间
- 如果 P4 无更新，sync 输出 `File(s) up-to-date.`，不影响后续步骤
- `tmp/` 目录需定期手动清理历史 flask 日志
