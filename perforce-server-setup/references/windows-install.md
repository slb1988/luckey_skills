# Windows 安装与服务配置

下面的路径是示例，执行前替换为已确认的本机路径；示例服务名为 `Perforce`。
片段用于构建有失败处理、状态输出与回退的脚本，不是允许覆盖既有实例的一键安装器。

## 安装包与现有客户端是两个独立边界

已验证的 2024.1 安装包使用 WiX Burn 外层与 MSI payload。外层产品版本不等于实际 `p4d` 版本。
其引导程序检测到 Helix Core Apps 的 DVCS 组件后，会拒绝安装 Server；`/layout` 也执行该检测。
这个限制不能当作卸载 P4V 或清理现有 DVCS 数据的授权。

独立部署只使用原包内已验证的服务端程序，不执行 MSI 自定义操作、不复刻整套安装器：

| MSI File ID（本次版本） | 部署文件 | 作用 |
|---|---|---|
| `filp4dx64.exe` | `p4d.exe` | 初始化与离线维护 |
| `filp4sx64.exe` | `p4s.exe` | Windows 服务 |
| `filrelnotes.txt` | `relnotes.txt` | 版本说明 |
| `fili18nnotes.txt` | `i18nnotes.txt` | Unicode 说明 |

其他版本先检查 MSI File 表，不猜 payload 名称。不安装无关的 proxy/broker，不替换现有客户端。
这条路径是独立文件部署 + 服务注册，不能声称已完成原安装器的 MSI 注册或卸载集成。

## 1. 前置检查与提权

```powershell
$installer = 'C:\Staging\helix-core-server-x64.exe'
Get-AuthenticodeSignature -LiteralPath $installer
Get-CimInstance Win32_Service |
    Where-Object { $_.Name -match 'Perforce|Helix' -or $_.PathName -match 'p4[ds]\.exe' }
Get-NetTCPConnection -State Listen -LocalPort 1666 -ErrorAction SilentlyContinue
Get-NetIPAddress -AddressFamily IPv4
Get-NetConnectionProfile
```

验证签名状态及签署者，不只检查 `.exe` 扩展名。确认目标目录不存在/为空、磁盘空间和数据归属。
记录当前客户端二进制哈希与客户端设置；认证缓存的准确快照见 [认证隔离](auth-and-validation.md)。

提权脚本放在本机 staging，不放密码。让用户确认 UAC：

```powershell
$script = 'C:\Staging\install-server.ps1'
$process = Start-Process powershell.exe -Verb RunAs -PassThru -Wait `
    -ArgumentList "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$script`""
$process.ExitCode
```

同时核实脚本结果、服务与协议；不能把 launcher 的退出码或进程 ID 当成安装验收。
PowerShell 调外部程序还需检查 `$LASTEXITCODE`，`$ErrorActionPreference='Stop'` 不替代它。

## 2. 提取原包中的服务端

安装器支持布局且没有共存限制时，可按该版本支持的 layout 参数提取。
对于上述 Burn 包，可离线列出嵌入 CAB，再检查 CAB 中的 MSI；只处理已校验安装包，不执行未知 payload。

下面的 Python 片段按 CAB 头记录长度切出容器，**不硬编码包内偏移或“第二个 CAB 一定是 MSI”**：

```python
from pathlib import Path
import struct

installer = Path(r'C:\Staging\helix-core-server-x64.exe')
stage = Path(r'C:\Staging\p4-extracted')
stage.mkdir(parents=True, exist_ok=False)
data = installer.read_bytes()
offset = 0
count = 0
while True:
    position = data.find(b'MSCF', offset)
    if position < 0:
        break
    offset = position + 4
    if position + 36 > len(data):
        continue
    reserved, size = struct.unpack_from('<II', data, position + 4)
    if reserved != 0 or size < 36 or position + size > len(data):
        continue
    count += 1
    (stage / f'container-{count}.cab').write_bytes(data[position:position + size])
if not count:
    raise RuntimeError('No CAB candidates; inspect this installer format instead.')
```

用已安装的 7-Zip 列表/解压各容器，再解压确认过的 MSI。`MSCF` 扫描只是容器定位，不是内容真实性证明。
payload 可能叫 `a0`，不能只凭文件名判定格式；MSI 是 OLE Compound 文件。
Windows `expand` 的输出文件名可能沿用输入名，实际得到 MSI 却仍叫 `.cab`，应检查内容格式。

```powershell
$sevenZip = 'C:\Program Files\7-Zip\7z.exe'
& $sevenZip l 'C:\Staging\p4-extracted\container-2.cab' # 编号取自实际列表
& $sevenZip x 'C:\Staging\p4-extracted\container-2.cab' '-oC:\Staging\p4-payload'
# 确认 payload 为 MSI，并按需命名后：
& $sevenZip x 'C:\Staging\p4-payload\HelixCoreServer.msi' '-oC:\Staging\p4-files'
```

对得到的 `filp4dx64.exe` / `filp4sx64.exe` 再验 Authenticode 与 Perforce 签署者，然后运行 `filp4dx64.exe -V`。
只将这组原始文件部署到独立程序目录，例如 `C:\Program Files\Perforce Server`。

## 3. 新实例初始化

只有明确不存在旧数据时才执行。已有 `db.*`、运行中的实例或升级需求不走此分支。

```powershell
$bin = 'C:\Program Files\Perforce Server'
$root = 'D:\PerforceServer'
$bootstrapEndpoint = '127.0.0.1:1666'
New-Item -ItemType Directory -Path $root, "$root\logs", "$root\checkpoints"
& "$bin\p4d.exe" -r $root -p $bootstrapEndpoint `
    -L "$root\logs\p4d.log" -J "$root\logs\journal" -xi
if ($LASTEXITCODE -ne 0) { throw 'Unicode initialization failed' }
& "$bin\p4d.exe" -r $root -xD 'windows-p4'
if ($LASTEXITCODE -ne 0) { throw 'Server ID initialization failed' }
```

