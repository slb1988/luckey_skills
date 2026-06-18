# Host Fingerprint — Machine Identity Reference

When controlling multiple machines via this skill, always check the hostname first to confirm which machine you're operating on. The fingerprint below is the canonical identity for this machine.

## auto-server

| Property | Value |
|---|---|
| Hostname | `auto-server` |
| FQDN | `auto-server` (no domain) |
| OS | Ubuntu 22.04, Linux 6.8.0-111-generic, x86_64 |
| Primary IP | `192.168.2.13/23` (enp13s0) |
| TeamCity install | `/data/TeamCity/` |
| TeamCity data dir | `/mnt/disk2/TeamCity/.BuildServer/` |
| TeamCity web URL | `http://192.168.2.13:8111/` |
| TeamCity version | 2025.11 (build 208045) |
| Java home | `/usr` (system JDK, picked up automatically) |

## Adding a new machine

When onboarded to a new host:
1. Run `hostname` to get the hostname
2. Discover TeamCity install with `find / -name "teamcity-server.sh" 2>/dev/null`
3. Read `<install>/conf/teamcity-startup.properties` for `teamcity.data.path`
4. Record IP: `ip addr show | grep "inet " | grep -v 127.0.0.1`
5. Add a new section above following the same table format
6. At runtime, `hostname` → match section → load that machine's reference file
