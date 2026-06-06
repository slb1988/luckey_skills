---
name: mihomo-proxy-setup
description: 在新的 Ubuntu 服务器上安装配置 mihomo (Clash Meta) 代理客户端翻墙。当用户提到"装代理"、"翻墙"、"科学上网"、"proxy"、"VPN"、"clash"、"mihomo"、"配置代理"、"新服务器要翻墙"、"访问 Google"、"GitHub 太慢"、"连不上外网"、"装梯子"时触发。即使用户只是抱怨某个命令超时或下载失败（如 pip/npm/docker pull/git clone 连不上），也应考虑使用此 Skill。
---

# Mihomo (Clash Meta) 代理安装与配置

在 Ubuntu 服务器上快速部署 mihomo 代理，支持 Clash 格式订阅，实现科学上网。

## 为什么选 mihomo 而不是 v2rayA

- 原生支持 Clash YAML 订阅，不需要格式转换
- 协议覆盖广：SS、SSR、VMess、VLESS、Trojan、Hysteria、Tuic 等
- 内置规则分流引擎，国内直连国外走代理，零额外配置
- 配置即文件，纯 YAML，不依赖 Web UI 或数据库

---

## 安装步骤

### 1. 下载 mihomo 二进制

GitHub 在墙内无法直连。需要用户通过其他途径将 `.gz` 文件传到服务器上，或通过镜像下载。

```bash
# 确认架构
dpkg --print-architecture   # 通常是 amd64

# 从 GitHub Releases 下载（需翻墙或镜像）
# https://github.com/MetaCubeX/mihomo/releases
# 文件名格式：mihomo-linux-amd64-v1.19.x.gz
```

### 2. 安装二进制

```bash
cd ~
gunzip -k mihomo-linux-amd64-*.gz
chmod +x mihomo-linux-amd64-*
sudo cp mihomo-linux-amd64-* /usr/local/bin/mihomo
mihomo -v   # 验证
```

### 3. 准备 GeoIP / GeoSite 数据

mihomo 需要 geoip.dat 和 geosite.dat 做规则分流。如果机器上已有 xray，可以直接复用：

```bash
sudo mkdir -p /etc/mihomo

# 方式 A：复用 xray 的 geodata
sudo cp /usr/local/share/xray/geoip.dat /etc/mihomo/
sudo cp /usr/local/share/xray/geosite.dat /etc/mihomo/

# 方式 B：手动下载（需翻墙或镜像）
# https://github.com/Loyalsoldier/v2ray-rules-dat/releases
```

### 4. 写配置文件

详见 `references/config-template.yaml`，这是一份开箱即用的配置模板。

核心要做的事：将 `proxy-providers.my-sub.url` 替换为用户实际的 **Clash 订阅地址**（选 "Clash/stash简单规则" 格式）。

```bash
sudo nano /etc/mihomo/config.yaml
# 粘贴模板内容，替换订阅地址
```

如果订阅 URL 本身也被墙，无法直接拉取，可以在能翻墙的设备上访问订阅地址，把返回的 YAML 保存为文件传到服务器，然后改用 `type: file`：

```yaml
proxy-providers:
  my-sub:
    type: file
    path: ./proxies/my-sub.yaml
    health-check:
      enable: true
      interval: 300
      url: https://www.gstatic.com/generate_204
```

### 5. 创建 systemd 服务

```bash
sudo tee /etc/systemd/system/mihomo.service > /dev/null << 'EOF'
[Unit]
Description=mihomo Daemon, Another Clash Kernel.
After=network.target NetworkManager.service systemd-networkd.service iwd.service

[Service]
Type=simple
LimitNPROC=500
LimitNOFILE=1000000
CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_RAW CAP_NET_BIND_SERVICE CAP_SYS_TIME CAP_SYS_PTRACE CAP_DAC_READ_SEARCH CAP_DAC_OVERRIDE
AmbientCapabilities=CAP_NET_ADMIN CAP_NET_RAW CAP_NET_BIND_SERVICE CAP_SYS_TIME CAP_SYS_PTRACE CAP_DAC_READ_SEARCH CAP_DAC_OVERRIDE
Restart=always
ExecStartPre=/usr/bin/sleep 1s
ExecStart=/usr/local/bin/mihomo -d /etc/mihomo
ExecReload=/bin/kill -HUP $MAINPID

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now mihomo
```

