# Fancyss Workflow

## Core Paths

Common KoolShare/fancyss paths:

```sh
/koolshare/scripts/ss_config.sh
/koolshare/scripts/ss_node_subscribe.sh
/koolshare/scripts/ss_proc_status.sh
/koolshare/ss/ssr.json
/tmp/upload/ss_log.txt
/tmp/chinadns_ng.conf
```

Useful binaries:

```sh
/koolshare/bin/rss-local
/koolshare/bin/rss-redir
/koolshare/bin/chinadns-ng
/koolshare/bin/curl-fancyss
```

## Subscription Import

For newer fancyss full builds, subscription URLs are stored in Base64:

```sh
dbus set ss_online_links="$ASUS_FANCYSS_SUBSCRIPTION_B64"
dbus set ssr_subscribe_mode=2
dbus set ss_basic_online_ua=2
dbus set ss_basic_online_links_proxy=2
dbus set ss_basic_sub_ai=1
dbus set ss_basic_sub_node_log=1
dbus set ss_basic_sub_keep_info_node=0
sh /koolshare/scripts/ss_node_subscribe.sh 3
```

Interpretation:

- `ss_basic_online_ua=2`: V2rayN user agent.
- `ss_basic_online_links_proxy=2`: download subscription without proxy.
- `ssr_subscribe_mode=2`: subscribe mode used by this plugin build.

## Node Schema

Newer fancyss stores nodes as Base64-encoded JSON in `fss_node_<id>`. Decode before comparing fields:

```sh
dbus get fss_node_4 | base64 -d
dbus get fss_node_5 | base64 -d
```

Important fields for SS + obfs nodes:

```json
{
  "type": "1",
  "server": "example.com",
  "port": "8101",
  "method": "chacha20-ietf",
  "password": "<redacted>",
  "rss_obfs": "http_simple",
  "rss_obfs_param": "download.microsoft.com",
  "rss_protocol": "origin"
}
```

Map Clash-style nodes as:

- `type: ss` maps to fancyss `type=1` in this build.
- `plugin: obfs` and `plugin-opts.mode: http` map to `rss_obfs=http_simple`.
- `plugin-opts.host` maps to `rss_obfs_param`.
- `cipher` maps to `method`.

## Subscription Content Varies By Client UA

The airport serves different node lists depending on the subscription request's User-Agent:

- Clash/mihomo UA → full YAML: SS nodes on `cn*.somethingstranges.com:121xx` (chacha20-ietf + obfs http) plus AnyTLS nodes the router cannot speak.
- v2rayN UA (what fancyss sends) → SS-2022 IPLC nodes on `*.dlam.is` (`2022-blake3-aes-128-gcm`); contains none of the chacha20-ietf+obfs nodes.

Consequences:

- Refreshing the router subscription cannot restore the known-good SS+obfs nodes; keep the hand-maintained `fss_node_4/5` entries and avoid blind 更新订阅.
- The old armv7 `rss-local`'s support for `2022-blake3-*` ciphers is unverified — refreshed nodes are not guaranteed to start.
- Node ports rotate over time (81xx → 121xx observed). The local Clash profile is the source of truth for current live ports; compare before assuming a node or the plugin is broken.

## Node Storage And Manual Sync From Clash

Subscription import resolves each node's domain to an IP at import time and stores the **IP**. Airport server-IP rotations then silently break every imported node (symptom: overseas DNS dead in whitelist mode; IoT devices phoning home to overseas domains loop DHCP release/retry). The local Clash profile YAML is the source of truth for current server/port/password/obfs host.

Compatibility filter before syncing: only Clash `type: ss` with classical ciphers (`chacha20-ietf` etc.) and `plugin: obfs` map to fancyss `type=1` with `rss_obfs=http_simple`. AnyTLS nodes are unsupported; `2022-blake3-*` ciphers are unverified on the armv7 rss-local — exclude both.

Manual write: build per-node schema-2 JSON (keys in order: `group,method,mode,name,password,port,rss_obfs,rss_obfs_param,rss_protocol,server,type` + `_source,_profile_id,_airport_identity,_source_scope,_source_url_hash` + `_id,_created_at,_schema,_rev,_b64_mode="raw",_updated_at`), base64 it, `dbus set fss_node_<id>=<b64>`. Reuse existing slot ids for name matches and preserve the **current** node's `_identity*` fields so `fss_node_current_identity` keeps resolving.

