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
