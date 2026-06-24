---
name: wireguard-setup
description: 在 Ubuntu 服务器上搭建 WireGuard VPN 服务端，实现私有组网。当用户提到"装WireGuard"、"搭建VPN"、"私有组网"、"异地组网"、"WireGuard 服务端"、"wg VPN"、"手机连电脑"、"iOS连VPN"、"wireguard server"、"组网环境"、"内网互通"、"点对点VPN"时触发。即使用户只说"帮我和几台机器组个网"或"我想从外面连回家里电脑"，也应考虑使用此 Skill。支持全新的服务端搭建和已有服务端添加新客户端。
---

# WireGuard VPN 服务端搭建

在 Ubuntu 上快速搭建 WireGuard VPN 服务端，让 iOS / Android / Windows / macOS / Linux 客户端互相通信，形成私有局域网。

## 为什么选 WireGuard

- 内核级实现（Linux 5.6+ 内置），性能极高，CPU 开销极低
- 配置极简：每个节点只需几行配置
- 漫游友好：IP 变化时自动重连，无需重拨
- 跨平台：iOS / Android / Windows / macOS / Linux 全有原生客户端
- 安全性：基于 Noise 协议，密钥对认证，无弱加密选项

## 第一步：环境检查

运行以下检查，确认当前状态。检查项全部通过再开始安装。

```bash
# 1. 系统版本（需 Ubuntu，内核 >= 5.6）
lsb_release -a 2>/dev/null
uname -r

# 2. 当前公网 IP
curl -s --max-time 5 ifconfig.me || curl -s --max-time 5 icanhazip.com

# 3. 默认出口网卡和网关
ip route show default

# 4. WireGuard 是否已安装
which wg 2>/dev/null && wg --version || echo "WireGuard not installed"

# 5. 是否已有 wg0 接口
sudo wg show 2>/dev/null || echo "No existing WireGuard interface"
```

⚠️ 如果内核版本低于 5.6，需要额外安装 wireguard-dkms，不在本 Skill 覆盖范围内。

## 第二步：确认关键参数

和用户确认以下参数后再开始配置。如果用户没有特别要求，使用默认值。

| 参数 | 默认值 | 说明 |
|------|--------|------|
| VPN 子网 | `10.77.77.0/24` | 避开 Docker (172.x) 和常见 VPC (10.0.x) |
| 服务器 VPN IP | `10.77.77.1` | 子网第一个地址 |
| 监听端口 | `51820` | WireGuard 默认端口 |
| 公网 IP | 自动检测 | 用户可手动指定 |
| 客户端流量模式 | `0.0.0.0/0`（全隧道） | 如需分流可改为子网段 |
| 数据目录 | `~/wireguard-configs/` | 私钥和客户端配置存放处 |

**流量模式说明：**
- `AllowedIPs = 0.0.0.0/0`：客户端所有流量走 VPN（全隧道，适合在外面用）
- `AllowedIPs = 10.77.77.0/24`：只有 VPN 内网流量走隧道（分流，适合只想互访设备）

## 第三步：安装 WireGuard

```bash
sudo apt update && sudo apt install wireguard wireguard-tools qrencode -y
```

- `wireguard`：内核模块和 wg-quick 脚本
- `wireguard-tools`：wg 命令行工具
- `qrencode`：生成二维码，供手机扫码导入

## 第四步：生成密钥对

**所有私钥文件保存在 `~/wireguard-configs/` 目录中，权限 600。**
这是核心原则：私钥不落终端日志、不外泄。

```bash
mkdir -p ~/wireguard-configs
chmod 700 ~/wireguard-configs

# 生成服务端密钥对
wg genkey | tee ~/wireguard-configs/server_private.key | wg pubkey > ~/wireguard-configs/server_public.key
chmod 600 ~/wireguard-configs/server_private.key ~/wireguard-configs/server_public.key
```

**每新增一个客户端**也执行类似操作，见「添加新客户端」一节。

## 第五步：编写服务端配置

生成 `/etc/wireguard/wg0.conf`，结构如下：

```ini
[Interface]
PrivateKey = <server_private_key>
Address = <server_vpn_ip>/24
ListenPort = 51820

# NAT 转发 - 允许客户端互相访问 + 通过服务器上网
PostUp = iptables -A FORWARD -i wg0 -j ACCEPT
PostUp = iptables -A FORWARD -o wg0 -j ACCEPT
PostUp = iptables -t nat -A POSTROUTING -o <public_nic> -j MASQUERADE
PostDown = iptables -D FORWARD -i wg0 -j ACCEPT
PostDown = iptables -D FORWARD -o wg0 -j ACCEPT
PostDown = iptables -t nat -D POSTROUTING -o <public_nic> -j MASQUERADE

[Peer]
# <client_name>
PublicKey = <client_public_key>
AllowedIPs = <client_vpn_ip>/32
```

其中 `<public_nic>` 是默认路由的出口网卡（通常是 `eth0`）。

写入后设置权限并部署：

```bash
# 用 write 工具写临时文件，确认无误后再 cp
sudo cp /tmp/wg0-server.conf /etc/wireguard/wg0.conf
sudo chmod 600 /etc/wireguard/wg0.conf
```

**注意：** 每个客户端对应一个 `[Peer]` 段，`AllowedIPs` 必须写 `/32` 精确匹配该客户端的 VPN IP。后续添加客户端时直接追加在文件末尾即可。

## 第六步：开启系统 IP 转发

```bash
# 修改 sysctl
sudo sed -i 's/^#net.ipv4.ip_forward=1/net.ipv4.ip_forward=1/' /etc/sysctl.conf
# 立即生效（如果已经开启也不会报错）
sudo sysctl -p 2>/dev/null | grep forward
```

