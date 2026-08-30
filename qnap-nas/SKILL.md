---
name: qnap-nas
description: QNAP NAS 综合运维工具。当用户提到 QNAP 命令行、NAS 工具、HybridMount/CacheMount 挂载云存储、HBS3/HybridBackup 备份同步、NAS 磁盘管理、缓存策略、云网关 CLI、云备份 CLI、NAS 上的命令行工具、远程挂载管理、文件型云网关、天翼云盘/189网盘同步 时触发。即使用户只是说"HybridMount 命令行"、"HBS3 CLI"、"hbs3-rr3c"、"CacheMount 怎么用"、"NAS 上怎么看缓存"、"天翼云盘备份到 NAS" 也应触发。
---

# QNAP NAS 综合运维

## 环境信息

- **型号**: TS-453Dmini (Gemini Lake, TS-X53D 系列)
- **QPKG 路径**: `/share/CACHEDEV1_DATA/.qpkg/`
- **Shell 环境**: `/bin/sh`（非 bash），需注意兼容性

## HybridMount / CacheMount 命令行

HybridMount 的底层组件是 **CacheMount**，安装路径 `/share/CACHEDEV1_DATA/.qpkg/CacheMount/`，提供完整的 CLI 工具集。

### CLI 工具清单（位于 `bin/`）

| 工具 | 类型 | 用途 |
|------|------|------|
| `cmfs_cli` | 二进制 | **主管理工具** — mount/umount、缓存控制、健康检查、文件状态、日志管理 |
| `remote_mount_tool` | 二进制 | 远端云存储挂载管理 — 执行具体挂载/卸载操作 |
| `cm_cli` | 二进制 | 通用 CacheMount 操作（调用 libcachemount.so） |
| `cachemount_cli` | 二进制 | CacheMount 守护进程控制 |
| `cm_license_cli` | 二进制 | License 注册管理 |
| `cmfs` | 二进制 | CacheMountFS FUSE 文件系统 |
| `sshfs` / `sshpass` | 二进制 | SSH/SFTP 挂载支持 |
| `kick_cache` | 二进制 | 清理缓存 |

### cmfs_cli 完整命令参考

版本: v1.17.1 build 202604291035

```
cmfs_cli help                                   显示帮助
cmfs_cli version                                显示版本
cmfs_cli mount --config-file <conf> \
        --subfolders <子目录列表> <挂载点>         挂载缓存文件系统
cmfs_cli umount <挂载点>                         卸载

cmfs_cli get-cache-usage <挂载点>               查看缓存卷容量使用
cmfs_cli df <挂载点>                             同上（别名）

cmfs_cli reload <挂载点>                         重载配置
cmfs_cli reload-subfolder <挂载点>               重载子文件夹配置

cmfs_cli cached-synced <挂载点>                  检查缓存文件是否全部同步 (0:未完成, 1:已完成)
cmfs_cli cache-priority <挂载点>                 检查是否有缓存优先级变更 (0:无, 1:有)
cmfs_cli vs-refresh <目录>                       计算卷状态

cmfs_cli status <文件>                           查看文件缓存状态
cmfs_cli permission <文件>                       查看文件权限
cmfs_cli health <挂载点>                         挂载点健康检查
cmfs_cli upload <文件>                           上传文件到云端

cmfs_cli set-log-level <1-5> <挂载点>           设置日志级别 (1:ERROR 2:NOTICE 3:WARN 4:INFO 5:DEBUG)
cmfs_cli get-log-level <挂载点>                 查看当前日志级别

cmfs_cli cache-migration-status <挂载点>         导出缓存迁移进度
cmfs_cli chunkmap <文件>                         导出分块下载进度
cmfs_cli cache-size <文件>                       查看文件缓存大小

cmfs_cli get-global-error <挂载点>              显示全局错误
cmfs_cli set-fs-state <0|1|2> <挂载点>          设置文件系统状态 (0:normal, 1:read-only, 2:nospc)
cmfs_cli get-fs-state <挂载点>                   查看文件系统状态 ("normal"/"read-only"/"nospc")
cmfs_cli mountopt <挂载点>                       查看挂载选项

cmfs_cli set-write-cache <0|1> <挂载点>         开关写入缓存 (0:off, 1:on)
cmfs_cli purge-cache <文件>                      移除缓存
cmfs_cli get-pin-dir-status <目录>              查看已固定目录统计
cmfs_cli is-pin-nospc <挂载点>                   查看固定缓存是否空间不足
cmfs_cli scan-pin-dir-status <挂载点>            触发更新固定目录统计
cmfs_cli dir-select-level <目录>                 查看目录选择级别
cmfs_cli retrieve-subfolder <挂载点>             导出子文件夹列表
cmfs_cli set-priority <1|2|3> <路径>            设置路径优先级 (1:low, 2:normal, 3:pin)
cmfs_cli reset-vault-idle-time <秒> <挂载点>    重置 Vault 空闲时间
```

