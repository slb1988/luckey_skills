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

## VPN Capability Limits

- **No WireGuard on this router**: KoolShare RT-AC5300 stays on kernel 2.6.36; Merlin's native WireGuard requires 388.x firmware which does not exist for this KoolShare model, and wireguard-go via Entware is impractical on this kernel. Do not propose router-level WG peering.
- **No inbound exposure either**: home broadband is likely CGNAT (no public IP), so port-forwarding LAN services (e.g. printer 9100/631) to the internet is both infeasible and unsafe.
- Consequence: to bring LAN-only devices into the private WireGuard network, use a dual-homed relay that is both a WG peer and on the home LAN (e.g. QNAP NAS 10.77.77.6 running a CUPS container), not the router.

## Access

- Admin host: use `ASUS_ROUTER_HOST` from sensitive config.
- SSH is available and preferred for recovery. **SSH listens on port 1222** (LAN only, per Web UI 系统设置); set `ASUS_ROUTER_PORT=1222` — plain port 22 is refused.
- Web admin login via API: POST `login.cgi` with `login_authorization=base64(user:pass)`, empty `login_captcha`, and a `Referer: http://<host>/Main_Login.asp` header — without the Referer the POST silently fails back to the login page. Success returns `Set-Cookie: asus_token=...`; reuse that cookie for other pages.
- `login_captcha` is only enforced after repeated failed logins (observed: failure counter at 0, captcha gate disabled). Get the scripted POST right on the first attempt — Referer header included — and avoid blind retry loops that can trip the captcha gate and break subsequent logins.
- Web admin reachability is checked with `/Main_Login.asp`.
- BusyBox environment: commands such as `id` may be unavailable; BusyBox `nc` has no `-z` flag — test TCP with `echo | nc -w 6 host port`.

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

## 2026-10-17 Session Findings

### Root cause: provider rotated SS node ports; router subscription feed is stale

- Router nodes 香港01/02 pointed at `cn01.somethingstranges.com:8101/8102` — TCP connect to 8101 was **closed**, while the current port 12101 was **open**. The airport rotated SS endpoints from 81xx to 121xx ports.
- The live Clash subscription (clash UA) serves SS nodes `cn01:12101/12102` (chacha20-ietf + obfs http) plus 101 AnyTLS nodes the router cannot speak. The **v2rayN-UA feed that fancyss fetches no longer contains any chacha20-ietf+obfs node** — it now serves IPLC `*.dlam.is` SS-2022 (`2022-blake3-aes-128-gcm`) nodes. Do not click 更新订阅 on the router: it would overwrite the hand-fixed nodes with an untested node family.
- Password did not change across the rotation (matched `ASUS_FANCYSS_NODE_PASSWORD`).

### Fix applied (working)

- Rewrote `fss_node_4`/`fss_node_5` in place: `server` → resolved IP `147.90.24.250` (rss-local runtime DNS still broken — pre-check logged `节点服务器域名运行时解析失败` while nslookup succeeded), `port` → `12101`/`12102`. Auto subscription update is disabled on the router, so the manual edit persists.
- After stop→start: rss-local/rss-redir/smartdns stayed up, `127.0.0.1:23456` LISTEN (previously never bound), self-test exit IP `140.235.141.8` 海外, socks5 country=HK, google generate_204=204; LAN client (gateway 192.168.50.1) got google 204 and baidu 200 direct. SSH/Web management stayed reachable after start this time.

### Batch node repair (all nodes, 2026-10-17)

Router held 145 stale nodes (all chacha20-ietf+http_simple, 8xxx ports). Name-matched against the live Clash profile's 45 SS nodes (method/password unchanged upstream — only server/port rotate). Per-endpoint TCP probe from the router:

- **18 nodes usable from mainland and fixed** (server→resolved IP, port→121xx/122xx/124xx/125xx): 香港01-03 (12101-12103), 新加坡01-05 (12201-12205), 日本01-03 (12401-12403), 美国01-06 (12501-12506), 仅海外用户台湾1 (ostw01:2000). Live spot-check on 新加坡01 returned country=SG.
- **27 matched-but-unusable**: `仅海外用户*` nodes (oshk/ossg/osjp/osus/osuk/tr/osng/cn101, port 2000) refuse mainland connections by design; id./br. no longer resolve. Left untouched.
- **100 old nodes** (香港04-26, TW01/JP01/US01, 菲律宾, 新加坡06-18, 日本04-08, 美国07-19, etc.) have no modern SS equivalent — dead upstream, left untouched.

Operational notes: expect/ssh sessions wrap long lines at ~80 cols — never parse long base64 values from session output; pull via `dbus get` piped to files or use short field greps. Long probe loops exceed the 180s expect timeout — run `nc` tests in parallel with `&`+`wait` (28 tests in ~5s) or under `nohup` and poll a results file. A `dbus set fss_node_<id>=<b64>` line can silently fail in a long batch (id 157 did) — always re-verify each node individually afterwards.

### Node list cleanup (2026-10-17, user-approved)

Deleted the 127 dead nodes, keeping only the 18 working ones. Node bookkeeping keys that must stay consistent when deleting: `fss_node_order` (comma-separated display order — rewrite to kept ids), `fss_node_failover_identity` (was pointing at deleted TW01 — repointed to 香港02 `4aec7140_7bf5b27e`), `fss_node_current`/`fss_node_current_identity` (untouched, id 4), `fss_node_next_id` (left at 163, no id reuse). Full pre-cleanup backup of all 145 base64 node values lives in the session's `/tmp/router_nodes_clean.txt` (ephemeral).

### If it breaks again

1. Compare router node ports with the local Clash profile SS nodes (`cn*.somethingstranges.com:121xx`); ports rotate.
2. Re-resolve the node domain (`nslookup cn01.somethingstranges.com 223.5.5.5`) — the pinned IP `147.90.24.250` superseded the older `206.109.71.215`, so it does rotate; update `server` in the affected `fss_node_<id>` accordingly.
3. `fss_node_current=4` keeps pointing at node id 4 after in-place JSON edits; `_identity` fields only matter for subscription reconciliation, not startup.

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
