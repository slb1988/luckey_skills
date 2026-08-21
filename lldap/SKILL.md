---
name: lldap
description: 团队 LLDAP 统一认证服务：查询用户/组成员关系 + 部署运维。当用户提到 lldap、LDAP、查某人是否在某组（如 p4-devops）、组成员或用户列表、LDAP bind/集成配置、统一认证账号，或要安装/搭建/部署 LLDAP、Docker LDAP 时触发。即使用户只说「xx 在 yy 组里么」「查一下 LDAP 账号」「帮我搭个 LDAP」也应触发。
---

# LLDAP：查询访问 + 部署运维

LLDAP 是团队统一认证目录（P4 / TeamCity / Jira / pyAutomation 共用账号）。两条路径：

- **查询 / 集成访问**（高频）——正文速查，更多见 [references/access.md](references/access.md)
- **部署 / 运维**（搭建、启停、排障）——[references/setup.md](references/setup.md)

## 现网实例

| 项 | 值 |
|---|---|
| LDAP | `192.168.2.13:3890`（无 SSL） |
| Web UI | `http://192.168.2.13:17170` |
| Base DN | `dc=example,dc=com` |
| 用户 OU | `ou=people,dc=example,dc=com` |
| 组 OU | `ou=groups,dc=example,dc=com` |

## 只读服务账号（查询用）

- 账号 `svcteamcity`（`uid=svcteamcity,ou=people,dc=example,dc=com`），**只读**，bind 后可搜全目录。核实「某人在不在某组」不需要 admin——任意有效账号 bind 即可读。
- 凭据在本机 `~/.env`：`LLDAP_HOST` / `LLDAP_PORT` / `LLDAP_BASE_DN` / `LLDAP_BIND_DN` / `LLDAP_BIND_PASSWORD`。
- **保密规则**：一律从 `~/.env` 读取，禁止把密码打印到对话、文档、git 仓库或记忆内容。pyAutomation `config/base.py` 里硬编码的默认值可能过期，以 `~/.env` 为准。
- 匿名 bind 被拒。

## 查某人在不在某组（标准做法）

```python
from pathlib import Path
from ldap3 import Server, Connection, SUBTREE

# 从 ~/.env 读凭据（不回显密码）
env = dict(l.split('=', 1) for l in Path('~/.env').expanduser().read_text().splitlines()
           if '=' in l and not l.startswith('#'))
s = Server(env['LLDAP_HOST'], port=int(env.get('LLDAP_PORT', '3890')), connect_timeout=5)
c = Connection(s, user=env['LLDAP_BIND_DN'], password=env['LLDAP_BIND_PASSWORD'], auto_bind=True)
c.search(f"ou=groups,{env['LLDAP_BASE_DN']}", '(cn=p4-devops)', search_scope=SUBTREE, attributes=['member'])
members = [str(v) for e in c.entries for v in e.entry_attributes_as_dict.get('member', [])]
print('xuzhiyang in group:', any('uid=xuzhiyang,' in m for m in members))
c.unbind()
```

## Schema 坑位

- 组成员在**组条目**的 `member` 属性（完整 DN 列表）；用户条目也有 `memberOf`。
- 用户条目**没有 `displayName`**，请求它会报 `invalid attribute type`；显示名用 `cn`。
- 组对象类 `groupOfUniqueNames`，用户 `person`（`inetOrgPerson`）。

## 注意：Jira 不能当组判据

Jira 同步了 LLDAP 用户，但**没同步 `p4-devops` 这类组**——Jira 里看不到不代表 LLDAP 没有。

## 路由

- 部署新实例 / 启停 / 备份 / 排障 / LDAPS / SMTP → [references/setup.md](references/setup.md)
- 扩展查询示例、GraphQL 管理控制台、Jira/TeamCity/SFTPGo 集成、凭据获取注意事项 → [references/access.md](references/access.md)
