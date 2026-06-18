# auto-server — TeamCity Configuration Reference

Machine: `auto-server` (192.168.2.13, Ubuntu 22.04)

## Directory layout

| Path | Purpose |
|---|---|
| `/data/TeamCity/` | TeamCity installation (binaries) |
| `/data/TeamCity/bin/` | Scripts: `runAll.sh`, `teamcity-server.sh`, `teamcity-server-restarter.sh` |
| `/data/TeamCity/conf/` | Server config XMLs, `teamcity-startup.properties` |
| `/data/TeamCity/logs/` | Server logs |
| `/mnt/disk2/TeamCity/.BuildServer/` | **Data directory** (configured in startup props) |
| `/mnt/disk2/TeamCity/.BuildServer/config/` | Runtime config files |
| `/mnt/disk2/TeamCity/.BuildServer/system/artifacts/` | Build artifacts storage |
| `/mnt/disk2/TeamCity/buildAgent/` | Default build agent |
| `/mnt/disk2/TeamCity/buildAgent/conf/buildAgent.properties` | Agent config |

## Data directory

Defined in `/data/TeamCity/conf/teamcity-startup.properties`:
```
teamcity.data.path=/mnt/disk2/TeamCity/.BuildServer
```

This is critical — the installation is under `/data/TeamCity/` but all runtime data lives on `/mnt/disk2/`. When dealing with config files, logs, or the LDAP properties, the correct path is under `/mnt/disk2/TeamCity/.BuildServer/`, NOT `/data/TeamCity/`.

## Service management

The canonical way to start/stop everything (server + agent):

```bash
# Stop everything
cd /data/TeamCity && bash bin/runAll.sh stop

# Start everything (background with nohup recommended)
cd /data/TeamCity && nohup bash bin/runAll.sh start > /tmp/teamcity-startup.log 2>&1 &
```

`runAll.sh` delegates to:
- `sh ./teamcity-server.sh {start|stop}` — TeamCity server
- `sh ./agent.sh {start|stop}` — Build agent (from `../buildAgent/bin`)

Individual control:
```bash
# Server only
cd /data/TeamCity && bash bin/teamcity-server.sh {start|stop|status}

# Agent only
cd /mnt/disk2/TeamCity/buildAgent/bin && bash agent.sh {start|stop}
```

## Server URLs & Ports

| Port | Purpose |
|---|---|
| 8111 | Web UI (HTTP) |
| 8105 | Tomcat shutdown port |

Root URL: `http://192.168.2.13:8111/` (configured in `main-config.xml`)

## Database

MySQL on same host (`/mnt/disk2/TeamCity/.BuildServer/config/database.properties`):
```
connectionUrl=jdbc:mysql://192.168.2.13:13306/teamcity_db
connectionProperties.user=root
```

## Key config files

| File | Purpose |
|---|---|
| `main-config.xml` | Server UUID, root URL, encryption, artifact limits, VCS settings |
| `database.properties` | DB connection |
| `ldap-config.properties` | LDAP integration (see `references/ldap-config.md`) |
| `auth-config.xml`  | Authentication modules (where LDAP gets registered) |
| `roles-config.xml` | Role/permission mappings |
| `nodes-config.xml` | Cluster node configuration |
| `backup-config.xml` | Backup schedule |
| `build-queue-priorities.xml` | Build queue priority rules |
| `disabled-plugins.xml` | Disabled plugin list |
| `ntlm-config.properties` | NTLM/Windows auth |

## Auth modules

Directory: `/mnt/disk2/TeamCity/.BuildServer/config/_auth/`

| File | Purpose |
|---|---|
| `default.xml` | Default auth (built-in user/password) |
| `ldap.xml` | LDAP auth module registration |
| `ldap-ntlm.xml` | LDAP+NTLM combined |
| `nt-domain.xml` | NT domain auth |

## Runtime verification

Check if running:
```bash
ps aux | grep -E "teamcity|TeamCity" | grep -v grep
```

Expected processes (at least):
- `teamcity-server.sh _start_internal`
- `teamcity-server-restarter.sh run`
- Java process with `org.apache.catalina.startup.Bootstrap start` (catalina.base=/data/TeamCity)
- Java process with `jetbrains.buildServer.agent.AgentMain` (build agent)

Check logs:
```bash
# Server log
tail -f /mnt/disk2/TeamCity/logs/teamcity-server.log
# Also in installation logs dir (symlinks or dups)
tail -f /data/TeamCity/logs/teamcity-server.log
```

## LLDAP server (Docker)

LLDAP runs as a Docker container providing LDAP auth for TeamCity:

| Property | Value |
|---|---|
| Container | `lldap/lldap:stable` |
| LDAP port | 3890 (plain, no TLS) |
| Web UI | http://192.168.2.13:17170 |
| Base DN | `dc=example,dc=com` |
| Admin user | `uid=admin,ou=people,dc=example,dc=com` |
| User objectClass | `inetOrgPerson` |
| Group objectClass | `groupOfUniqueNames` |
| Member attribute | `uniqueMember` |
| No displayName | Use `cn` for full name |

LLDAP has no TLS/LDAPS support — TeamCity's "insecure" warning is cosmetic and can be ignored.

Query users directly with Python:
```bash
python3 -c "import ldap3; s=ldap3.Server('192.168.2.13',port=3890); c=ldap3.Connection(s,'uid=admin,ou=people,dc=example,dc=com','admin123!',auto_bind=True); c.search('ou=people,dc=example,dc=com','(objectClass=*)',attributes=['*']); [print(e.entry_dn) for e in c.entries]"
```

## Plugins

96 plugins loaded including: ldap, jetbrains.git, docker-support, kubernetes-executor, unreal-engine (1.3.4), slackNotifier, and more. The `ldap` plugin is bundled (ver:208045).
