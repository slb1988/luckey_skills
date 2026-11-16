---
name: minio-gc
description: auto-server MinIO 对象存储的 ugs-* bucket 垃圾清理（GC）。当用户提到 minio 清理、ugs-binaries 清理、UGS 构建包清理、blob 清理、minio 磁盘只增不减、清理 UGS 旧构建、minio-gc 时触发。即使用户只说"minio 又满了"、"清理一下 UGS 的旧包"、"ugs 桶哪些能删"也应触发。硬性规则：只清理 ugs-* 前缀 bucket；manifest 永远不删；90 天内 manifest 引用的 blob 永远不许删。清理必须走 dry-run 出清单 → 用户 review → 小批量试删 → 全量执行的流程，不允许跳过 review 直接删。
---

# MinIO ugs-* GC

清理 auto-server 上 MinIO 的 `ugs-*` bucket 中不再被引用的 blob（UGS 构建二进制内容寻址存储，只增不减）。

## 环境事实（2026-10-30 实测）

- 主机：auto-server（本机，192.168.2.13），容器名 `minio`，API `127.0.0.1:9000`
- 数据 bind mount 在 `/data/minio/data/<bucket>/`，盘上 ZFS lz4 压缩（逻辑:物理 ≈ 1:0.42）
- 根凭证从 `docker inspect minio --format '{{json .Config.Env}}'` 的 `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` 读取（脚本已内置，不要手抄密码到任何文件）
- bucket versioning 关闭，删除即彻底删除，不可恢复
- `images`（feishu-wiki 图床）等非 ugs-* bucket 与清理无关，永不触碰

## 硬性安全规则

1. **只清理 `ugs-*` 前缀的 bucket**，其他名字脚本直接拒绝
2. **manifest_*.json 永远不删**——它们是 UGS 按 CL 拉取的索引，且体积可忽略
3. **90 天内（mtime）manifest 引用的 blob 永远不许删**。这是脚本的核心不变量：execute 阶段会重新解析近期 manifest 再过滤一遍待删清单，防止 dry-run 之后新构建的 manifest 引用了清单里的旧 blob（内容寻址去重会发生这种情况）
4. mtime 7 天内的 blob 一律跳过（上传中途半成品保护）
5. 删除走 S3 API（`remove_objects`，批 1000），不直接 rm 盘上文件

## 流程（不许跳步）

1. **dry-run**：
   ```bash
   python3 /home/dev/.pi/skills/minio-gc/scripts/ugs_gc.py dry-run --bucket ugs-binaries
   ```
   产出 `runs/<bucket>-<date>/` 下的 `summary.txt`（回收预估）和 `delete_list.csv`（待删清单）。
2. **给用户 review**：汇报 summary 数字（待删数/纯孤儿数/仅旧 manifest 引用数/预计物理回收），清单路径交给用户过目。**未经用户明确同意不得执行删除。**
3. **小批量试删**：`execute --bucket ugs-binaries --limit 2000`，确认 UGS 客户端拉取近期 CL 正常。
4. **全量执行**：`execute --bucket ugs-binaries`（断点续删，中断后重跑自动跳过已删）。
5. **验证回收**：`du -sh /data/minio/data/<bucket>` 前后对比。

## 依赖性

- 宿主 python3 需 `pip3 install --user minio`（2026-10 已装）
- manifest 解析细节（每 1MiB 有 32 字节二进制头、blob key = `<2hex>/<62hex>`）见脚本 docstring，改解析逻辑前先读

## 已知边界

- 清理后 >90 天的旧 manifest 会悬空（索引在、blob 没了），即旧 CL 不能再从 UGS 拉二进制——这是策略预期行为，已在 review 时与用户确认
- grace 窗口内正在上传的 blob 靠 mtime 保护；execute 的重校验再兜一道
- 想改保留天数需改脚本 `RETENTION_DAYS` 并重新 dry-run + review，不要在命令行临时发挥
