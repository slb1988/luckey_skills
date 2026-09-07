# QNAP NAS 磁盘空间治理

2026-09 实测（TS-453Dmini 全盘 du 排查后确认）。

## 卷拓扑

本机共 **4 个存储卷**，不要只盯主卷：

| 卷 | 容量级 | 备注 |
|---|---|---|
| CACHEDEV1 | 主卷 | 系统/.qpkg/docker/Perforce 都在这 |
| CACHEDEV2 | ~14.3T | 大容量卷，曾到 91% 而主卷仅 66%——**真正的容量危机可能在这里** |
| CACHEDEV3 / 4 | — | 历史排查时余量充足 |

排查空间必须先 `df` 全部卷，主卷健康不代表整机健康。

## CACHEDEV1 已知可清理缓存（按收益排序）

| 路径 | 量级 | 清理代价 |
|---|---|---|
| `/share/CACHEDEV1_DATA/.system/thumbnail/` | **~51G** | 纯缩略图缓存可重建；重建期 CPU 高、相册首访变慢 |
| `ArchivedDocuments/@Recycle` | ~5.1G | 回收站，清空即可 |
| `/share/CACHEDEV1_DATA/.system/dbbackup/` | ~3.5G | QTS 配置周备会无限累积（曾 9+ 份），保留最近 2–4 份 |
| Qsirch 索引 | ~2G | 重建期间全文搜索不可用 |
| QuMagie 人脸索引 | ~1.5G | 重建即可 |
| Plex 缓存/转码目录 | ~1G | 清缓存不影响媒体库 |
| Perforce `checkpoint.1` 等旧 checkpoint | 数百 M | ⚠️ 确认当前 checkpoint 有效后再删 |

## 保护区（不要当缓存清）

- 用户数据：Multimedia / Public / Documents（合计数百 G，占大头但属正常数据）
- Perforce 两实例 depot ~64G、memory-center ~7G、docker 镜像 ~7.9G（其中 ollama ~5G，被运行容器引用）

## 排查结论（校准预期）

- **`docker system prune`（dangling）收益≈0**：镜像几乎全被在跑容器引用，空间全在数据/缓存目录，不在 docker 孤儿对象。
- **`/tmp` 是 tmpfs（内存盘）**，永远不是磁盘占用来源，不用查。
- 本机**没有大日志文件**——日志不是这台 NAS 的空间杠杆，排查时跳过日志路径直接 du 大户目录。

## 2026-09-07 执行轮实测补充

- **`.system/thumbnail/` 清理**：直接删目录内容（保留目录本身）即可，**不需要停 MultimediaConsole**，删除后自动重建（实测 1 分钟内重建出 257 个子目录）。`mmc_cli.sh clear-unused-thumb` 官方命令释放为 0，不可靠，跳过。
- **Plex 缓存实际只有 ~2MB**，且目录属 admin 不可写——不值得列入清理项。
- **CACHEDEV2 占用分解**（14.3T 卷）：`ArchivedDocuments/` 11.5T（其中 **UE/ 10.8T**，LearningResource 387G）、`ArchivedMultimedia/` 1.6T（电视剧 1.16T）、Software 209G。下一轮清理主线 = UE 归档专项审计（旧引擎版本/可再生的 DerivedDataCache、Intermediate、Saved）。
- **BusyBox 无 `nohup`**：后台跑长删除任务用 `setsid`，首轮用 nohup 会静默未启动。
- 权限限制下 `truncate -s 0` 降级有效：dbbackup 5 份旧备份实测回收 2.27G（空文件条目需 admin 后补删）。