### remote_mount_tool 用法

```bash
remote_mount_tool \
  --func=FUNC \        # 功能名
  --sid=SID \          # Session ID
  --in=INPUT \         # 输入数据 (JSON)
  --owner=UID \        # 所有者 UID
  --uuid=UUID \        # UUID
  --p1=PARAM1 \        # 参数1
  --p2=PARAM2 \        # 参数2
  --debug=0-3          # 调试级别 (0-3, 3 最详细)
```

### 常用操作示例

```bash
# 进入 CacheMount 目录
cd /share/CACHEDEV1_DATA/.qpkg/CacheMount/bin

# 查看 mount 的配置文件
ls /share/CACHEDEV1_DATA/.qpkg/CacheMount/mount/

# 查看挂载列表
./cmfs_cli retrieve-subfolder /path/to/mountpoint

# 检查缓存同步状态
./cmfs_cli cached-synced /path/to/mountpoint

# 查看卷容量使用
./cmfs_cli get-cache-usage /path/to/mountpoint

# 健康检查
./cmfs_cli health /path/to/mountpoint

# 查看文件缓存状态
./cmfs_cli status /path/to/file

# 触发上传到云端
./cmfs_cli upload /path/to/file

# 查看全局错误
./cmfs_cli get-global-error /path/to/mountpoint

# 查看文件系统状态
./cmfs_cli get-fs-state /path/to/mountpoint

# 开启写入缓存
./cmfs_cli set-write-cache 1 /path/to/mountpoint

# 固定目录（始终缓存本地）
./cmfs_cli set-priority 3 /path/to/dir

# 设置详细日志
./cmfs_cli set-log-level 4 /path/to/mountpoint

# 查看版本
./cmfs_cli version
```

### cm_license_cli 用法

```bash
# License 注册
cm_license_cli qlicense_register
```

### 配置与日志路径

| 路径 | 说明 |
|------|------|
| `/share/CACHEDEV1_DATA/.qpkg/CacheMount/cachemount.json` | 运行时配置（symlink → cachemount_production.json） |
| `/share/CACHEDEV1_DATA/.qpkg/CacheMount/cachemount_production.json` | 生产配置 |
| `/share/CACHEDEV1_DATA/.qpkg/CacheMount/cachemount.conf` | 基础配置 |
| `/share/CACHEDEV1_DATA/.qpkg/CacheMount/log/` | 日志目录 |
| `/mnt/ext/opt/cachemount/log/cm.log` | cm_cli 日志 |
| `/share/CACHEDEV1_DATA/.qpkg/CacheMount/mount/` | 挂载配置目录 |
| `/share/CACHEDEV1_DATA/.qpkg/CacheMount/remote_mount.json` | 远程挂载配置 |

### 缓存目录

