# Docker p4d 运维（旧方案，待下线）

> Docker 版 Perforce 容器运维指南。迁移至原生 p4d 后逐步废弃。
> 完整容器配置、历史事件、数据库清单见 `p4d-server.md`。
> 通用诊断命令见 `p4-diagnostics-ops.md`。

## 容器信息

- **容器名**: `helix-p4d-1`
- **镜像**: `hawkmothstudio/helix-p4d:latest-data-4`（2023 年停更）
- **p4d 版本**: P4D/LINUX26X86_64/2022.2/2407422
- **数据目录**: `/share/Container/perforce`（bind mount → 容器内 `/data/master/root`）
- **Restart Policy**: `always`
- **端口映射**: 1666 → 32768

## 关键凭证（环境变量）

- 管理员: `p4admin` / `Sun1305329`
- P4PORT: `1666`

## 常见故障

### 1. 容器 OOM Kill（Exit Code 137）

**症状**: 容器状态 `Exited (137)`，启动后几秒到几分钟即崩溃，日志最后显示 "Starting p4d server..."

**根因**: QNAP NAS（NAS453Dmini）仅 8GB RAM，p4d 容器内存限制 4.5GB。数据库文件巨大（db.rev 162MB, db.revhx 133MB, db.have 73MB），加上 1.7GB journal 回放，启动时峰值内存超限触发 OOM killer。

**解决步骤**:

```bash
# 1. 停止不必要容器释放内存
docker stop jellyfin qbittorrent-1 container_ddns_1 qd-1 2>/dev/null

# 2. 给 p4d 降低内存限制（让 swap 参与，避免 OOM）
docker update --memory 3g --memory-swap 12g helix-p4d-1

# 3. 启动容器
docker start helix-p4d-1

# 4. 观察日志
docker logs -f helix-p4d-1
```

如果仍然 OOM，终极方案是给 QNAP 加内存条（当前 8GB → 建议升级到 16GB+）。

### 2. Checkpoint 过期

**症状**: db 文件大、journal 膨胀、启动慢。

**根因**: checkpoint 由备份脚本执行，服务频繁崩溃时无法完成。

**解决**: 容器稳定运行后，手动执行 checkpoint：

```bash
docker exec -u perforce helix-p4d-1 sh -c "p4d -r /data/master/root -jc"
```

### 3. 健康检查失败

**症状**: Health status 显示 `unhealthy`，但 p4d 可能实际运行正常。

**根因**: 健康检查用 `p4 info` 连接 1666，但容器 IP 变化或网络问题可能导致连接失败。

**验证**: `docker exec helix-p4d-1 p4 -p 1666 info`

### 4. ServerID 未设置

**症状**: 日志反复警告 "ServerID for the server should be set"

**解决**: `docker exec helix-p4d-1 p4 -p 1666 serverid Master`

## 备份

备份脚本位于 `/share/Container/backup_perforce.sh`，流程：
1. 执行 checkpoint + 截断 journal
2. 停止容器
3. `docker cp` 全量拷贝数据
4. 重启容器

备份目录: `/share/Container/perforce_backup/<timestamp>/`

**手动跑备份**: `bash /share/Container/backup_perforce.sh`

## P4V 客户端连接（Docker 版）

- 地址: `192.168.50.2:32768`（或容器网络内 `10.0.3.1:1666`）
- 最后成功客户端: `pc_qnap_depot_9516` (admin, P4V 2025.2)
