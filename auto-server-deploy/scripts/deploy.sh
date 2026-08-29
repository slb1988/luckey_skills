#!/bin/bash
# ============================================================
# auto-server 全栈一键部署脚本（前端 + 后端）
# 用法: ./deploy.sh
# ============================================================
set -e

P4_USER="admin_sun"
P4_PORT="192.168.2.13:1666"
P4_CLIENT="auto-server"
export P4CHARSET=utf8

BACKEND_DIR="/data/py_automation/backend"
FRONTEND_DIR="/data/py_automation/frontend"
LOG_DIR="${BACKEND_DIR}/logs"
TMP_DIR="${BACKEND_DIR}/tmp"

echo "============================================"
echo "  auto-server 全栈部署 (前端 + 后端)"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================"

# ========== 后端 ==========
echo ""
echo "========== 后端部署 =========="

# --- Step B1: P4 同步后端代码 ---
echo ""
echo "[后端 1/5] P4 同步代码..."
cd "${BACKEND_DIR}"
p4 -u "${P4_USER}" -p "${P4_PORT}" -c "${P4_CLIENT}" sync
echo "  -> 后端代码同步完成"

# --- Step B2: 停止服务 ---
echo ""
echo "[后端 2/5] 停止服务..."
PORT=5000

PIDS_TO_KILL=()

# 来源1（精准）: 端口 5000 上所有 python 进程
# ss -tlnp 输出格式: ... users:(("python3",pid=12345,fd=13))
PORT_PIDS=$(ss -tlnp 2>/dev/null | grep ":${PORT}\b" | grep -oP 'pid=\K\d+' | sort -nu)
if [ -n "${PORT_PIDS}" ]; then
    for p in ${PORT_PIDS}; do
        # 确认是 python 进程才加入
        if ps -p "$p" -o comm= 2>/dev/null | grep -qi python; then
            PIDS_TO_KILL+=("$p")
        else
            echo "  -> 跳过非 python 进程 PID=${p}（$(ps -p "$p" -o comm= 2>/dev/null)）"
        fi
    done
fi

# 来源2（兜底）: manage.py / flask runserver 进程（含 reloader 子进程）
MANAGE_PIDS=$(pgrep -af "manage.py runserver|flask run" 2>/dev/null | grep -v pgrep | awk '{print $1}' || true)
if [ -n "${MANAGE_PIDS}" ]; then
    for p in ${MANAGE_PIDS}; do
        PIDS_TO_KILL+=("$p")
    done
fi

