# LLDAP 访问与集成

现网实例的连接参数、查询方法，以及各服务接入 LLDAP 的实操经验。SKILL.md 正文已给出最常用的「查某人在不在某组」做法，本文件覆盖其余场景。

## 连接信息

```
Host:    192.168.2.13
Port:    3890（无 SSL）
Base DN: dc=example,dc=com
用户 OU: ou=people,dc=example,dc=com
组 OU:   ou=groups,dc=example,dc=com
Bind DN: uid=svcteamcity,ou=people,dc=example,dc=com（只读服务账号）
```

凭据在本机 `~/.env`（`LLDAP_*` 五个键），读取方法见 SKILL.md 正文示例。**不要**在输出中回显 `LLDAP_BIND_PASSWORD`。

## 查询示例

以下片段假设已按 SKILL.md 正文的方式建立了 `c`（已 bind 的 Connection）。

### 列出组全部成员

```python
c.search('ou=groups,dc=example,dc=com', '(cn=p4-devops)',
         search_scope=SUBTREE, attributes=['member'])
members = [str(v) for e in c.entries for v in e.entry_attributes_as_dict.get('member', [])]
# member 是完整 DN：uid=xxx,ou=people,dc=example,dc=com
```

### 查某用户属于哪些组（memberOf）

```python
c.search('ou=people,dc=example,dc=com', '(uid=xuzhiyang)',
         search_scope=SUBTREE, attributes=['uid', 'cn', 'mail', 'memberOf'])
# 注意：不要请求 displayName——LLDAP 用户条目没有这个属性，会报 invalid attribute type
```

### 列全部用户 / 全部组

```python
c.search('ou=people,dc=example,dc=com', '(objectClass=person)', search_scope=SUBTREE, attributes=['uid', 'cn', 'mail'])
c.search('ou=groups,dc=example,dc=com', '(objectClass=groupOfUniqueNames)', search_scope=SUBTREE, attributes=['cn', 'member'])
```

## 凭据注意事项（历史教训）

- pyAutomation `backend/server/config/base.py` 里 `LDAP_BIND_PASSWORD` 的**硬编码默认值可能过期**（bind 返回 invalidCredentials），真实值以 auto-server 部署环境变量 / 本机 `~/.env` 为准。
- 拿不到 LLDAP 凭据时的旁证：pyAutomation `base.py` 的 `DEBUG_GROUP_LDAP_SYNC_MAP` 把本地组 `devops` 映射为 LLDAP 组 `p4-devops`；P4 侧（192.168.2.13:1666）`devops` 组成员名单可作参考——**非权威**，两边靠人工保持一致。
- Windows 本机直连 SSH `dev@192.168.2.13` 被 publickey 拒绝，取环境变量需换路径。

## 管理操作（写入）

- **Web UI**：`http://192.168.2.13:17170`，用 admin 或 `lldap_admin` 组成员账号登录。
- **pyAutomation 账号管理控制台**（推荐）：`server/applications/lldap_admin/` 封装了 LLDAP GraphQL 管理 API（`:17170`），用户/组的增删与加人进组都走这里；写操作以当前登录人的 LLDAP 会话执行，须 `lldap_admin` 成员，无会话时回退 svcteamcity 只读。
- 本 skill 的只读账号**不能写**；要加人/建组，走 Web UI 或 pyAutomation 控制台。

## 各服务集成要点

### Jira（192.168.2.13:8083）

Jira 接 LLDAP 做用户目录的关键点（详见 `luckey/02_notes/toolchain/jira.md`）：

- Bind DN 必须填**完整 DN**（如 `uid=svcteamcity,ou=people,dc=example,dc=com`），只填 `svcteamcity` 不行
- Base DN `dc=example,dc=com`，Additional User DN `ou=people`，Additional Group DN `ou=groups`
- User Name Attribute `uid`；User Object Filter `(objectClass=person)`；Group Object Filter `(objectClass=groupOfUniqueNames)`
- ⚠️ Jira 只同步了用户，**没同步 `p4-devops` 这类业务组**——不能拿 Jira 的组列表当 LLDAP 判据

### TeamCity

- 用同一个服务账号 `svcteamcity` 接入（2026-07 完成配置并禁止游客登录）
- 团队约定：成员用 **P4 账号密码**登录 TeamCity（P4 与 LLDAP 密码已统一）
- LLDAP 是密码 bind 协议，无 token 替代方案

Windows 盘 FTP 想统一用 LLDAP 账号：微软 IIS FTP 只认 Windows 本地账户或 AD 域，不支持通用 LDAP Bind，接不进 LLDAP；pGina 也无效（IIS FTP 走 LogonUser 网络登录，不经过交互式登录）；LLDAP 只存密码哈希不可导出，"同步成 Windows 本地账户"路线不通。已确认可行路径：用 SFTPGo（Windows 原生服务，FTP/FTPS/SFTP/WebDAV 一体）替代 IIS FTP，其内置 LDAP 用 `bind_as_user: true`，用户 DN 模式 `uid=%username%,ou=people,<base dn>`，首次登录自动建档；盘符权限用 SFTPGo 的 per-user/per-group virtual folder 映射（如 D:\、E:\ 分用户设只读/读写）。
