---
name: ue-launcher-toolbox
description: UE Launcher 工具箱（Toolbox）端到端知识与操作流程，覆盖 MainDev Tools/ue-launcher Tauri 客户端、pyAutomation ue_launcher 后端与 auto-server 生产部署。当用户提到 ue-launcher、工具箱、toolbox、软件下载/安装目录、tools.json 配置、上架软件（Notepad++/Everything/P4V/mTail/Node/Python 等）、发布便携 EXE 或 ZIP 免安装包、编译 launcher exe、740 提权报错、目录拉取失败（builder error）、灰/彩图标状态、已安装软件识别去重时必须使用。修改后端、手工配置软件条目、编译客户端、部署发布前先读对应 references 模块。
compatibility: Tauri, React, Rust, Flask-RESTX, SQLAlchemy, Perforce
---

# UE Launcher 工具箱

共性层：[pyauto-shared](../pyauto-shared/SKILL.md)（证据/权限/交付边界）。部署通用步骤见 [auto-server-backend-deploy](../auto-server-backend-deploy/SKILL.md)，本 skill 只维护 ue-launcher 特有契约与流程，不复制通用部署文档。

## 系统速览

| 组件 | 位置 | 说明 |
|---|---|---|
| 客户端 | ws:maindev `Tools/ue-launcher/` | Tauri：React `src/` + Rust `src-tauri/` |
| 服务端 | ws:autoserver-deveops `pyAutomation/backend/server/applications/ue_launcher/` | Flask-RESTX，URL 前缀 `/ue-launcher` |
| 生产服务 | auto-server `192.168.2.13:5000`（WG `10.77.77.4:5000`） | 运行用户 dev，目录 `/data/py_automation/backend`；**与 NAS 无关** |
| 运行数据 | MySQL `ue_launcher_tool` 表 + `UE_LAUNCHER_DATA_ROOT=/data/py_automation_data/ue_launcher` | DB 是运行时唯一事实源；tools.json 只是导入入口 |
| 客户端已安装副本 | `%LOCALAPPDATA%\UnrealGameSync\Tools\UeLauncher\ue-launcher.exe` | 用户实际运行的 exe 位置，更新 tracked exe 不等于更新它 |

两端权威文档（字段级细节以它们为准）：服务端 `pyAutomation/doc/ue-launcher-api-spec.md`；客户端 `Tools/ue-launcher/references/toolbox.md`。

## 模块导航（按需读，不整份加载）

| 任务 | 读 |
|---|---|
| 改后端代码、迁移、部署、回滚 | [references/backend-changes.md](references/backend-changes.md) |
| 手工上架/修改/下架软件条目 | [references/tool-config.md](references/tool-config.md) |
| 编译客户端、更新 exe 到各位置 | [references/client-build.md](references/client-build.md) |
| 改客户端行为：目录拉取、安装、便携部署、本机识别、去重、提权 | [references/client-runtime.md](references/client-runtime.md) |
| 协议契约、字段、存储布局、版本兼容性 | [references/architecture.md](references/architecture.md) |
| 报错排查（740、builder error、占用、部署坑） | [references/troubleshooting.md](references/troubleshooting.md) |

## 硬规则

- 两端 P4 改动各建**专用 pending CL**；**pending CL 不要 shelf**（用户 2026-09-19 硬性规则）；不擅自 submit，用户明确指示才提交。
- 不杀用户或运行中的 launcher 进程；exe 被占用改用独立 target 目录编译，替换等进程退出后再做。
- 不自动安装第三方软件、不触发真实 UAC、不写用户 settings/HKCU 来"验证"；真实安装/UAC 验收需用户明确授权。
- **新包型（portable/zip）条目在确认所有目录消费者升级前不发布**——旧客户端遇未知 installerType 会整份目录校验失败。
- 服务端写接口（POST/PUT/DELETE/upload）有管理员鉴权（401/403）；目录 GET 公开。配置/发布走 CLI dry-run→apply，不直写 SQL。
- 目录状态由客户端本机检测决定（灰=未就绪可点击安装，彩=可运行点击启动）；**是否安装不写进服务器目录**。