| 路径 | 说明 |
|------|------|
| `/mnt/ext/opt/cachemount/temp_cache` | 临时缓存 |
| `/share/CACHEDEV1_DATA/.qpkg/CacheMount/temp_cache` | 临时缓存（实际路径） |
| `/share/CACHEDEV1_DATA/.qpkg/CacheMount/metadata/` | 元数据 |
| `/mnt/ext/opt/cachemount/metadata` | 元数据 symlink（已启用 io_aware 标记） |

### 启动/停止

```bash
# CacheMount 生命周期由 /etc/rcS.d 和 /etc/rcK.d 管理
# 启动序号: K27CacheMount (rcK.d 中优先级 27)
# 手动启动:
/share/CACHEDEV1_DATA/.qpkg/CacheMount/CacheMount.sh start

# 手动停止:
/share/CACHEDEV1_DATA/.qpkg/CacheMount/CacheMount.sh stop

# 远端挂载守护进程:
/share/CACHEDEV1_DATA/.qpkg/CacheMount/etc/init.d/remote_mount.sh start|stop
```

## HybridBackup / HBS3 (Hybrid Backup Sync) 命令行

HBS3 是 QNAP 的云网盘备份同步工具，核心 CLI 是 **hbs3-rr3c**（基于 rclone 定制），安装路径 `/share/CACHEDEV1_DATA/.qpkg/HybridBackup/bin/hbs3-rr3c`。

版本: v1.68.0-DEV (Go 1.22.9)

### 命令概览

```
hbs3-rr3c [command]

命令:
  hbssync     执行 HBS RR3 同步任务
  hbsfix      根据完整性检查报告修复损坏文件
  lsf         列出远程路径文件和目录（可解析格式）
  lsjson      以 JSON 格式列出远程路径
  obscure     加密密码用于配置文件
  version     显示版本
  help        显示帮助
```

### hbssync — 同步任务

核心同步命令，功能基于 rclone sync，面向 HBS 作业场景增强。

```bash
hbs3-rr3c hbssync source:path dest:path [flags]
```

**常用 flags:**

| Flag | 说明 |
|------|------|
| `--dry-run` / `-n` | 试运行，不实际修改 |
| `--verbose` / `-v` | 详细输出（可重复，`-vv` 更详细） |
| `--checksum` / `-c` | 用校验和检测变化 |
| `--ignore-times` / `-I` | 不跳过大小和时间匹配的文件 |
| `--update` / `-u` | 跳过目标端更新的文件 |
| `--size-only` | 仅比较大小 |
| `--delete-extra` | 删除目标端多余的文件 |
| `--delete-before/after/during` | 删除时机 |
| `--exclude pattern` | 排除匹配的文件 |
| `--include pattern` | 包含匹配的文件 |
| `--max-age Duration` | 仅传输指定时间内的文件 |
| `--min-size SizeSuffix` | 仅传输大于指定大小的文件 |
| `--max-transfer SizeSuffix` | 最大传输数据量 |
| `--max-duration Duration` | 最大传输时间 |
| `--backup-dir DIR` | 备份目录（保留被覆盖的文件） |
| `--suffix SUFFIX` | 给变化文件加后缀 |
| `--track-renames` | 跟踪重命名，服务端 move |
| `--inplace` | 直接写入目标文件（不先写临时文件） |
| `--multi-thread-streams N` | 多线程下载流数（默认 4） |
| `--multi-thread-cutoff Size` | 多线程阈值（默认 256Mi） |
| `--check-first` | 先检查再传输 |
| `--ignore-existing` | 跳过已存在的文件 |
| `--create-empty-src-dirs` | 在目标端创建空的源目录 |
| `--hbs-check-report file` | 输出完整性检查报告 CSV |

**HBS 专用 flags:**

| Flag | 说明 |
|------|------|
| `--job-id string` | HBS 作业 ID |
| `--job-name string` | HBS 作业名称 |
| `--realtime` | 实时同步模式 |
| `--snapshot` | 创建快照 |
| `--notify-finish` | 任务完成时发送通知 |
| `--notify-fail` | 任务失败时发送通知 |
| `--notify-resume` | 任务恢复时发送通知 |

