#!/bin/bash
# ============================================================
# auto-server 全栈一键部署脚本（前端 + 后端）
# 用法: ./deploy.sh
#       FORCE_DEPLOY=1 ./deploy.sh   # 跳过空闲检测（确认风险后强制）
#
# 后端段自 2026-09-04 起整体委托 depot 版脚本执行：
#   /data/py_automation/backend/deploy.sh
# （P4 同步 → /server_status/busy 空闲等待 → 停服 → 日志归档/轮转 → 启动），
# 本脚本不再自行 kill -9，消除「skill 版无等待保护」的双脚本分叉。
# ============================================================
set -e

P4_USER="admin_sun"
P4_PORT="192.168.2.13:1666"
P4_CLIENT="auto-server"
export P4CHARSET=utf8

BACKEND_DIR="/data/py_automation/backend"
FRONTEND_DIR="/data/py_automation/frontend"
BACKEND_DEPLOY="${BACKEND_DIR}/deploy.sh"

echo "============================================"
echo "  auto-server 全栈部署 (前端 + 后端)"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================"

# ---- 环境变量（必须先于后端子脚本调用，使其继承；前端构建同用） ----
# JWT_SECRET / LDAP_BIND_DN / LDAP_BIND_PASSWORD / AI_REVIEW_P4USER / AI_REVIEW_P4PASSWD
# 均存于系统级 /etc/environment（PAM 登录时载入；此处显式 source 兜底：
# cron/非登录 shell 也能取到）。轮换凭据时只改 /etc/environment 即可。
# ⚠️ /etc/environment 的 PATH= 会整体覆盖当前 PATH，source 后必须补回
#    npm-global（lark-cli）与 pnpm（pi）——后端 fork 子进程时需要它们。
[ -f /etc/environment ] && set -a && . /etc/environment && set +a
export PATH="$HOME/.npm-global/bin:$HOME/.local/share/pnpm:$PATH"
export FEISHU_ASSISTANT_PI_BIN="${FEISHU_ASSISTANT_PI_BIN:-$HOME/.local/share/pnpm/pi}"

# ========== 后端 ==========
echo ""
echo "========== 后端部署（委托 depot 版 ${BACKEND_DEPLOY}） =========="
if [ ! -f "${BACKEND_DEPLOY}" ]; then
    echo "  ❌ 未找到 ${BACKEND_DEPLOY}"
    echo "     该文件由 P4 depot 下发（//depot/pyAutomation/backend/deploy.sh），"
    echo "     请检查后端工作区 /data/py_automation/backend 是否正常。"
    exit 1
fi
# depot 版内置 /server_status/busy 空闲等待：连续 2 次空闲才 kill，上限 5 分钟，
# 超时交互确认（非交互放弃部署）；FORCE_DEPLOY=1 跳过（环境变量子进程继承）。
# 空闲语义注意：AI review 进 await_compile 后构建跑在 TeamCity 上，服务器侧
# 只是 DB 持久化状态，判空闲是正确行为——重启无损，新进程收 tc_callback 续跑。
bash "${BACKEND_DEPLOY}"

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
# python3_pid.log 可能不可靠（nohup/bash -c 包装场景写入的不是真实 PID），
# 以 pgrep 拿到的真实进程为准并顺手修正 PID 文件。
REAL_PID=$(pgrep -f "manage.py runserver" | head -1)
if [ -n "${REAL_PID}" ]; then
    echo "${REAL_PID}" > "${BACKEND_DIR}/python3_pid.log"
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/)
    echo "  后端 PID: ${REAL_PID}  |  HTTP: ${HTTP_CODE}"
else
    echo "  ❌ 后端进程未运行!"
fi

echo "  前端 dist: ${FRONTEND_DIR}/dist/"
if [ -d "${FRONTEND_DIR}/dist" ]; then
    echo "  ✅ 前端构建产物已就绪"
else
    echo "  ❌ 前端构建产物不存在!"
fi
