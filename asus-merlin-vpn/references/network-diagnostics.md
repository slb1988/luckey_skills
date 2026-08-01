# Network Diagnostics

Run validation on the router when the user says local proxy is off or asks not to use the local machine as evidence.

## Router-Side DNS

Test node domain resolution directly:

```sh
nslookup "$ASUS_FANCYSS_NODE_SERVER" 223.5.5.5
nslookup www.google.com 127.0.0.1
```

If `127.0.0.1` returns `2001::1` or `198.18.0.0/15` synthetic answers, recognize them as fancyss DNS/proxy markers rather than normal public DNS answers.

## Router-Side Socks Tests

Use the plugin's local socks port:

```sh
curl -4 -sS --connect-timeout 10 --max-time 20 --socks5-hostname 127.0.0.1:23456 -I https://www.google.com/generate_204
curl -4 -sS --connect-timeout 10 --max-time 20 --socks5-hostname 127.0.0.1:23456 https://ipinfo.io/country
```

If DNS is suspected, bypass DNS with `--resolve`:

```sh
curl -4 -k -sS --connect-timeout 10 --max-time 20 \
  --socks5 127.0.0.1:23456 \
  --resolve www.google.com:443:142.250.72.196 \
  -I https://www.google.com/generate_204
```

## Process And Port Checks

```sh
ps w | grep -E 'rss|ss-|sslocal|ss-redir|obfs|chinadns|dnsmasq|xray|v2ray|trojan' | grep -v grep
netstat -nlp 2>/dev/null | grep -E '23456|3333|7913|rss|obfs|ss'
ls -l /var/run/ssr.pid /var/run/ssrlocal.pid 2>/dev/null
```

PID files alone are not proof that the process is alive.

## DNS Mode Repair

If logs show DoT upstreams and router DNS stalls, switch the China upstream away from DoT and force full restart:

```sh
dbus set ss_basic_chng=1
dbus set ss_basic_chng_china_dns_1_chk=1
dbus set ss_basic_chng_china_dns_2_chk=1
dbus set ss_basic_chng_china_dns_3_chk=0
dbus set ss_basic_chng_china_net_1_typ=udp
dbus set ss_basic_chng_china_udp_1_opt=223.5.5.5
dbus set ss_basic_chng_china_udp_2_opt=119.29.29.29
dbus set ss_basic_chng_dns_query_times=2
sh /koolshare/scripts/ss_config.sh stop
sh /koolshare/scripts/ss_config.sh start
```

Verify `/tmp/chinadns_ng.conf` contains China upstreams such as:

```text
china-dns udp://223.5.5.5
china-dns tcp://119.28.28.28
```

## Avoid Misleading Local Tests

When local tests are allowed, clear proxy variables and bypass proxy for the router admin page:

```sh
env -u http_proxy -u https_proxy -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
  curl --noproxy '*' -I "http://${ASUS_ROUTER_HOST}/Main_Login.asp"
```

Do not treat a successful local Google test as proof that fancyss's router-side test should pass.
