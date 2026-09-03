# NAS CUPS 打印中继（cups-server）

QNAP TS-453Dmini 上的 Docker CUPS 服务，把家中 Brother 打印机暴露给 WireGuard 私网设备与 AI agent（@nas 中转）。2026-09-03 部署上线，试打印已出纸。

## 架构

```
AI agent ──a2a_send(文件=OSS链接/图片附件)──▶ @nas ──docker exec──▶ cups-server ──IPP──▶ Brother
WG/局域网设备 ──lp -h 10.77.77.6 | 192.168.50.2──▶ cups-server :631 ──IPP──▶ 192.168.50.40
```

## 容器事实

| 项 | 值 |
|---|---|
| 容器名 | `cups-server` |
| 镜像 | `olbat/cupsd:latest`（x86_64） |
| 网络 | host 模式，监听 `0.0.0.0:631`（LAN `192.168.50.2:631` + WG `10.77.77.6:631` 双入口） |
| 重启策略 | `unless-stopped`（NAS 重启自恢复） |
| 配置卷 | `/share/CACHEDEV1_DATA/Container/cups/config` → 容器 `/etc/cups` |
| Web 管理 | `http://192.168.50.2:631/admin`（admin 账号，密码部署时设定，问用户） |
| 队列 | `brother` → `ipp://192.168.50.40/ipp/print`，driverless（IPP Everywhere）自动 PPD，默认 A4，已开启共享 |

## olbat/cupsd 系统属性

- **latest 无 entrypoint 引导逻辑**：挂到 `/etc/cups` 的空宿主目录会遮盖镜像自带的默认配置，cupsd 找不到 cupsd.conf 直接 Exit 1 且日志为空。全新部署（配置卷为空）必须先用镜像预填配置再启动：
  ```bash
  docker run --rm -v /share/CACHEDEV1_DATA/Container/cups/config:/mnt \
    olbat/cupsd:latest sh -c 'cp -a /etc/cups/. /mnt/'
  ```
- **默认网络放行**：`Listen *:631`，`<Location />` Allow all——局域网/WG 内免认证打印；`/admin` 由 `CUPS_USER_ADMIN` / `CUPS_USER_PASSWORD` 环境变量建的账号保护。
- **日志里的 avahi 报错无害**：容器内无 avahi-daemon，仅影响 mDNS 发现广播，打印功能不受影响。

## @nas 派发模板（可直接抄进 a2a_send）

### 打印 PDF（走 OSS 链接，支持选页/双面/份数）

```bash
curl -sL '<OSS_URL>' -o /tmp/print-job.pdf && \
docker exec cups-server lp -d brother \
  -o page-ranges=1-3,7 -o sides=two-sided-long-edge -o copies=1 /tmp/print-job.pdf
```

### 打印已在 NAS 本地的文件

```bash
docker exec cups-server lp -d brother -o <options> <NAS绝对路径>
```

### 图片直打

图片 ≤5MB 可作为 a2a_send 附件直接传给 @nas，落盘后同样走 `lp -d brother`；CUPS 过滤链自动处理缩放。改纸张示例：`-o media=iso_a5_148x210mm`。

**注意容器文件系统隔离**：附件落在宿主机（如 `/tmp/xx.png`）后，`docker exec cups-server lp ... /tmp/xx.png` 会报 `No such file or directory`——容器 `/tmp` 与宿主机不共享。必须先 `docker cp /tmp/xx.png cups-server:/tmp/xx.png` 拷进容器，再对容器内路径执行 `lp`。

### 状态确认（每次派发打印后必跟）

```bash
docker exec cups-server lpstat -W all -o brother   # 任务从列表消失 = completed
docker exec cups-server lpstat -p brother -l        # 队列状态/告警
```

## 运维操作

```bash
# 状态与日志
docker ps --filter name=cups-server
docker logs cups-server --tail 30

# 打印机换 IP 后重建队列（-m everywhere 会向打印机重新拉取能力生成 PPD）
docker exec cups-server lpadmin -p brother -E -v ipp://<新IP>/ipp/print -m everywhere

# 容器整体重建（配置卷非空，直接重跑即可）
docker rm -f cups-server
docker run -d --name cups-server --network host --restart unless-stopped \
  -v /share/CACHEDEV1_DATA/Container/cups/config:/etc/cups \
  -e CUPS_USER_ADMIN=admin -e CUPS_USER_PASSWORD='<问用户>' \
  olbat/cupsd:latest

# 从零全新部署（配置卷为空）→ 先执行上方"预填配置"命令，再 docker run
```

## 客户端接入

| 客户端 | 方式 |
|---|---|
| Linux / macOS（WG 内） | `lp -h 10.77.77.6 -d brother -o page-ranges=1-3 file.pdf`，或添加 `ipp://10.77.77.6:631/printers/brother` |
| Linux / macOS（家局域网） | 同上，host 换 `192.168.50.2` |
| Windows | 添加打印机 → 按 URL → `http://10.77.77.6:631/printers/brother`（WG）或 `http://192.168.50.2:631/printers/brother`（局域网），驱动选 Generic IPP Everywhere / Microsoft IPP Class Driver |