# 去重 + 逐个杀
if [ ${#PIDS_TO_KILL[@]} -gt 0 ]; then
    PIDS_TO_KILL=($(printf '%s\n' "${PIDS_TO_KILL[@]}" | sort -nu))
    echo "  -> 发现 ${#PIDS_TO_KILL[@]} 个待杀进程: ${PIDS_TO_KILL[*]}"
    for pid in "${PIDS_TO_KILL[@]}"; do
        if kill -0 "${pid}" 2>/dev/null; then
            CMD=$(ps -p "${pid}" -o args= 2>/dev/null | head -c 100)
            kill -9 "${pid}" 2>/dev/null && echo "  -> 已杀死 PID=${pid}  (${CMD})" || echo "  -> 无法杀死 PID=${pid}"
        else
            echo "  -> PID=${pid} 已不存在，跳过"
        fi
    done
else
    echo "  -> 未发现任何运行中的进程"
fi

# 最终验证：端口必须释放 + 无残留 python 进程
sleep 2
STILL_ON_PORT=$(ss -tlnp 2>/dev/null | grep ":${PORT}\b" | grep -oP 'pid=\K\d+' || true)
if [ -n "${STILL_ON_PORT}" ]; then
    echo "  -> ⚠️ 端口 ${PORT} 仍被占用(PID=${STILL_ON_PORT})，强制 fuser -k..."
    fuser -k ${PORT}/tcp 2>/dev/null || true
    sleep 1
    if ss -tlnp 2>/dev/null | grep -q ":${PORT}\b"; then
        echo "  -> ❌ 无法释放端口 ${PORT}，请手动检查"
        exit 1
    fi
fi

# 二次确认：无残留 manage.py/flask python 进程
REMAIN=$(pgrep -af "manage.py runserver|flask run" 2>/dev/null | grep -v pgrep || true)
if [ -n "${REMAIN}" ]; then
    echo "  -> ❌ 仍有残留进程:\n${REMAIN}"
    exit 1
fi
echo "  -> ✅ 端口 ${PORT} 已关闭，无残留 python 进程"

# --- Step B3: 归档 flask 日志 ---
echo ""
echo "[后端 3/5] 归档 flask 日志到 tmp/..."
ARCHIVED_COUNT=0
for f in flask_*.log; do
    [ -f "$f" ] || continue
    mv "$f" "${TMP_DIR}/"
    ARCHIVED_COUNT=$((ARCHIVED_COUNT + 1))
done
echo "  -> 已归档 ${ARCHIVED_COUNT} 个 flask 日志"

# --- Step B4: 轮转 app.log ---
echo ""
echo "[后端 4/5] 轮转 app.log..."
if [ -f "${LOG_DIR}/app.log" ] && [ -s "${LOG_DIR}/app.log" ]; then
    NEXT=1
    while [ -f "${LOG_DIR}/app.log.${NEXT}" ]; do
        NEXT=$((NEXT + 1))
    done
    mv "${LOG_DIR}/app.log" "${LOG_DIR}/app.log.${NEXT}"
    echo "  -> app.log -> app.log.${NEXT}"
else
    echo "  -> app.log 为空或不存在，跳过轮转"
fi

# --- Step B5: 启动服务 ---
echo ""
echo "[后端 5/5] 启动服务..."

# ---- 系统环境变量（来源：/etc/environment，PAM 登录时载入；此处显式 source 兜底） ----
# JWT_SECRET / LDAP_BIND_DN / LDAP_BIND_PASSWORD / AI_REVIEW_P4USER / AI_REVIEW_P4PASSWD
# 均存于系统级 /etc/environment，不再在本脚本硬编码（避免密钥裸露在部署脚本）。
# 每次启动都 source（幂等）：PAM 已载入则重复赋值无害，未载入（cron/非登录 shell）也能取到。
# 轮换凭据时只改 /etc/environment 即可。
# ⚠️ 必须先于 venv activate：/etc/environment 里的 PATH= 会覆盖当前 PATH，若在其后
#    source 会丢掉 venv 的 bin → 系统 python3 缺 flask_migrate。
[ -f /etc/environment ] && set -a && . /etc/environment && set +a

# lark-cli 安装在 npm-global，Flask 进程需要能在 PATH 中找到它
# （/etc/environment 的 PATH 不含 npm-global，必须在 source 之后追加）
export PATH="$HOME/.npm-global/bin:$PATH"

# pi (coding agent) 安装在 pnpm 全局目录，飞书 AI 助手通过它 fork 子进程
# （/etc/environment 的 PATH 不含 pnpm，必须在 source 之后追加；
#   同时用 FEISHU_ASSISTANT_PI_BIN 绝对路径兜底，防 PATH 漂移）
export PATH="$HOME/.local/share/pnpm:$PATH"
export FEISHU_ASSISTANT_PI_BIN="${FEISHU_ASSISTANT_PI_BIN:-$HOME/.local/share/pnpm/pi}"

# 激活 venv（放在 /etc/environment 之后，其 activate 会在现有 PATH 前追加 venv/bin）
source ./venv/bin/activate

nohup python3 manage.py runserver --host 0.0.0.0 --port 5000 >> flask_$(echo $$).log 2>&1 &
NEW_PID=$!
echo "${NEW_PID}" > python3_pid.log
echo "  -> 服务已启动  PID=${NEW_PID}"
echo "  -> flask 日志: flask_${NEW_PID}.log"
echo "  -> app 日志:   logs/app.log"

# ========== 前端 ==========
echo ""
echo "========== 前端部署 =========="

# --- Step F1: P4 同步前端代码 ---
echo ""
echo "[前端 1/2] P4 同步代码..."
cd "${FRONTEND_DIR}"
p4 -u "${P4_USER}" -p "${P4_PORT}" -c "${P4_CLIENT}" sync
echo "  -> 前端代码同步完成"

# --- Step F2: 构建前端 ---
echo ""
echo "[前端 2/2] npm run build..."
npm run build
echo "  -> 前端构建完成"

# ========== 验证 ==========
echo ""
echo "============================================"
echo "  全栈部署完成!"
echo "============================================"

echo ""
echo "--- 验证后端 ---"
sleep 2
BACKEND_PID=$(cat "${BACKEND_DIR}/python3_pid.log")
if kill -0 "${BACKEND_PID}" 2>/dev/null; then
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/)
    echo "  后端 PID: ${BACKEND_PID}  |  HTTP: ${HTTP_CODE}"
else
    echo "  ❌ 后端进程未运行!"
fi

echo "  前端 dist: ${FRONTEND_DIR}/dist/"
if [ -d "${FRONTEND_DIR}/dist" ]; then
    echo "  ✅ 前端构建产物已就绪"
else
    echo "  ❌ 前端构建产物不存在!"
fi
