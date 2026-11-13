# FluxDown QPKG 安装 / 升级流程

> 实测记录：2026-10-23 在 TS-453Dmini（x86_64，QTS 5.x）安装 FluxDown-Server v0.6.1。

## 1. 找到正确的安装包

上游仓库：https://github.com/zerx-lab/FluxDown

用 GitHub API 列 releases（本机 `curl` 是 admin 专属，普通用户直接跑会 `Permission denied`，用 python3 urllib 代替）：

```bash
python3 -c "
import urllib.request, json
req = urllib.request.Request('https://api.github.com/repos/zerx-lab/FluxDown/releases', headers={'User-Agent':'pi-agent'})
rels = json.load(urllib.request.urlopen(req, timeout=30))
r = rels[0]
print(r['tag_name'])
for a in r['assets']:
    if 'qnap' in a['name']:
        print(a['name'], a['browser_download_url'])
"
```

- **x86_64 NAS（TS-453Dmini 等 Intel/AMD 机型）**：`FluxDown-Server-<ver>-qnap-x64.qpkg`
- **ARM 机型**：`FluxDown-Server-<ver>-qnap-arm64.qpkg`
- 注意区分：带 `Server` 的才是 NAS 服务端；`FluxDown-<ver>-linux-x64.*` 是桌面客户端，`FluxDown-CLI-*` 是命令行。

## 2. 下载到 /share/Download/

**GitHub 直连非常慢**（实测 28MB 下到 84% 超 5 分钟超时）。本机有代理可用：`127.0.0.1:7890`（用前先探测端口是否开着，7897/7890 都可能）。用 python3 urllib + Range 头支持断点续传：

```bash
cd /share/Download && python3 - <<'EOF'
import urllib.request, os
url = 'https://github.com/zerx-lab/FluxDown/releases/download/v0.6.1/FluxDown-Server-0.6.1-qnap-x64.qpkg'
path = os.path.basename(url)
proxy = urllib.request.ProxyHandler({'http':'http://127.0.0.1:7890','https':'http://127.0.0.1:7890'})
opener = urllib.request.build_opener(proxy)
existing = os.path.getsize(path) if os.path.exists(path) else 0
headers = {'User-Agent':'pi-agent'}
if existing:
    headers['Range'] = f'bytes={existing}-'
req = urllib.request.Request(url, headers=headers)
mode = 'ab' if existing else 'wb'
with opener.open(req, timeout=60) as r, open(path, mode) as f:
    # 如果服务器忽略 Range 返回 200，需要重新覆盖写
    if existing and r.status == 200:
        f.close(); f = open(path, 'wb')
    while True:
        chunk = r.read(1<<20)
        if not chunk: break
        f.write(chunk)
print('Done, size =', os.path.getsize(path))
EOF
```

## 3. 校验 SHA256

release 里的 `SHA256SUMS-server.txt` 包含服务端包的校验值：

```bash
# 拉官方校验值（同样走代理）
python3 -c "
import urllib.request
proxy = urllib.request.ProxyHandler({'http':'http://127.0.0.1:7890','https':'http://127.0.0.1:7890'})
opener = urllib.request.build_opener(proxy)
req = urllib.request.Request('https://github.com/zerx-lab/FluxDown/releases/download/v0.6.1/SHA256SUMS-server.txt', headers={'User-Agent':'pi-agent'})
print(opener.open(req, timeout=30).read().decode())
" | grep qnap

# 本地计算对比
sha256sum /share/Download/FluxDown-Server-*-qnap-x64.qpkg
```

两边一致才能装。不一致说明下载损坏，删掉重新续传。

## 4. 安装

QPKG 安装必须 admin 权限。**不要在任何文件里记录真实密码**——向用户要，或让用户自己执行：

```bash
echo "<admin密码>" | sudo -S -u admin sh /share/Download/FluxDown-Server-<ver>-qnap-x64.qpkg
```

用户也可以在 App Center 手动安装：QTS 管理界面 → App Center → 右上角「手动安装」→ 选 Download 共享文件夹里的 .qpkg。

### 安装输出的正常现象

```
Install QNAP package on TS-NAS...
Firmware check is fine.
Link service start/stop script: fluxdown.sh
Set QPKG information in /etc/config/qpkg.conf
qinstall.sh: /usr/local/sbin/notify: /usr/local/bin/python2.7: bad interpreter: No such file or directory
```

**`notify: bad interpreter` 报错可忽略**——QNAP 桌面通知脚本还指向 python2.7（新 QTS 已移除），只影响 App Center 弹通知，不影响安装结果。

升级就是装新版包，流程完全相同，qinstall 会覆盖旧版本。

## 5. 验证

```bash
# qpkg.conf 注册信息
grep -A5 -i fluxdown /etc/config/qpkg.conf
# 应看到 Web_Port = 17800, Install_Path, Shell = .../fluxdown.sh

# 进程
ps aux | grep -i flux | grep -v grep
# 应有 fluxdown-agent --server 和 fluxdownd

# 端口
netstat -tln | grep 17800

# Web UI
python3 -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:17800/', timeout=10).status)"
# 200 即正常
```

## 6. 日常运维

```bash
Q=/share/CACHEDEV1_DATA/.qpkg/FluxDown
$Q/fluxdown.sh start|stop|restart    # 服务生命周期
cat $Q/fluxdown.pid                   # PID 文件
ls $Q/data/                           # 应用数据
```

开机自启由 `/etc/config/qpkg.conf` 的 RC_Number (101) 保证。

## 踩坑记录

| 坑 | 现象 | 解法 |
|----|------|------|
| curl 权限 | `/sbin/curl: Permission denied` | QNAP 把 curl 限成 admin 专属；普通用户用 python3 urllib |
| GitHub 慢 | 直连 28MB 下不完 | 走 127.0.0.1:7890 代理 + Range 断点续传 |
| sudo 密码 | 写在文档里的密码后来被改，全部失效还要清理 | 密码永不落盘，只留 `<admin密码>` 占位符 |
| notify 报错 | 安装末尾两条 bad interpreter | 正常现象，忽略 |
