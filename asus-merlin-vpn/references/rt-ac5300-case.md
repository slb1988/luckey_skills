# RT-AC5300 Case Notes

## Hardware And Firmware

Observed router:

```text
Model: ASUS RT-AC5300
Firmware family: ASUSWRT-Merlin-KoolShare
Kernel: Linux 2.6.36.4brcmarm armv7l
Plugin: 科学上网 full / fancyss_arm_full
Observed local plugin version: 3.5.30
```

## Access

- Admin host: use `ASUS_ROUTER_HOST` from sensitive config.
- SSH is available and preferred for recovery.
- Web admin reachability is checked with `/Main_Login.asp`.
- BusyBox environment: commands such as `id` may be unavailable.

## Subscription State

Observed after reinstall:

- `ss_basic_enable=0`.
- No running `ss`, `rss`, `xray`, `v2ray`, or `trojan` processes.
- `ss_online_links` was empty until restored.
- Running `sh /koolshare/scripts/ss_node_subscribe.sh 3` successfully parsed 143 SSR/SS-family nodes.
- Newer node storage uses `fss_node_<id>` Base64 JSON and `fss_node_current_identity`.

## Known Nodes

Two user-confirmed working local-client nodes correspond to router nodes:

```text
香港01: fss_node_current=4, server cn01.somethingstranges.com, port 8101, method chacha20-ietf, obfs http_simple, protocol origin
香港02: fss_node_current=5, server cn01.somethingstranges.com, port 8102, method chacha20-ietf, obfs http_simple, protocol origin
```

Do not store or print node passwords in this reference. Load identities and credentials from sensitive config.

## Findings From Troubleshooting

- The router web UI became reachable again after stopping/recovering plugin state.
- Initial fancyss startup used China DNS over DoT: `tls://dns.alidns.com@223.5.5.5`.
- That DNS mode caused client and router DNS stalls in the observed environment.
- Switching China DNS to UDP/TCP and then running `stop` followed by `start` regenerated `/tmp/chinadns_ng.conf`.
- With DNS repaired, node domain resolution returned an IP from router-side `nslookup`.
- Router-side socks tests through `127.0.0.1:23456` still failed for the observed HK nodes, while local-client versions of the nodes were reported working by the user.
- Logs repeatedly showed `rss-local` / `rss-redir` failing to resolve server name and then exiting; always verify process liveness after startup, not just plugin log completion.

## Practical Hypotheses

Prioritize these explanations when the router still fails but local clients work:

- Router DNS runtime differs from the client and `rss-local` cannot resolve the server after fancyss DNS hijack rules are installed.
- The older armv7 `rss-local/rss-redir` binary may handle SS + simple-obfs differently than the user's local client.
- The node server may block or drop traffic from the router WAN path while accepting another client path.
- The plugin test may be false-negative, but only accept that if router-side socks tests return a non-mainland exit.

## 2026-08-01 Session Findings

### What was done

1. Confirmed SSH username is `slb1988` and password matches Web login; OpenSSH from macOS repeatedly failed while `vssh` succeeded, likely due to router-side rate limiting or authentication negotiation differences.
2. Initial state: `ss_basic_enable=0`, only `dnsmasq` running, `fss_node_current=5`.
3. Started fancyss with default `chinadns-ng` DNS scheme. `rss-local`/`rss-redir` started but did **not** bind ports; manual run showed `failed to resolve server name` for the SSR node domain `cn01.somethingstranges.com`.
4. Root cause: `rss-local` could not resolve the node domain through the router's DNS runtime even though `nslookup` returned an IP. This prevented `chinadns-ng`'s trust-DNS-over-socks5 path from working, so Google domains failed and the plugin self-test reported "代理服务器出口地址检测失败".
5. Workaround: changed both node 4 and node 5 `server` fields from `cn01.somethingstranges.com` to the resolved IP `206.109.71.215` via `dbus set fss_node_<id>=$(base64 ...)`.
6. After switching DNS scheme to `smartdns` (`ss_basic_chng`/`ss_basic_dns_plan=2`) and restarting, the plugin self-test passed: exit IP `118.140.56.80/81` overseas, node IP `206.109.71.215`.
7. LAN clients could access Google/overseas sites. Router self-origin `curl` to Google still timed out on DNS; Web UI built-in test also reported failure.

### Important outcomes and warnings

- **LAN proxy works; router self-management is fragile.** Once fancyss started, router-side SSH/Web management eventually became unreachable. The exact trigger is unconfirmed, but fancyss writes extensive `iptables` nat/mangle/filter rules. **Do not manually modify these rules unless you have a rollback path.**
- **Avoid SSH-only recovery assumptions.** When both SSH and Web UI are unreachable, the only recovery is a physical router reboot (power cycle). After reboot, fancyss is normally disabled unless auto-start is set.
- **IP-based node workaround is not robust.** If `cn01.somethingstranges.com` changes IP, the node will break. A better long-term fix is to make `rss-local` resolve the node domain correctly (e.g., via `/etc/hosts` or fixing the DNS scheme), but any DNS/iptables change must be tested while preserving management access.
- **If management breaks while VPN is working:** do not continue tweaking. Power-cycle the router to restore access, then re-evaluate.

### Open questions

- Why does `rss-local` fail to resolve the node domain when `nslookup 127.0.0.1` succeeds?
- Which exact `iptables` rule blocks router-self management traffic after fancyss starts?
- Does `smartdns` properly serve router-self DNS queries for foreign domains, or only LAN clients?

### Safe recovery checklist

If router admin access breaks after enabling fancyss:

1. Try LAN Web UI first: `http://192.168.50.1/Main_Login.asp`.
2. If Web UI works, disable fancyss in the plugin page.
3. If Web UI fails, **physically reboot the router** (power off 10 seconds, power on).
4. After reboot, verify SSH and Web UI before re-enabling fancyss.
5. Never change iptables or DNS configuration without a tested rollback command or reboot plan.
