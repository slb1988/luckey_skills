# Docker → Native p4d 迁移实录

> 从 Docker 容器 `helix-p4d-1` (2022.2) 迁移到原生 p4d (2024.1)
> 日期：2026-07-04/05

## 核心步骤速览

```bash
# 1. 从 Docker 做 checkpoint
docker exec -u perforce helix-p4d-1 sh -lc "p4d -r /data/master/root -jc /data/master/checkpoints/p4_backup"

# 2. 验证并拷出 checkpoint
docker exec -u perforce helix-p4d-1 sh -lc "p4d -jv /data/master/checkpoints/p4_backup.ckp.9"
docker cp helix-p4d-1:/data/master/checkpoints/p4_backup.ckp.9 /share/Container/perforce_backup/

# 3. 清空目标目录，恢复 checkpoint
rm -rf /share/Container/p4server/db.* /share/Container/p4server/journal /share/Container/p4server/server.locks
p4d -r /share/Container/p4server -jr /share/Container/perforce_backup/p4_backup.ckp.9

# 4. 升级数据库（跨大版本必须）
p4d -r /share/Container/p4server -xu

# 5. 安装 license（Keygen 生成）
Keygen -customer "slb1988" -ip "192.168.50.2" -users 100 -license-expires 10 -support-expires 10
cp license /share/Container/p4server/

# 6. 拷贝 depot archive 文件（28GB，耗时较长）
cp -a /share/Container/perforce/{depot,unity,ProjectB,ProjectC,DevOps,Plugins} /share/Container/p4server/

# 7. 启动
p4d -r /share/Container/p4server -p 192.168.50.2:1666 -d
```

## 迁移后清理

```bash
cd /share/Container/p4server
rm -rf checkpoint.* journal.0 journal.7 log ssl server.locks
# 节省约 2.4GB：checkpoint.1(361M) + checkpoint.8(467M) + journal.0(1.6G)
```

## 配置

```bash
export P4CHARSET=utf8
p4 -p 192.168.50.2:1666 -u slb1988 serverid NAS453Dmini
p4 -p 192.168.50.2:1666 -u slb1988 configure set monitor=1
p4 -p 192.168.50.2:1666 -u slb1988 configure set dm.user.noautocreate=2
p4 -p 192.168.50.2:1666 -u slb1988 configure set "P4PORT=192.168.50.2:1666"
p4 -p 192.168.50.2:1666 -u slb1988 admin restart
```

## 关键坑

### 1. Unicode 模式需要 P4CHARSET

旧 Docker 服务器开了 `P4D_USE_UNICODE=true`，恢复后所有 `p4` 命令需加：

```bash
export P4CHARSET=utf8
```

### 2. 跨版本升级

旧 p4d 是 2022.2（db version 55），新 p4d 是 2024.1（db version 58）。
必须跑 `p4d -xu`，否则 db 文件不兼容。

### 3. 权限问题（security=2 + protect 表）

恢复后的 protect 表没有 super 用户配置，导致 `p4 configure` 等操作无权限。

**解法**：停服 → 删 `db.protect` → 重启（空 protect 表下所有用户有 super 权限）→ 重新设置：

```bash
kill $(ps aux | grep 'p4d.*p4server' | awk '{print $2}')
rm /share/Container/p4server/db.protect
p4d -r /share/Container/p4server -p 192.168.50.2:1666 -d

# 配置 protect
p4 -p 192.168.50.2:1666 -u slb1988 protect -i <<'EOF'
Protections:
    super user slb1988 * //...
    super user admin * //...
    super user p4admin * //...
    write group * * //...
EOF
```

### 4. Docker chown 卡死

恢复 `db_backup` 文件后，Docker entrypoint 的 `chown -R perforce:perforce /data/master/root` 会遍历 28GB 全量文件，耗时极长。

**解法**：启动前手动修好 db 文件属主，避免 entrypoint 遍历 depot 目录：

```bash
chown -R 105:106 /share/Container/perforce/db.* /share/Container/perforce/journal*
```

### 5. checkpoint 路径在容器内部

Docker 备份脚本将 checkpoint 写到 `/data/master/checkpoints/`，此路径在容器 overlay 文件系统内，宿主机不可见。需 `docker cp` 拷出。

更好的做法是直接写到 bind mount 下：

```bash
docker exec -u perforce helix-p4d-1 \
  p4d -r /data/master/root -jc /data/master/root/checkpoint_backup
# 这样直接在宿主机 /share/Container/perforce/checkpoint_backup.ckp.N 可见
```

### 6. 数据恢复源

迁移过程中误删了 /share/Container/perforce 下的核心 db（db.rev, db.have, db.integed 等，共约 23 个文件）。恢复来源：

- `/share/Container/perforce_backup/db_backup/` — 手动备份的快照，包含全量 db 文件
- `/share/Container/perforce_backup/p4_backup.ckp.9` — 误删前 1 分钟做的 checkpoint
- Depot archive 文件（19G depot + 7.7G unity + ...）在磁盘上完好无损

## 最终验证

```bash
export P4CHARSET=utf8
p4 -p 192.168.50.2:1666 -u slb1988 info
p4 -p 192.168.50.2:1666 -u slb1988 depots
p4 -p 192.168.50.2:1666 -u slb1988 users
p4 -p 192.168.50.2:1666 -u slb1988 changes -m 3 -s submitted

# 文件数校验
for depot in DevOps Plugins ProjectB ProjectC depot unity; do
  echo "$depot: $(p4 -p 192.168.50.2:1666 files //$depot/... | wc -l) files"
done
```

预期结果：361,465 files across 7 depots，最新提交 Change 875 (2026/06/17)。