### hbsfix — 修复损坏文件

```bash
hbs3-rr3c hbsfix source:path dest:path [flags]
```

读取 hbssync 生成的 `--hbs-check-report` CSV，根据标志列自动修复：

| 标志 | 含义 | 修复动作 |
|------|------|----------|
| `+` | 目标端缺失 | 从源拷贝到目标 |
| `-` | 源端缺失 | 从目标删除 |
| `<` | mtime 不一致（源更旧） | 更新目标 mtime |
| `s` | 大小不匹配 | 从源重新拷贝 |
| `*` | 校验和不匹配 | 从源重新拷贝 |

```bash
# 用法示例
hbs3-rr3c hbsfix src: dst: \
  --check-csv-file /path/to/hbs_check_report.csv \
  --fix-csv-file /path/to/hbs_fix_report.csv \
  --dry-run
```

### lsf / lsjson — 列出远程文件

```bash
# 可解析格式列出
hbs3-rr3c lsf remote:path [flags]
  -R, --recursive       递归
  --csv                 输出 CSV
  --files-only          仅文件
  --dirs-only           仅目录
  -F, --format string   输出格式（默认 "p"）

# JSON 格式列出
hbs3-rr3c lsjson remote:path [flags]
  -R, --recursive       递归
  --files-only          仅文件
  --dirs-only           仅目录
  --hash                包含哈希
  -M, --metadata        包含元数据
  --no-modtime          跳过修改时间
  --stat                仅返回文件信息
```

### obscure — 密码加密

```bash
hbs3-rr3c obscure <password>
# 输出加密后的密码字符串，用于写入配置文件
```

### 常用操作示例

```bash
BIN=/share/CACHEDEV1_DATA/.qpkg/HybridBackup/bin/hbs3-rr3c

# 试运行同步（查看会做什么但不执行）
$BIN hbssync /share/SourceDir remote:BackupDir --dry-run -v

# 全量同步 + 删除目标端多余文件
$BIN hbssync /share/SourceDir remote:BackupDir --delete-extra -v

# 用校验和比较
$BIN hbssync /share/SourceDir remote:BackupDir --checksum -v

# 生成完整性检查报告
$BIN hbssync /share/SourceDir remote:BackupDir \
  --hbs-check-report /tmp/hbs_check.csv -v

# 根据报告修复损坏文件
$BIN hbsfix /share/SourceDir remote:BackupDir \
  --check-csv-file /tmp/hbs_check.csv \
  --fix-csv-file /tmp/hbs_fix.csv

# 列出远程目录（JSON）
$BIN lsjson remote:BackupDir -R

# 查看版本
$BIN version
```

### 云端账号

| 名称 | 类型 |
|------|------|
| 百度网盘Vip | 百度网盘 |
| OneDrive_382 | OneDrive |

### 当前同步任务

**已配置的 HBS3 同步任务及运行状态** 详见 → [references/hbs3-jobs.md](references/hbs3-jobs.md)

快速概览：

| 任务名 | UUID | 启用 | 账号 | 方向 | 本地路径 | 远程路径 | 调度 |
|--------|------|------|------|------|----------|----------|------|
| Perforce Sync | `c0b4...b3ef` | ✅ | 百度网盘 | → 远程 | `Container/perforce` | `/NasSync/PerforceBackup` | 每天 04:00 |
| Two-way Sync | `1f6a...b3ef` | ✅ | 百度网盘 | ↔ 双向 | `BaiduDisk/Sync` | `/NasSyncNew` | 手动 |
| Two-way Sync 1 | `4355...0e2b` | ❌ | OneDrive | ↔ 双向 | `Documents/OneDriveDisk` | `/OneDrive` | — |
| Two-way Sync Worked | `0b25...4012` | ❌ | 百度网盘 | ↔ 双向 | `BaiduDisk/BaiduDiskAutoSync` | `/NasSync` | 每天 19:00 |

