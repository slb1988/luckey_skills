---
name: auto-server-backend-deploy
description: Deploy the auto-server Flask backend on dev@auto-server. Syncs latest code from Perforce, stops old service, archives logs, rotates app.log, and starts the service. Use when publishing or deploying the py_automation backend.
---

# Auto-Server Backend Deploy

## 概述

在 `auto-server` 本地部署 py_automation Flask 后端。**pi 本身就运行在 auto-server 上**（`auto-server` 解析到 `127.0.1.1`），无需 SSH，直接用 bash 执行本地命令即可。

## 快速开始

```bash
# 仅后端（depot 版，内置 /server_status/busy 空闲等待；FORCE_DEPLOY=1 跳过等待）：
cd /data/py_automation/backend && ./deploy.sh

# 全栈（前端 + 后端，后端段同样走上面的 depot 版脚本）：
/home/dev/.pi/skills/auto-server-deploy/scripts/deploy.sh
```

## 部署步骤

| 步骤 | 操作 | 说明 |
|------|------|------|
| 1 | P4 同步代码 | `export P4CHARSET=utf8 && p4 -u admin_sun -p 192.168.2.13:1666 -c auto-server sync` |
| 2 | 等待空闲 | 轮询 `GET /server_status/busy`，连续 2 次空闲才继续，上限 5 分钟；超时交互确认（非交互放弃）；`FORCE_DEPLOY=1` 跳过 |
| 3 | 停止服务 | 用 `pgrep -f "manage.py runserver"` 找到真实 PID 后 kill（**不能用 `python3_pid.log`，见下方陷阱**） |
| 4 | 归档 flask 日志 | `mv flask_*.log ./tmp/` |
| 5 | 轮转 app.log | `mv logs/app.log logs/app.log.{N}`（自动递增序号，永不覆盖） |
| 6 | 启动服务 + 修正 PID | 启动后用 `pgrep -f "manage.py runserver"` 获取真实 python PID 写入 `python3_pid.log` |

## P4 配置

| 参数 | 值 |
|------|-----|
| 用户 | `admin_sun` |
| 服务器 | `192.168.2.13:1666` |
| 客户端 | `auto-server` |
| 字符集 | `utf8`（**必须**，服务器为 Unicode 模式） |
| 本地路径 | `/data/py_automation/backend` |

## 日志管理

### 两类日志

| 日志 | 路径 | 描述 |
|------|------|------|
| Flask 进程日志 | `flask_{PID}.log`（根目录） | Flask stdout/stderr，nohup 重定向 |
| App 应用日志 | `logs/app.log` | 应用程序写入的业务日志 |

### 日志生命周期

```
每次部署:
  flask_{PID}.log     →  mv 到 tmp/            （归档保留）
  logs/app.log        →  logs/app.log.{N}       （轮转，N 自动递增不覆盖）

当前运行:
  flask_{新PID}.log    ←  nohup 输出
  logs/app.log         ← 应用日志（新建）
```

### app.log 轮转规则

- `logs/app.log` → `logs/app.log.1`、`app.log.2`、`app.log.3` ... 依次递增
- 每次部署自动找下一个可用序号 `N = max(已有序号) + 1`
- **永不覆盖**旧日志，可无限追溯历史部署
- 当前 `app.log` 为空时不轮转

### flask 日志归档

- 所有根目录 `flask_*.log` 移动到 `tmp/`
- 按 PID 命名区分实例
- `tmp/` 保留所有历史日志，需手动清理

## 目录结构

```
/data/py_automation/backend/
├── kill.sh             ← 单独停服脚本
├── start.sh            ← 单独启动脚本
├── manage.py           ← Flask 入口
├── venv/               ← Python 虚拟环境
├── python3_pid.log     ← 当前进程 PID
├── flask_{PID}.log     ← 当前运行的 flask stdout/stderr
├── logs/
│   ├── app.log         ← 当前应用日志
│   ├── app.log.1       ← 历史应用日志 #1
│   └── ...
└── tmp/
    └── flask_*.log     ← 归档的历史 flask 日志
```

> 一键部署脚本：`/home/dev/.pi/skills/auto-server-deploy/scripts/deploy.sh`

## 手动部署（不使用脚本时）