### 6. 验证

```bash
# 检查服务状态
sudo systemctl status mihomo

# 检查端口监听
ss -tlnp | grep -E '7890|7891|7892'

# 测试代理
curl -x http://127.0.0.1:7892 -s --connect-timeout 10 https://www.google.com -o /dev/null -w "HTTP: %{http_code}\n"
```

---

## 代理端口

| 端口 | 协议 | 说明 |
|------|------|------|
| 7890 | Mixed (HTTP+SOCKS5) | 推荐使用 |
| 7891 | SOCKS5 | 纯 SOCKS5 |
| 7892 | HTTP | 纯 HTTP |

---

## 使用代理

### 终端环境变量（当前会话）

```bash
export https_proxy=http://127.0.0.1:7892
export http_proxy=http://127.0.0.1:7892
export all_proxy=socks5://127.0.0.1:7890
export no_proxy=localhost,127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,.cn
```

### 持久化到 .bashrc

```bash
cat >> ~/.bashrc << 'EOF'
# mihomo proxy
export https_proxy=http://127.0.0.1:7892
export http_proxy=http://127.0.0.1:7892
export all_proxy=socks5://127.0.0.1:7890
export no_proxy=localhost,127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,.cn
EOF
source ~/.bashrc
```

### 各工具单独配置

```bash
# git
git config --global http.proxy http://127.0.0.1:7892
git config --global https.proxy http://127.0.0.1:7892

# docker
sudo mkdir -p /etc/systemd/system/docker.service.d
sudo tee /etc/systemd/system/docker.service.d/proxy.conf << 'EOF'
[Service]
Environment="HTTP_PROXY=http://127.0.0.1:7892"
Environment="HTTPS_PROXY=http://127.0.0.1:7892"
Environment="NO_PROXY=localhost,127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
EOF
sudo systemctl daemon-reload && sudo systemctl restart docker

# pip
pip install --proxy http://127.0.0.1:7892 <package>

# curl 单次
curl -x http://127.0.0.1:7892 https://example.com
```

---

## 日常管理命令

```bash
sudo systemctl start mihomo        # 启动
sudo systemctl stop mihomo         # 停止
sudo systemctl restart mihomo      # 重启
sudo systemctl status mihomo       # 状态
sudo journalctl -u mihomo -f       # 实时日志
sudo kill -HUP $(pidof mihomo)     # 热重载配置（不断连接）
mihomo -t -d /etc/mihomo           # 检查配置语法
```

---

## 故障排查

| 症状 | 排查方式 |
|------|----------|
| 服务起不来 | `sudo journalctl -u mihomo -n 50` 看报错 |
| 端口没监听 | `ss -tlnp \| grep 7890` — 多半是 YAML 语法错 |
| 配置语法错 | `mihomo -t -d /etc/mihomo` 测试 |
| 订阅拉不下来 | 订阅 URL 本身被墙，改用 `type: file` 手动放文件 |
| 连上了但打不开 | 节点可能全挂，换订阅或检查 health-check 日志 |
| DNS 污染 | 确认 config 里 dns.fallback 配了境外 DNS |

---

## 卸载旧的 v2rayA（如有）

如果之前装过 v2rayA 且不再使用：

```bash
sudo systemctl stop v2raya
sudo systemctl disable v2raya
sudo apt purge -y v2raya
sudo rm -rf /etc/v2raya/ /var/lib/v2raya/ /root/.local/share/v2raya/
sudo rm -f /etc/apt/sources.list.d/v2raya.list /etc/apt/keyrings/v2raya.asc
```

v2rayA 的主要问题：不支持 Clash YAML 订阅、cipher 名兼容性差、obfs 支持不完善。

---

## 文件布局速查

| 文件 | 路径 |
|------|------|
| mihomo 二进制 | `/usr/local/bin/mihomo` |
| 主配置 | `/etc/mihomo/config.yaml` |
| GeoIP 数据 | `/etc/mihomo/geoip.dat` |
| GeoSite 数据 | `/etc/mihomo/geosite.dat` |
| 订阅缓存 | `/etc/mihomo/proxies/my-sub.yaml` |
| systemd 服务 | `/etc/systemd/system/mihomo.service` |
