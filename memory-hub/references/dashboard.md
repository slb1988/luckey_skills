# Memory Hub Dashboard 开发/部署备忘

面板地址 `http://10.77.77.6:9288/`；权威文档见服务端仓库 `docs/DASHBOARD.md`。

<memory category="code-locations">
Dashboard 开发在本机源码副本 `D:/Github/memory-hub` 进行，NAS `/share/Container/memory-hub` 只是部署目标（经 git push/pull 同步；本机直连 NAS 的 SSH key 未授权、SMB 无凭证，部署需在 NAS 上执行命令或提供 SSH 密码）。前端是 Vue 3 + TS + Vite，构建产物 `frontend/dist` **自 commit 2c3b935 起不再纳入 git 追踪**（.gitignore 已移除 dist）；NAS 上现已有 node v22（`~/.local/bin/node`），部署 = NAS 本地 `cd frontend && npm ci && npm run build`，dist 由 backend 直接托管（带 ETag/304 缓存）。legacy 后端 `src/memory_hub` 因历史原因保持不动，新功能只加在独立 `backend/`。
</memory>

<memory category="deployment">
前后端发布标准流程（NAS 上执行，三次实测验证）：`git pull` → 若 `frontend/` 有变更则 `cd frontend && npm run build`（依赖已装过可跳过 npm ci）→ `sh scripts/stop_all.sh && sh scripts/start_all.sh`（ editable 安装的 python 包代码重启即生效，无需 reinstall；仅 pyproject/依赖变更时才 `uv pip install -e .`）→ 验证 `curl :9287/health/ready` + `curl :9288/api/v1/health/live` + `curl :9288/ | grep index-*.js` 确认托管的是新构建产物。
</memory>

<memory category="troubleshooting">
新版 FastAPI 的 `include_router` 会包成嵌套的 `_IncludedRouter`，在测试里遍历 `app.routes` 做 openapi 协议一致性校验时必须递归展开，否则路由漏检导致误报。升级 FastAPI 后协议校验测试突然失败先查这里。
</memory>
