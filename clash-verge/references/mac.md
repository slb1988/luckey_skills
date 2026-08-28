# macOS 细节

> 本文件内容基于 Clash Verge Rev 的通用约定整理，**首次在 Mac 上使用时先按「控制 API」一节实际确认**，如有出入以实际为准并更新本文件。

## 应用数据目录

`~/Library/Application Support/io.github.clash-verge-rev.clash-verge-rev/`

目录结构与 Windows 相同：`profiles/`、`profiles.yaml`、`verge.yaml`、`clash-verge.yaml`（运行时合并配置）、`logs/`。各文件含义见 [windows.md](windows.md) 的表格。

## 端口

- mixed 默认 **7897**（同样会被 Verge 设置覆盖 profile 里的值）

```bash
lsof -iTCP:7897 -sTCP:LISTEN     # 端口监听
ps aux | grep -i verge-mihomo    # 核心进程
```

## 控制 API

macOS 没有命名管道，以运行时配置里的字段为准，常见两种：

1. **TCP**：`external-controller: 127.0.0.1:<端口>`

```bash
curl -H "Authorization: Bearer <secret>" http://127.0.0.1:<端口>/version
curl -H "Authorization: Bearer <secret>" http://127.0.0.1:<端口>/proxies/<分组>
curl -X PUT -H "Authorization: Bearer <secret>" -H "Content-Type: application/json" \
     -d '{"name":"<节点名>"}' http://127.0.0.1:<端口>/proxies/<分组>
```

2. **Unix socket**：`external-controller-unix: <路径>`

```bash
curl --unix-socket <路径> -H "Authorization: Bearer <secret>" http://localhost/version
```

首次使用先确认：

```bash
grep -E "external-controller|secret" \
  "$HOME/Library/Application Support/io.github.clash-verge-rev.clash-verge-rev/clash-verge.yaml"
```

## 排查命令速查

```bash
curl -x http://127.0.0.1:7897 -s -o /dev/null -w "%{http_code} %{time_total}s\n" --connect-timeout 12 https://<目标域名>
curl -x http://127.0.0.1:7897 -s http://ipinfo.io/json    # 出口 IP/ASN
```

排障思路（对照组、OpenAI 封锁特征、域名清单）与系统无关，见 [../SKILL.md](../SKILL.md)。