`-xi` 切换数据库的 Unicode 模式，不设置客户端全局字符集。Windows 此版本的默认大小写处理为 insensitive；不要据此推断 NAS/Linux 数据库的兼容性。

## 4. 服务账户、文件 ACL 与配置配对

已验证组合采用 `NT AUTHORITY\LocalService`，而不是给整个服务本地管理员身份：

| 对象 | 权限 |
|---|---|
| 程序目录 | 管理员部署；服务账户可读/执行，不授予写权限 |
| 新 `P4ROOT` 及子项 | SYSTEM/Administrators 完全控制；LocalService 修改；操作者按需只读 |
| 此服务的 `Parameters` 注册表键 | 已验证组合给 LocalService 可写权限，范围仅此键 |
| 仓库外凭据目录 | 当前操作者、SYSTEM/Administrators；不授予普通 Users 或服务账户读取 |

服务账户的 SID 是 `S-1-5-19`，SYSTEM 是 `S-1-5-18`，Administrators 是 `S-1-5-32-544`。
仅在新建目录上收紧继承；不要批量改旧仓库、盘根或 `Program Files` 的 ACL。

```powershell
$operatorSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& icacls.exe $root '/inheritance:r' '/grant:r' `
    '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' `
    '*S-1-5-19:(OI)(CI)M' "*$($operatorSid):(OI)(CI)RX"
if ($LASTEXITCODE -ne 0) { throw 'Data ACL configuration failed' }

$p4 = 'C:\Program Files\Perforce\p4.exe' # 先定位已安装客户端
$command = '"{0}\p4s.exe" -r "{1}" -p {2} -L "{1}\logs\p4d.log" -J "{1}\logs\journal"' -f $bin, $root, $bootstrapEndpoint
$credential = [PSCredential]::new('NT AUTHORITY\LocalService', [Security.SecureString]::new())
New-Service -Name Perforce -BinaryPathName $command -DisplayName 'Helix Core Server' `
    -StartupType Automatic -Credential $credential
& $p4 set -S Perforce "P4ROOT=$root" "P4PORT=$bootstrapEndpoint" `
    "P4LOG=$root\logs\p4d.log" "P4JOURNAL=$root\logs\journal"
if ($LASTEXITCODE -ne 0) { throw 'Service-scoped configuration failed' }

$key = 'HKLM:\SYSTEM\CurrentControlSet\Services\Perforce\Parameters'
$acl = Get-Acl $key
$sid = [Security.Principal.SecurityIdentifier]::new('S-1-5-19')
$acl.SetAccessRule([Security.AccessControl.RegistryAccessRule]::new(
    $sid, 'FullControl', 'ContainerInherit', 'None', 'Allow'))
Set-Acl $key $acl
Start-Service Perforce
(Get-Service Perforce).WaitForStatus('Running', [TimeSpan]::FromSeconds(30))
```

这是经过整体验证的配置组合；**没有单独证明注册表 FullControl 是最低必要权限**，不要将它扩展为全局注册表授权规则或把某次启动失败归因于唯一权限项。
启动后核对监听与 `p4 info` 的 root，再配置认证。

## 5. 认证完成后绑定网络

1. 用 [认证流程](auth-and-validation.md) 完成管理员引导和客户端状态恢复。
2. 确认目标 IP 属于本机；停服，同步更新 ImagePath 的 `-p` 与 `p4 set -S Perforce P4PORT=...`。
3. Windows PowerShell 5.1 可用 `Invoke-CimMethod Win32_Service.Change` 修改 ImagePath，检查 `ReturnValue=0`；不要假定 `Set-Service` 支持 `-BinaryPathName`。
4. 重启并验证实际 IP 监听、root 和认证，再创建防火墙规则。

防火墙同时限定程序、TCP 端口、本机地址、允许的来源网段及匹配当前网卡的 Profile：

```powershell
# 文档示例地址，不可原样部署；替换为本机 IP 和实际允许的网段。
$listenIp = '192.0.2.10'
$allowedSubnet = '192.0.2.0/24'
New-NetFirewallRule -Name 'PerforceServer-1666-LAN' -Direction Inbound -Action Allow `
    -Enabled True -Profile Private -Protocol TCP -LocalPort 1666 `
    -LocalAddress $listenIp -RemoteAddress $allowedSubnet -Program "$bin\p4s.exe"
```

同名服务/规则已存在时先检查归属，不覆盖。Profile 必须与实际网络匹配；不要为连通性而禁用防火墙或放行所有网络。
服务自启不等于地址固定；需要跨重启保持 LAN IP 时，单独确认 DHCP 保留/静态地址需求，不在安装中擅自改网卡。