Store the **resolved IP** (not the domain) in `server`: this build's dynamic-resolution mode (「保留域名写入配置，交由DNS方案直连上游解析」) fails at startup (「节点服务器域名运行时解析失败」) — the node IP then never enters the proxy bypass set, the router's own traffic to the node gets captured by rss-redir, and the whole overseas path (proxy + smartdns remote group) deadlocks. Symptom: 出口检测失败 + LAN clients' overseas TLS reset while domestic stays fine. Downside: when the airport rotates IPs, re-resolve the Clash profile domains and rewrite `server` fields again.

Transport pitfall: piping long multi-line scripts through the expect-based `router_ssh.sh` randomly truncates or drops individual lines (pty burst). After every bulk `dbus set`, verify every slot with `dbus get fss_node_<id> | tr -d "\n" | wc -c` against locally computed b64 lengths and resend mismatches individually until all lengths match.

UI visibility: the web UI enumerates nodes from the **`fss_node_order`** dbus key (comma-separated id whitelist), not by scanning `fss_node_*` keys. Hand-added nodes must be appended to `fss_node_order` and `fss_node_next_id` bumped past the highest used id, or they stay invisible.

## Status / Latency Test Toolchain Broken On AC5300 (kernel 2.6.36)

fancyss 3.5.30's Zig helper binaries cannot probe on this router: `status-tool` runs but every probe fails with `TimerUnsupported` (32-bit Zig uses the `clock_gettime64` syscall, absent on 2.6.36), and `webtest-tool` cannot even start (`UPX-5.0 wants memfd_create()`). Symptoms: 首页「国外/国内连接」永远 X 或 Waiting、节点卡片全 `failed!`，而实际代理完全正常。`statusctl` 和 `node-tool` 不受影响。

Fix: shell shims replace the two binaries ( originals backed up as `/koolshare/bin/*.zig.bak`):

- `/koolshare/bin/status-tool`: `fancyss` subcommand probes china-url direct + foreign-url via `socks5://127.0.0.1:23456` with curl-fancyss and prints the `国外链接 【ts】 ✓&nbsp;&nbsp;N ms@@国内连接 ...` payload; `serve`/`daemon` loop-write the legacy + state JSON files (no unix socket); `client get_cache|probe_once|ping` file-backed; `--version` prints `0.1.3-shim`.
- `/koolshare/bin/webtest-tool`: `run --config <job.json>` — per target runs `start_script`, waits for `wait_port`, probes through `socks5h://127.0.0.1:<test_port>` (warmup discarded, first success of `attempts` wins), appends `id>testing|ms|failed|timeout` to `legacy_stream_file`, ends with `{"results":[{"id,state,latency_ms}]}` in `output_json` (states ok/timeout/failed).
- `dbus set ss_basic_status_mode=once` so the UI path calls the shim directly instead of the socket-based serve daemon (failover is off; in serve mode the missing socket causes restart churn on every poll).

Plugin upgrades overwrite `/koolshare/bin/*` — re-apply the shims after upgrading.

## Start And Switch Nodes

Use `stop` then `start`; `restart` may not regenerate all temporary config files in this build.

```sh
dbus set fss_node_current="$ASUS_FANCYSS_HK01_ID"
dbus set fss_node_current_identity="$ASUS_FANCYSS_HK01_IDENTITY"
dbus set ss_basic_mode=2
dbus set ss_basic_enable=1
rm -f /tmp/upload/ss_log.txt
sh /koolshare/scripts/ss_config.sh stop
sh /koolshare/scripts/ss_config.sh start
tail -160 /tmp/upload/ss_log.txt
```

`ss_basic_mode=2` is mainland whitelist mode in the observed build.

## Success Signals

Look for all of these:

- Log reaches `启动完毕`.
- `rss-redir`, `rss-local`, and `chinadns-ng` stay running after startup.
- `netstat -nlp` shows `23456` for local socks and `7913` for `chinadns-ng`.
- Router-side proxy tests return non-mainland output when using the local socks port.

## Failure Signals

Common failure strings:

```text
节点服务器域名运行时解析失败
代理服务器出口地址检测失败
failed to resolve server name
failed to resolve the provided hostname
```

If `rss-local` and `rss-redir` exit after repeated `failed to resolve server name`, focus on router-side DNS resolution of the node server before changing subscription or node fields.
