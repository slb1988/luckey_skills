# 架构与协议契约

## 拓扑

```
ue-launcher 客户端（Tauri，MainDev/Tools/ue-launcher）
    GET <manifestUrl>            默认 http://192.168.2.13:5000/ue-launcher/tools
    GET <downloadUrl>（Range 续传 + 长度/SHA256 校验）
        │
auto-server 192.168.2.13:5000（WG 10.77.77.4:5000，同机两入口）
    Flask-RESTX namespace /ue-launcher（连字符，不是下划线）
        │
MySQL ue_launcher_tool（运行时唯一事实源）
    + UE_LAUNCHER_DATA_ROOT=/data/py_automation_data/ue_launcher
        ├── config/tools.json + packages/ + portable/   管理员手工维护的导入源
        ├── ue_launcher_packages/<slug>/<sha16>__<file>  已发布安装包（不可变）
        ├── ue_launcher_icons/<slug>/<file>              已发布图标
        └── backups/                                     发布前快照
```

部署主机是 auto-server（192.168.2.13），**与 NAS 无关**；NAS 不承担任何 ue-launcher 角色。

## 响应包装契约

pyAutomation 统一 `ServerResponse` 包装，HTTP 200 不代表业务成功：

```json
{ "status": { "code": 0, "message": "success", "description": "success" },
  "result": { "schemaVersion": 1, "updatedAt": "...", "tools": [ ... ] } }
```

- 成功判据是 `status.code == 0`（数字），FAIL=1 / EXCEPTION=2 也返回 HTTP 200。
- 客户端同时接受裸 manifest 与该包装（解包后走同一校验）；失败不覆盖最后有效缓存。
- `schemaVersion` 保持 1：serde 无 `deny_unknown_fields`，新增可选字段旧客户端会忽略；但**新 installerType 枚举值会让旧客户端整份目录拒收**（详见下方兼容性）。

## 工具条目字段（manifest v1）

| 字段 | 必填 | 说明 |
|---|---|---|
| id | ✅ | 稳定 slug，小写字母开头、仅小写/数字/短横线；升级改名不换 id |
| name | ✅ | 显示名 |
| version | ✅ | 发行标识，不代表本机已装版本 |
| installerType | ✅ | `exe` / `msi` / `portable` / `zip`（DB String(8) 恰好容纳 portable） |
| fileName / sha256 / sizeBytes | ✅ | 发布时由服务端计算，64 位 hex、>0 |
| downloadUrl | ✅ | 响应时拼接；外链显式优先，否则指向托管包 |
| category / description / toolType / webUrl | 可选 | description 即 tips，悬浮与详情共用 |
| installArgs | 可选 | exe/msi 用；portable/zip **必须为空**（不借它执行命令） |
| launchCandidates | 可选* | 已安装程序候选路径，支持 `%LOCALAPPDATA%` 等环境变量展开；portable/zip 可空，给了必须指向 .exe；exe/msi 至少一个 |
| iconUrl | 可选 | 托管图标或外链；加载失败回退默认图标 |
| entryPoint | 可选 | ≤256 字符；portable=单个 EXE 文件名（禁目录），zip=包内安全相对 .exe 路径（可子目录）；exe/msi/web 输出空串 |

## 四类包型

| installerType | 包 | 客户端行为 |
|---|---|---|
| exe | 安装器 | 下载校验 → spawn 安装向导（740 时 PowerShell RunAs 回退）→ 按 launchCandidates 检测就绪 |
| msi | 安装包 | `msiexec /i` + installArgs，其余同 exe |
| portable | 单文件 EXE | 校验后复制到用户级受管目录，以 entryPoint 文件名直接运行，无安装器 |
| zip | 普通 ZIP（Store/Deflate，不加密/分卷/自解压） | 安全解压保留文件树 → 运行 entryPoint；工作目录=EXE 所在目录 |

便携部署根：`%LOCALAPPDATA%\Programs\UE-Launcher\Toolbox\<tool-id>\<包SHA256>\`，staging→校验→原子绑定；与下载缓存（`%APPDATA%\com.pl.ue-launcher\toolbox_packages\`）分离。

## 路径安全规则（entryPoint 与 ZIP 条目共用）

拒绝：绝对路径、`..`、空段/单点段、ADS 冒号、Windows 设备保留名、段尾点/空格、大小写冲突。ZIP 固定上限：20,000 条目 / 实际输出 4 GiB（实现保护值，不代表对某个真实厂商包的验收结论）。

## 版本兼容性矩阵

| 场景 | 结果 |
|---|---|
| 旧客户端 + 目录新增可选字段 | 兼容（忽略未知字段），但重写缓存时丢失新字段 |
| 旧客户端 + 目录含 portable/zip 条目 | **整份 manifest 校验失败**，工具箱不可用 |
| 服务端/客户端任一损坏响应 | 客户端保留最后有效缓存，已安装软件仍可启动 |

发布新包型条目前必须确认所有目录消费者已升级；不能确认则保持条目未发布。