```bash
cd /data/py_automation/backend

# 1. 同步（必须设置 P4CHARSET）
export P4CHARSET=utf8
p4 -u admin_sun -p 192.168.2.13:1666 -c auto-server sync

# 1.5 等待空闲（避免切到在途任务；确认风险后可跳过直接进 2）：
for i in $(seq 1 30); do
    curl -s --max-time 5 http://127.0.0.1:5000/server_status/busy | grep -q '"busy": *false' && break
    echo "等待服务器空闲... ($i)"
    sleep 10
done

# 2. 停服（用 pgrep 找真实 PID，不要依赖 python3_pid.log）
REAL_PID=$(pgrep -f "manage.py runserver")
if [ -n "$REAL_PID" ]; then
    kill -9 $REAL_PID
fi

# 3. 归档 flask 日志
mv flask_*.log ./tmp/ 2>/dev/null

# 4. 轮转 app.log
if [ -f logs/app.log ] && [ -s logs/app.log ]; then
    N=1
    while [ -f "logs/app.log.$N" ]; do N=$((N+1)); done
    mv logs/app.log "logs/app.log.$N"
fi

# 5. 启动并修正 PID
source ./venv/bin/activate
nohup python3 manage.py runserver --host 0.0.0.0 --port 5000 >> flask_$$.log 2>&1 &
sleep 2  # 等待子进程就绪
# 获取真实 python 进程 PID（nohup 包装进程会立即退出）
pgrep -f "manage.py runserver" > python3_pid.log
```

## 部署后验证

```bash
cd /data/py_automation/backend

# 获取真实 PID 再验证（python3_pid.log 可能过期）
REAL_PID=$(pgrep -f "manage.py runserver")
if [ -n "$REAL_PID" ]; then
    echo "$REAL_PID" > python3_pid.log
    echo "后端 PID: $REAL_PID"
    curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:5000/
else
    echo "❌ 后端未运行"
fi
```

## 常见陷阱

### 陷阱 0：飞书 AI 助手找不到 pi（PATH 被 /etc/environment 覆盖）

**现象**：飞书机器人报 pi 启动失败，`.logs/feishu.log` 里有 `{"stage": "pi_failed", "error": "pi 启动失败: [Errno 2] No such file or directory: 'pi'"}`。

**根因**：deploy.sh source `/etc/environment` 时其 `PATH=` 会整体覆盖当前 PATH，脚本只补回了 npm-global，没补 pnpm（pi 装在 `$HOME/.local/share/pnpm/`）→ 后端进程 fork 子进程时找不到 `pi`。

**已修复（2026-08-29，三保险）**：
1. `/etc/environment` 的 `PATH=` 已直接包含 `/home/dev/.local/share/pnpm` 和 `/home/dev/.npm-global/bin`（根治，备份在 `/etc/environment.bak.20260829`）
2. `auto-server-deploy/scripts/deploy.sh` 在 source /etc/environment 后追加 `export PATH="$HOME/.local/share/pnpm:$PATH"` 和 `export FEISHU_ASSISTANT_PI_BIN=$HOME/.local/share/pnpm/pi`（冗余保险）
3. `/etc/environment` 里写入了 `FEISHU_ASSISTANT_PI_BIN=/home/dev/.local/share/pnpm/pi`（绝对路径兜底，deploy.sh 每次 source 自动带上）

**排查命令**：
```bash
PID=$(pgrep -f "manage.py runserver" | head -1)
tr '\0' '\n' < /proc/$PID/environ | grep -E '^(PATH|FEISHU_ASSISTANT_PI_BIN)='
grep '"pi_failed"' /data/py_automation/backend/.logs/feishu.log | tail -3
```

⚠️ 仓库里的 `/data/py_automation/backend/start.sh` 未修（只加了 npm-global），手动 `./start.sh` 启动仍会踩坑——但 `/etc/environment` 的绝对路径兜底对 start.sh 不生效（它不 source /etc/environment），建议后续把仓库 start.sh 也补上同样两行。

### 陷阱 1：不需要 SSH

`auto-server` 解析到 `127.0.1.1`，pi 本身就运行在这台机器上。直接使用 `bash` 工具执行本地命令，**不要尝试 SSH**（`ssh dev@auto-server` 会因密钥问题失败）。

### 陷阱 2：PID 文件不可靠（关键）

`start.sh` / `deploy.sh` 中的 `nohup ... & echo $! > python3_pid.log` **写入的是 nohup 包装进程的 PID，不是 python3 的 PID**。

原因：
1. `$!` 获取的是 nohup 包装进程（bash 子进程）的 PID
2. nohup 包装进程 exec python3 后立即退出
3. python3 获得一个新 PID（子进程）
4. `python3_pid.log` 里存的是已退出的包装进程 PID，`kill -0` 检验失败

**正确做法**：每次启动后、验证前，用 `pgrep -f "manage.py runserver"` 获取真实 PID 并覆盖 `python3_pid.log`。

