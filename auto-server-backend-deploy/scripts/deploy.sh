#!/bin/bash
# ============================================================
# auto-server 一键更新部署脚本
# 用法: ./deploy.sh
# ============================================================
set -e

P4_USER="admin_sun"
P4_PORT="192.168.2.13:1666"
P4_CLIENT="auto-server"
export P4CHARSET=utf8
BACKEND_DIR="/data/py_automation/backend"
LOG_DIR="${BACKEND_DIR}/logs"
TMP_DIR="${BACKEND_DIR}/tmp"

cd "${BACKEND_DIR}"

echo "============================================"
echo "  auto-server 一键部署"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================"

# ---------- Step 1: P4 同步最新代码 ----------
echo ""
echo "[1/5] P4 同步代码..."
p4 -u "${P4_USER}" -p "${P4_PORT}" -c "${P4_CLIENT}" sync
echo "  -> 代码同步完成"

# ---------- Step 2: 停止服务 ----------
echo ""
echo "[2/5] 停止服务..."
if [ -f python3_pid.log ]; then
    PID=$(cat python3_pid.log)
    if kill -0 "${PID}" 2>/dev/null; then
        kill -9 "${PID}"
        echo "  -> 已停止进程 PID=${PID}"
    else
        echo "  -> 进程 PID=${PID} 已不存在"
    fi
else
    echo "  -> 未找到 PID 文件，跳过"
fi

# ---------- Step 3: 归档 flask 日志到 tmp/ ----------
echo ""
echo "[3/5] 归档 flask 日志到 tmp/..."
ARCHIVED_COUNT=0
for f in flask_*.log; do
    [ -f "$f" ] || continue
    mv "$f" "${TMP_DIR}/"
    ARCHIVED_COUNT=$((ARCHIVED_COUNT + 1))
done
echo "  -> 已归档 ${ARCHIVED_COUNT} 个 flask 日志"

# ---------- Step 4: 轮转 app.log（自动递增序号，不覆盖） ----------
echo ""
echo "[4/5] 轮转 app.log..."
if [ -f "${LOG_DIR}/app.log" ] && [ -s "${LOG_DIR}/app.log" ]; then
    # 找到下一个可用序号
    NEXT=1
    while [ -f "${LOG_DIR}/app.log.${NEXT}" ]; do
        NEXT=$((NEXT + 1))
    done
    mv "${LOG_DIR}/app.log" "${LOG_DIR}/app.log.${NEXT}"
    echo "  -> app.log -> app.log.${NEXT}"
else
    echo "  -> app.log 为空或不存在，跳过轮转"
fi

# ---------- Step 5: 启动服务 ----------
echo ""
echo "[5/5] 启动服务..."
source ./venv/bin/activate
nohup python3 manage.py runserver --host 0.0.0.0 --port 5000 >> flask_$(echo $$).log 2>&1 &
NEW_PID=$!
echo "${NEW_PID}" > python3_pid.log
echo "  -> 服务已启动  PID=${NEW_PID}"
echo "  -> flask 日志: flask_${NEW_PID}.log"
echo "  -> app 日志:   logs/app.log"

echo ""
echo "============================================"
echo "  部署完成!"
echo "============================================"
