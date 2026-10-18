---
name: asus-merlin-vpn
description: Troubleshoot and configure ASUSWRT-Merlin / ASUSWRT-Merlin-KoolShare routers, especially KoolShare software-center VPN plugins such as fancyss / 科学上网 full, subscription import, SSR/SS+obfs node selection, dbus settings, DNS split-horizon failures, SSH-only recovery, and router-side connectivity tests. Use when the user asks to fix ASUS Merlin router VPN, compare local proxy nodes with router fancyss nodes, diagnose why 192.168.x.x router admin or 科学上网 tests fail, or preserve ASUS router troubleshooting knowledge.
---

# ASUS Merlin VPN

## Overview

Use this skill to operate an ASUS Merlin/KoolShare router carefully over SSH, repair fancyss state, and validate VPN behavior from the router itself. Keep credentials out of skill files; load them from the repository root `.env` file or `.env/asus-router.env` when that directory layout exists.

## Working Rules

- Prefer SSH over the web UI when the admin page is slow, unreachable, or likely to hang.
- Do not use the local computer's proxy or curl results as proof unless the user explicitly asks for client-side validation.
- Treat router operations as live infrastructure changes. Read current state before writing dbus keys, and keep changes limited to the VPN plugin unless the user asks otherwise.
- **Never manually modify iptables rules on the router.** fancyss writes complex nat/mangle/filter rules; incorrect changes can break SSH, Web UI, and LAN DNS simultaneously. If management access is lost, the only recovery may be a physical reboot.
- Never print passwords, subscription tokens, or full node credentials in final answers. Redact node passwords even when they look generic.
- Use `scripts/router_ssh.sh` for repeatable SSH access. It loads `ASUS_ROUTER_HOST`, `ASUS_ROUTER_USER`, and `ASUS_ROUTER_PASSWORD` from the repository root sensitive config.

## Workflow

1. Load credentials and access conventions from [access-and-secrets.md](references/access-and-secrets.md).
2. Snapshot router state before changing anything:
   ```sh
   scripts/router_ssh.sh 'dbus get ss_basic_enable; dbus get ss_basic_status; dbus get fss_node_current; ps w | grep -E "rss|ss-|xray|trojan|chinadns|dnsmasq" | grep -v grep'
   ```
3. For fancyss subscription import, node comparison, and start/stop commands, read [fancyss-workflow.md](references/fancyss-workflow.md).
4. For DNS and router-side validation, read [network-diagnostics.md](references/network-diagnostics.md).
5. For this user's RT-AC5300 case history and known findings, read [rt-ac5300-case.md](references/rt-ac5300-case.md).

## Safe Recovery

If router admin access or LAN DNS breaks after enabling the plugin, immediately stop fancyss over SSH if access is still available:

```sh
scripts/router_ssh.sh 'sh /koolshare/scripts/ss_config.sh stop; service restart_dnsmasq 2>/dev/null || /sbin/service restart_dnsmasq'
```

If SSH and Web UI are both unreachable, **physically reboot the router** (power off for 10 seconds, then power on). After reboot, fancyss is normally disabled unless auto-start is configured, which restores management access.

Then verify the admin page from the LAN using `curl --noproxy "*" -I http://$ASUS_ROUTER_HOST/Main_Login.asp` or the browser requested by the user.

## Common Commands

Use these only after reading the relevant reference file:

```sh
scripts/router_ssh.sh 'sh /koolshare/scripts/ss_node_subscribe.sh 3'
scripts/router_ssh.sh 'dbus set fss_node_current=4; dbus set fss_node_current_identity=<identity>; dbus set ss_basic_mode=2; dbus set ss_basic_enable=1; sh /koolshare/scripts/ss_config.sh start'
scripts/router_ssh.sh 'tail -160 /tmp/upload/ss_log.txt; ps w | grep -E "rss|ss-|xray|trojan|chinadns|dnsmasq" | grep -v grep'
```

<memory category="common-patterns">
- LAN 侧 DHCP 下发的 DNS（网页 LAN → DHCP Server → DNS Server 1/2）对应 nvram `dhcp_dns1_x` / `dhcp_dns2_x`。网页表单可能写不进 nvram（重启后被清空），可靠做法：SSH `nvram set dhcp_dns1_x=<ip>; nvram commit; service restart_dnsmasq`。
- `dhcp_dns2_x` 有意留空：存在备用 DNS 时客户端可能绕过首选 DNS，沉洞/过滤场景即失效。
- 验证要两层：nvram 回读 + 生效配置 `grep dhcp-option /etc/dnsmasq.conf`（应见 `dhcp-option=lan,6,<ip>`）。
- 客户端要等 DHCP 续约（重连 WiFi/重启）才换 DNS；手工指定 DNS 的设备（如本机 Mac 固定 223.5.5.5/114.114.114.114）不受路由器 DHCP 影响。
</memory>

## References

- [access-and-secrets.md](references/access-and-secrets.md): credential handling and SSH/browser access.
- [fancyss-workflow.md](references/fancyss-workflow.md): subscription, node schema, and plugin dbus workflow.
- [network-diagnostics.md](references/network-diagnostics.md): router-side tests and DNS failure patterns.
- [rt-ac5300-case.md](references/rt-ac5300-case.md): observed facts from the current RT-AC5300 troubleshooting session.
