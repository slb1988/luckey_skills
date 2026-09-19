# 服务端修改逻辑

后端源码：`ws:autoserver-deveops`（D:\work\admin_sun_depot_7184）`pyAutomation/backend/`。生产部署通用步骤见 [auto-server-backend-deploy](../../auto-server-backend-deploy/SKILL.md)，本页只写 ue-launcher 特有部分。

## 代码结构

| 文件 | 职责 |
|---|---|
| `server/applications/ue_launcher/api.py` | RESTX 路由：health/server-info、tools CRUD、upload-package、packages/icons 下载；写端点管理员鉴权（401/403） |
| `server/applications/ue_launcher/catalog.py` | 统一校验与发布服务：JSON 导入 dry-run/apply/upsert/导出、包/图标准备（hash+size+不可变落盘）、发布门槛（半成品/不受支持包型不下发） |
| `server/applications/ue_launcher/service.py` | manifest 组装：downloadUrl 外链优先否则托管地址（`UE_LAUNCHER_PUBLIC_BASE_URL`）、toolType app/web 分流 |
| `server/applications/ue_launcher/model.py` | `ue_launcher_tool` 表：slug/name/description/icon_url/file_name/sha256/size_bytes/install_args/launch_candidates/installer_type/web_url/external_url/icon_file/entry_point |
| `server/applications/ue_launcher/cli.py` | `ue-launcher import/export` CLI（注册 app.cli） |
| `doc/ue-launcher-api-spec.md` | 权威接口/配置文档（改字段必须同步） |
| `doc/examples/ue-launcher/tools.example.json` | 可校验样例（有单测钉住防漂移） |
| 测试 | `backend/tests/unit/test_ue_launcher_catalog.py`、`tests/api/test_ue_launcher_api.py`、`tests/unit/test_ue_launcher_migration.py` |

## 修改流程

1. Orca worker 在 `ws:autoserver-deveops` 实施；P4 命令一律 `-C utf8`。
2. 收尾建专用 pending CL，`describe` 核实清单；**不 shelf**（用户硬性规则）。未提交代码需要部署到 auto-server 时先报告用户决定传输方式，不自行 shelf。
3. 用户指示提交后再 submit；auto-server 走正常 `p4 sync`（代码已入库，无需取码技巧）。
4. 注意服务器工作区曾存在"部署跟踪 CL"（把未提交内容 reconcile 进服务器 client 的临时 CL）；源 CL 正式提交后必须显式处理该跟踪 CL 再 sync，不能直接忽略。

## 数据库迁移

- 迁移手写于 `backend/migrations/versions/`，挂在**当前实际唯一 head** 之后（`database_migration_guide` 文档里的 head 记录可能过时，以仓库 migrations 目录实测为准）。
- 离线 SQLite upgrade/downgrade 往返验证 + 既有 `test_migration_chain.py` 链完整性检查；不连生产库验证。
- 生产迁移：先备份（mysqldump + alembic_version/表快照到 `backend/tmp/backup_*`），再 `DISABLE_SCHEDULER=1 python -m flask --app manage.py db upgrade <revision>` 单步执行；deploy.sh 内建 upgrade 复核应为 no-op。
- 新增列用 nullable 增量；**回滚优先只回滚代码、保留新列与迁移 revision**——不要"downgrade 后再跑 deploy.sh"（脚本会重新 upgrade 抵消），也不要删迁移文件（alembic_version 会指向不存在的 revision）。

## 部署与验证（auto-server）

通用 deploy.sh 流程之外，ue-launcher 特有项：

- 模块环境变量经 `venv/bin/activate` 标记块注入（deploy.sh 每次 source）：`UE_LAUNCHER_DATA_ROOT=/data/py_automation_data/ue_launcher`、`UE_LAUNCHER_PUBLIC_BASE_URL=http://192.168.2.13:5000`。**重建 venv 会丢**，重建前备份恢复；长期应迁到受管持久配置。
- deploy.sh 的 sync 步骤可能遇到 writable 位文件报 "Can't clobber"（`chmod u-w` 后重试），sync 后脚本可能丢 +x（用 `bash deploy.sh` 跑）。
- 验证清单：`GET /ue-launcher/tools`（LAN+WG）200 + `status.code=0` + `schemaVersion=1` + 既有条目字段完整；匿名 POST/upload 401；`/ue-launcher/server-info` 反映新能力；`flask/app.log` 无 error。
- CLI 操作一律带 `DISABLE_SCHEDULER=1` 前缀（避免导入 app 时起调度器）。

## 当前线上状态速查

已上架（exe/msi）：everything 1.4.1.1030、notepad-plus-plus 8.7.9、p4v 2025.1.2742992、nodejs 24.15.0（msi）、python 3.11.8。`config/portable/mTail.exe` 已上传原件但未发布（便携条目需客户端兼容性确认）。