查询命令：

```bash
SQLITE=/share/CACHEDEV1_DATA/.qpkg/CacheMount/bin/sqlite3
DB=/share/CACHEDEV1_DATA/.qpkg/HybridBackup/CloudConnector3/config.db
$SQLITE $DB "SELECT json_extract(value, '$.name'), json_extract(value, '$.enable') FROM jobs;"
```

**手动触发同步任务** — 使用 CloudConnector3 内置的 `sync` CLI（需 sudo admin），详见 → [references/hbs3-jobs.md#命令行触发同步任务](references/hbs3-jobs.md#命令行触发同步任务)

### 其他 HybridBackup 工具

| 工具 | 路径 | 用途 |
|------|------|------|
| `rsync` | `bin/rsync` | rsync 同步（多个版本） |
| `qsync` | `bin/qsync` | Qsync 同步（多个版本） |
| `qts_bbr` | `bin/qts_bbr` | BBR 加速 |
| `rr2/bin/cli/` | Python 脚本 | job_config, verify, check_md5, server 等管理工具 |
| `rsyncRR.sh` | 根目录 | 实时 rsync 脚本 |
| `CloudConnector3/` | 根目录 | 三方云连接器 + 任务数据库 |

## 天翼云盘（189）同步方案

天翼云盘**无官方 Linux/QNAP 客户端**（只有 Win/Mac/手机），NAS 上只能走第三方工具：

| 方案 | 形态 | 适用场景 | 备注 |
|------|------|----------|------|
| **OpenList** | Docker | 网盘挂载 + WebDAV + 云间互拷 | **首选**；AList 2025 被收购后的社区 fork，原生 189CloudPC 驱动 |
| **cloudpan189-go** | 单二进制 CLI | NAS 本地 → 天翼单向备份 | 最轻量，自带 backup/sync 命令配 cron 即可；项目维护慢，天翼接口变动有失效风险 |
| **CloudDrive2** | Docker/QPKG | 网盘挂成本地盘再 rsync | 闭源免费版功能受限；FUSE 挂载跑大批量备份稳定性一般 |

推荐架构：

- **NAS → 天翼备份**：OpenList 挂天翼开 WebDAV，`rclone sync /share/xxx webdav:/backup` + cron（断点续传/增量比对/校验比裸脚本可靠）；轻量替代是 cloudpan189-go `backup` + cron
- **云到云**（别的网盘/分享链接 → 天翼，不经本地落盘）：OpenList 双挂源盘和天翼后用后台「复制任务」服务器端互拷；或两边开 WebDAV 用 rclone 搬

坑位：

- 天翼分**个人云**和**家庭云**，driver 配置选错会登录失败或看不到文件
- 非会员大流量上传限速，首次大批量备份建议夜间跑
- cookie/token 有有效期，OpenList 掉线要重新登录；长期无人值守场景需留意凭证刷新

## 其他已安装的 QPKG 应用

完整列表见 → [references/installed-qpkgs.md](references/installed-qpkgs.md)。

| QPKG | 用途 |
|------|------|
| `CacheMount` | 文件型云网关 (HybridMount) |
| `HybridBackup` | 混合备份中心 |
| `container-station` | Docker 容器管理 |
| `Entware` | 包管理器 (opkg) |
| `QTransmission3` | BT 下载 |
| `PlexMediaServer` | 媒体服务器 |
| `DownloadStation` | 下载站 |
| `QsyncServer` | 同步服务 |
| `Qsirch` | 全文搜索 |
| `CloudLink` | 远程访问 |
| `QuMagieCore` | AI 相册 |
| `xunlei-pan` | 迅雷云盘 |

## 相关 Skill

- `qnap-git-setup` — Git 安装、SSH key 生成、GitHub 绑定
- `qnap-perforce` — Docker Perforce (Helix Core) 运维
- `mihomo-proxy-setup` — 翻墙代理（QNAP 可能需要）