### 陷阱 3：bash -c 包裹时 $$ 和 $! 都会变化

通过 pi 的 `bash` 工具执行命令时，`bash -c "..."` 会额外包裹一层。此时：
- `$$` = bash -c 进程的 PID（不是 python 的）
- `$!` = nohup 包装进程 PID（也不是 python 的）

flask 日志文件名用了 `$$`，所以日志文件和实际 python PID 不对应。这不影响功能（stdout/stderr 重定向正确），但不要用日志文件名中的 PID 去验证进程。

### 陷阱 4：停服不要只读 python3_pid.log

`kill.sh` 脚本直接 `kill -9 $(cat python3_pid.log)`，如果 PID 文件过期则会 kill 失败或误杀。

**安全做法**：用 `pgrep -f "manage.py runserver"` 找出真实 Python 进程后再 kill，同时处理旧 PID 文件中残留的无关进程。

### 陷阱 5：部署 kill 撞车 AI review 代提交窗口 → CL 署名 AutoServer、review 永久卡 approved

AI review 的代提交**不是原子的**。approve 落库后 `_trigger_auto_submit` → `submit_shelved_cl` 依次执行：

1. `p4 change -f -U AutoServer <shelved_cl>`（署名改成服务账号，P4 trigger 回调走服务账号 bypass）
2. `p4 submit -e`（服务端直落 shelf 内容，**不经 workspace 重写**；CL rename 为新号，此时署名=AutoServer）
3. `p4 change -f` 恢复作者署名 + DB 推进（`status=submitted`、写新 CL 号、补 `cl_submitted` 活动）

**步骤 2→3 之间有秒级窗口**。deploy.sh / kill.sh 的 `kill -9` 若命中此窗口（真实案例：CL 128399，2026-09-02，部署一个改 ai_review 代码的 CL 时撞车），步骤 3 全部丢失 → CL 永久署名 AutoServer、review 永久卡 `approved + 旧 shelved CL 号`。被杀进程无 Traceback、无 shutdown 日志，排查时"日志突然中断 + 进程号变了"就是外部 kill，别误判成代码异常。

**不会自愈也不会被误打回**：`submit_retry_sweep` 只重试已有失败活动（n>0）的 review，n==0 直接 `continue`。

- **预防**：部署前确认没有刚 approve 的 review（代提交在 approve 后秒级触发），改 ai_review 相关代码时尤其注意。
- **修复**：`p4 change -f <new_cl>` 把 User 改回作者（需 super）；生产库 SQL 把 review 行改为 `cl=<new_cl>, cl_type='submitted', status='submitted'` 并补一条 `cl_submitted` 活动。
- **识别类似事故**：CL 提交人是 AutoServer 但内容不像平台行为 → 基本是步骤 3 丢失；"CL 描述与文件清单不符 / BOM 被改"则通常是作者 shelve 时打的大包，`submit -e` 原样落 shelf 内容，平台不做合并或裁剪。

## 注意事项

<memory category="troubleshooting">
**deploy.sh 双脚本分叉（2026-09-04 已修复）**：等待空闲机制 `wait_for_idle`（轮询 `/server_status/busy`，连续 2 次空闲才 kill，上限 5 分钟）CL 1427（2026-09-03）起只进了 depot 版 `/data/py_automation/backend/deploy.sh`；skill 版 `~/.pi/skills/auto-server-deploy/scripts/deploy.sh` 曾长期没有（停留 08-29 版），而两份 SKILL.md 快速开始都指向它 → 按 skill 文档部署 = 绕过等待保护直接 kill -9。2026-09-04 起 skill 版后端段改为委托 depot 版执行，分叉消除。busy 语义注意：AI review 进 `await_compile` 后构建跑在 TeamCity 上，服务器侧只是 DB 状态，busy 判空闲是**正确的**，重启无损（新进程会正常收 `tc_callback` 续跑）。机制细节与残留缺陷（TOCTOU 窗口、PID 文件捷径）见 [references/deploy-wait-for-idle.md](references/deploy-wait-for-idle.md)。
</memory>

- **P4 字符集**：服务器为 Unicode 模式，必须设置 `P4CHARSET=utf8`，否则 sync 会失败
- **环境**：直接本地执行，不需要 SSH
- **PID**：`python3_pid.log` 写入不可靠，每次部署后/验证前必须用 `pgrep -f "manage.py runserver"` 修正
- `app.log` 序号自动递增，旧日志不会被覆盖
- `tmp/` 目录需定期手动清理
- 如果 P4 无更新，sync 输出 `File(s) up-to-date.`，不影响后续步骤
