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
