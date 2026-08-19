# auto-server — TeamCity Configuration Reference

Machine: `auto-server` (192.168.2.13, Ubuntu 22.04)

## Version (2026-08-11 upgraded)

| Item | Value |
|---|---|
| TeamCity | **2026.1.3 (build 222742)** — upgraded from 2025.11 (208214) on 2026-08-11 |
| Required Java | **Java 21** (OpenJDK 21.0.11 at `/usr/lib/jvm/java-21-openjdk-amd64`; Corretto 21 also at `/data/tools/amazon-corretto-21.0.9.11.1-linux-x64`) |
| Data format | **1039** (was 1032 before upgrade — **NOT downgradable**) |
| DB | MySQL via docker container `mysql` (port 13306) |
| Upgrade backup | `/mnt/disk2/TeamCity/.BuildServer/backup/TeamCity_Before_Upgrade_20260811_184822.zip` + manual mysqldump `/data/backup/teamcity_upgrade_20260811/teamcity_db.sql` |

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

> **Java 21 required (since 2026.1.3).** Start scripts resolve `java` from PATH/JAVA_HOME;
> before 2026-08-11 the server was running under Java 17. Always pass Java 21 explicitly:
> `JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 TEAMCITY_JRE=/usr/lib/jvm/java-21-openjdk-amd64`.
> `~/.profile` also sets JAVA_HOME/TEAMCITY_JRE to Corretto 21 (`/data/tools/amazon-corretto-21.0.9.11.1-linux-x64`).

```bash
# Stop everything
cd /data/TeamCity && bash bin/runAll.sh stop

# Start everything (background with nohup recommended)
cd /data/TeamCity && JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 TEAMCITY_JRE=/usr/lib/jvm/java-21-openjdk-amd64 \
  nohup bash bin/runAll.sh start > /tmp/teamcity-startup.log 2>&1 &
```

`runAll.sh` delegates to:
- `sh ./teamcity-server.sh {start|stop}` — TeamCity server
- `sh ./agent.sh {start|stop}` — Build agent (from `../buildAgent/bin`)

Individual control:
```bash
# Server only
cd /data/TeamCity && JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 TEAMCITY_JRE=/usr/lib/jvm/java-21-openjdk-amd64 bash bin/teamcity-server.sh {start|stop|status}

# Agent only
cd /mnt/disk2/TeamCity/buildAgent/bin && bash agent.sh {start|stop}
```

Verify the running JVM (not just the server log):
```bash
ss -tlnp | grep 8111            # note the java PID
sudo readlink /proc/<PID>/exe   # should be .../java-21-openjdk-amd64/bin/java
```
> Gotcha: `ps aux | grep Bootstrap` may also match the **Jira** JVM (`/usr/lib/jvm/java-17...`, atlassian-jira, port 8083). Match on `teamcity-startup.properties` instead.

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

DB runs in docker container `mysql` (port 13306 → container 3306). Root password is in the container env (`docker inspect mysql | grep MYSQL_ROOT_PASSWORD`). Backup:
```bash
docker exec mysql sh -c 'mysqldump -uroot -p<pass> --single-transaction --routines --triggers --databases teamcity_db' > backup.sql
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

## Upgrade log — 2025.11 (208214) → 2026.1.3 (222742), 2026-08-11

### Why
- TeamCity was compromised via **XStream deserialization RCE** (ysoserial CommonsCollections gadget, `TiedMapEntry`/`BasicDataSource`, attempts at 16:15:00 / 16:30:43 / 17:40:31 on 2026-08-11) through the **frp public tunnel** (server `81.68.211.31:7000`, TeamCity mapped to public `:18082`). The miner was dropped right after the first attempt. Upgrade was done to close the vulnerability.
- frp mapping for TeamCity (18082) has since been **removed** from `/etc/frp/frpc.toml` (backup `.bak.20260811184217`); agent 18080 / jira 18081 kept.

### Steps taken
1. Java 17 → 21: stop server, start with `JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 TEAMCITY_JRE=/usr/lib/jvm/java-21-openjdk-amd64 sh teamcity-server.sh start` (see Service management above).
2. First boot after upgrade shows a **data-format upgrade page** (1032 → 1039, MySQL). This is expected, not an error. **Backup first** (see below), then confirm in Web UI.
3. Upgrade itself was confirmed via Web UI; server restarted automatically and came up on Java 21 again.

### Backup (taken 2026-08-11 18:48, pre-upgrade)
- TeamCity built-in: `/mnt/disk2/TeamCity/.BuildServer/backup/TeamCity_Before_Upgrade_20260811_184822.zip`
- Manual mysqldump: `/data/backup/teamcity_upgrade_20260811/teamcity_db.sql` (1.4 GB)
- Data dir copy started but not finished (40 GB) — built-in zip + SQL dump were sufficient.

### Agents after upgrade
- Agents must run Java 21 after upgrade; agents on older Java connect but **cannot run new builds**. Windows agents (WinTest1 etc.) need their agent JVM updated.
- The old bogus agent `0252e8bf1f57` (version "pre5.0") registered during the attack was auto-unregistered after 90 s; if seen again it's malicious.
