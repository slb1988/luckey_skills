# 客户端隔离与分层验证

## 三类状态不是同一件事

| 状态 | 范围 | 控制方法 |
|---|---|---|
| 服务端配置 | 本实例数据库与服务设置 | root/port/log/journal、保护表、security |
| 客户端连接参数 | 一条命令或一个 P4 对象 | `-p/-u/-C`；`port/user/charset/password` |
| 客户端持久状态 | 注册表、环境、配置文件、ticket 文件 | 操作前准确快照；使用独立 ticket；验证本次影响 |

`p4 set -S Perforce` 设置服务，不等同于普通 `p4 set P4PORT=...`。
Unicode 客户端显式使用 `-C utf8`；非 Unicode 服务器按其模式连接。不要为了新服务器修改用户/系统全局 `P4CHARSET`。

## Windows 密码缓存的真实边界

已验证：在 Windows、全新 `security=0` 实例上，通过 P4Python `run_password('', password)` 设置密码，会将新密码的 MD5 写入：

```text
HKCU\SOFTWARE\Perforce\Environment\P4PASSWD
```

显式设置 `port/user/charset` 不阻止这个持久副作用；P4Python 不是独立于 P4 客户端配置的沙箱。
该观察不意味着所有安全等级/版本都会这样写，也不证明 `login` 会改同一项。
MD5 缓存仍是敏感认证材料，不得输出或提交。

### 精确保存与恢复

在密码操作前，由将执行该操作的同一 Windows 用户记录：

- 注册表路径、值名、**是否存在、原值及 RegistryValueKind**；不能只留总哈希。
- 至少保护上述 Perforce `P4PASSWD` 项，并核对用户环境中的 `P4PASSWD` 是否受本次操作影响。
- 保存原 `P4PORT/P4USER/P4CLIENT/P4CHARSET`，但不要把任何凭据值写入普通 transcript 或结果 JSON。
- 凭据快照优先留在同一控制进程内存；需跨提权进程时使用 DPAPI 或仅操作者可读的临时存储，完成后清理。

在 `finally` 中比较并恢复：原值存在则恢复其原值/类型，原本不存在则只移除本次新建值。
仅在当前值仍是本次写入的值时回退；发现并发修改，停止覆盖并报告。
**不能从进程 `P4PASSWD` 推断原注册表值**：进程环境可能陈旧，且明文、MD5 与 ticket 的表示不同。
恢复“当前有效密码”不等于恢复“原始持久配置”。

## 本机回环引导

新实例先只监听回环；防火墙还未对外开放。确认 `serverRoot` 指向新目录后：

1. 生成强随机密码，保存到仓库外的受限凭据文件；不经命令行参数或日志输出。
2. 在准确凭据快照保护下创建管理员并设密码。
3. 设置保护表，仅保留预期管理员的 super 权限；不要保留初始化的匿名/全员写权限。
4. 设置 `dm.user.noautocreate=2` 与 `security=3`。
5. 使用新密码完成 `login` 与 `login -s`，再检查 `depots`。
6. 恢复并核对旧客户端持久状态，最后才切换到用户指定的 LAN IP。

P4Python API 顺序示意；调用方负责上面的快照/恢复、权限和失败处理，不直接粘贴到现有生产实例：

```python
from P4 import P4

p4 = P4()
p4.port = bootstrap_endpoint
p4.user = admin_user
p4.client = 'setup-validation'
p4.charset = 'utf8'
p4.password = ''
p4.cwd = staging_directory
p4.ticket_file = private_ticket_file
try:
    p4.connect()
    info = p4.run_info()[0]
    assert info['serverRoot'].rstrip('\\/').lower() == expected_root.rstrip('\\/').lower()
    p4.save_user({'User': admin_user, 'Email': admin_email, 'FullName': admin_name})
    p4.run_password('', new_password)
    p4.password = new_password
    p4.save_protect({'Protections': [f'super user {admin_user} * //...']})
    p4.run_configure('set', 'dm.user.noautocreate=2')
    p4.run_configure('set', 'security=3')
    p4.run_login()
    p4.run_login('-s')
    p4.run_depots()
finally:
    if p4.connected():
        p4.disconnect()
```

邮件/姓名由部署需求提供，不伪造真实身份。不能用已有项目的工作区名进行写入测试。
给 P4Python 显式设置各连接参数和 `cwd`，并在部署子进程中隔离 `P4CONFIG/P4ENVIRO`；不改机器/用户全局值。

## 验证：从监听到真实认证

```powershell
$endpoint = '192.0.2.10:1666' # 替换为实际地址
$p4 = 'C:\Program Files\Perforce\p4.exe'
Get-CimInstance Win32_Service -Filter "Name='Perforce'"
Get-NetTCPConnection -State Listen -LocalPort 1666
Test-NetConnection -ComputerName '192.0.2.10' -Port 1666
& $p4 -p $endpoint -C utf8 -u $adminUser -c setup-validation info
```

不要将无密码也能成功的 `info` 当认证测试。用独立 ticket 文件和本次管理员凭据执行：

```text
login → login -s → depots → opened -a
```

可沿用上面的 P4Python 连接设置，只调用这些查询/认证命令，不重复创建用户、改密码或覆盖保护表。
检查实际返回值与异常，不只检查 launcher 退出码。初始实例的 `Client unknown` 不等于连接失败；`info` 不要求先创建客户端 spec。

重启服务后重复 TCP、`info` 和认证访问，并核对：

- 目标 root/serverID/version，而不是误连到用户默认的旧 P4PORT。
- 监听地址、端口与服务 PID 相符，不只是某个其他进程占用了 1666。
- 客户端持久设置与准确快照一致，原 P4V/p4 二进制未被覆盖。
- `opened -a` 没有本次遗留；纯查询不创建测试提交。

**测试范围**：本机访问自身 LAN IP 不经过真实远程入站路径，不能证明另一台机器可穿过防火墙。
异机测试要从获准的客户端执行同一 endpoint 的 TCP 与 P4 查询；未执行就明确写“仅本机验证”。