确认输出 `net.ipv4.ip_forward = 1`。

## 第七步：配置防火墙

假设使用 UFW（Ubuntu 默认）：

```bash
sudo ufw allow 51820/udp comment 'WireGuard VPN'
sudo ufw status | grep 51820
```

如果使用 iptables/firewalld，需要手动放行 `51820/udp`。另外云服务器（腾讯云/阿里云/AWS）还需在安全组中放行此端口。

## 第八步：启动 WireGuard 服务

```bash
sudo systemctl enable wg-quick@wg0
sudo systemctl start wg-quick@wg0
sudo systemctl status wg-quick@wg0 --no-pager -l
sudo wg show
```

确认 `sudo wg show` 输出中包含 `listening port: 51820` 和各个 peer。

## 第九步：生成客户端配置

为每个客户端在 `~/wireguard-configs/` 下生成 `.conf` 文件：

```ini
[Interface]
PrivateKey = <client_private_key>
Address = <client_vpn_ip>/24
DNS = 223.5.5.5

[Peer]
PublicKey = <server_public_key>
Endpoint = <public_ip>:51820
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
```

**DNS 说明：** 默认用阿里 DNS `223.5.5.5`（在国内延迟低）。也可用 `1.1.1.1` 或 `8.8.8.8`。

**PersistentKeepalive：** 对于 NAT 后的客户端（手机、家庭宽带），建议设为 25 秒，保持 UDP 隧道不老化。如果是直连服务器则不需要此行。

## 第十步：生成二维码（手机扫码导入）

```bash
qrencode -t ANSIUTF8 < ~/wireguard-configs/client-xxx.conf
```

终端中会显示二维码。iOS / Android 的 WireGuard App → 右上角 + → "从二维码扫描创建"。

也可以把 `.conf` 文件直接发送到手机上，用 "从文件或归档导入"。

## 验证连接

客户端连接后，在服务端执行：

```bash
# 查看连接状态（有 handshake 说明握手成功）
sudo wg show

# 从服务端 ping 客户端
ping 10.77.77.2

# 客户端应能 ping 通服务端和其他客户端
```

成功标志：
- `sudo wg show` 中对应 peer 出现 `latest handshake` 时间
- `transfer` 字段有非零的收发字节数
- 各个 IP 互相 ping 通

---

## 添加新客户端

已有服务端运行时，添加新客户端的流程：

### 1. 为新客户端生成密钥对

```bash
mkdir -p ~/wireguard-configs/clients
NUM=$(ls ~/wireguard-configs/clients/ 2>/dev/null | wc -l)
INDEX=$((NUM + 2))  # .1 是服务器，从 .2 开始

CLIENT_NAME="client${INDEX}"
wg genkey | tee ~/wireguard-configs/clients/${CLIENT_NAME}_private.key | wg pubkey > ~/wireguard-configs/clients/${CLIENT_NAME}_public.key
chmod 600 ~/wireguard-configs/clients/${CLIENT_NAME}_private.key
```

### 2. 在服务端配置中追加 Peer

```bash
# 读取旧配置，在末尾追加新的 [Peer] 段
echo "" | sudo tee -a /etc/wireguard/wg0.conf
echo "[Peer]" | sudo tee -a /etc/wireguard/wg0.conf
echo "# <备注>" | sudo tee -a /etc/wireguard/wg0.conf
echo "PublicKey = $(cat ~/wireguard-configs/clients/${CLIENT_NAME}_public.key)" | sudo tee -a /etc/wireguard/wg0.conf
echo "AllowedIPs = 10.77.77.${INDEX}/32" | sudo tee -a /etc/wireguard/wg0.conf
```

### 3. 重新加载（不中断已有连接）

```bash
sudo systemctl restart wg-quick@wg0
```

> 注意：`restart` 会短暂中断已有连接。如果不想中断，可用 `wg addconf`，但推荐直接用 restart（简单可靠）。

### 4. 生成客户端配置文件

按第九步模板生成 `.conf`，`PrivateKey` 用新生成的私钥，`Address` 用 `10.77.77.${INDEX}/24`。

### 5. 生成二维码发给用户

```bash
qrencode -t ANSIUTF8 < ~/wireguard-configs/clients/${CLIENT_NAME}.conf
```

---

## 故障排查

| 现象 | 可能原因 | 解决 |
|------|---------|------|
| 客户端连不上 | 防火墙/安全组没放行 51820/udp | `sudo ufw status` + 云控制台安全组 |
| 连上但 ping 不通 | IP 转发没开或 iptables 规则没生效 | `sudo sysctl net.ipv4.ip_forward` + `sudo iptables -t nat -L -v` |
| 连上一会后断开 | NAT 老化 | 客户端配置加 `PersistentKeepalive = 25` |
| wg show 无 handshake | 公网 IP 不对或端口被封 | 确认 Endpoint IP，换端口尝试 |
| 客户端能连但无法上网 | MASQUERADE 规则出口网卡不对 | 检查 `ip route show default` 的出口网卡名 |
| DNS 不工作 | 客户端 DNS 配置问题 | 确认客户端 config 中 `DNS = 223.5.5.5` |

## 安全提醒

- 私钥文件（`*_private.key`）权限必须是 600，目录 700
- 不要在聊天记录中完整显示私钥内容
- 客户端配置文件含私钥，传输时注意安全（二维码相对安全）
- 定期轮换密钥是良好实践，但这需要重新分发客户端配置

## 延伸阅读

> 详细参考：[架构与设计约束](references/architecture.md) — AllowedIPs 双重语义、NAT 三元组、密钥安全模型、PersistentKeepalive 选型依据
