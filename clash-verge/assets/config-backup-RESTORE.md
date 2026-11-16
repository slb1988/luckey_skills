# Clash Verge 配置恢复指南

`config-backup.zip`（带密码）是 2026-11-16 从 Windows 本机 `%APPDATA%\io.github.clash-verge-rev.clash-verge-rev\` 备份的迁移包。本文件不含敏感信息，故放在 zip 外随时可读。

## zip 内容（解压后得到 `config-backup/`）

```
config-backup/
├── profiles.yaml            # 已精简：current 指向 LKPxBnfnsFWk（本地 vless-kr2）+ 全局 Merge/Script
├── verge.yaml               # Verge 设置：端口覆盖、TUN 开关、系统代理
├── dns_config.yaml          # DNS / fake-ip 配置
├── README.md                # 备份内容说明（与本文互补）
└── profiles/
    ├── LKPxBnfnsFWk.yaml    # 活动 profile：本地 VLESS 节点（含凭据）
    ├── mDqpwXqJGmKi.yaml    # ┐ 该 profile 绑定的辅助文件
    ├── spJlxTnlmPmW.js      # │ merge / script / rules / proxies / groups
    ├── rEYqkofy1lol.yaml    # │
    ├── pZJKT7E8nwND.yaml    # │
    ├── g4rKoUesTIKa.yaml    # ┘
    ├── Merge.yaml           # 全局：TUN route-exclude-address、prepend-rules
    └── Script.js            # 全局：进程直连白名单（Feishu.exe 等）
```

**未备份**（新机器自动重建/需重新导入）：订阅 profile（IPLC.VIP、哆啦ā梦）、其他本地节点、GeoIP 数据库、cache.db、日志、service token。

## 恢复步骤

1. 新机器安装 Clash Verge Rev，**完全退出 Verge**（托盘右键退出）。
2. 解压 zip（资源管理器若不支持该加密格式，用 7-Zip / Bandizip）。
3. 把解压出的 `config-backup/` **里面的内容**（不含外层文件夹）拷入：
   ```
   %APPDATA%\io.github.clash-verge-rev.clash-verge-rev\
   ```
   覆盖同名文件，`profiles/` 目录合并。
4. 启动 Verge → 活动 profile 自动生效（本地节点，无需联网刷新）。
5. 验证：
   ```bash
   netstat -ano | findstr :7897                                    # mixed 端口在听
   curl -x http://127.0.0.1:7897 -s -o NUL -w "%{http_code}" https://www.google.com   # 200 = 通了
   ```
6. 若 TUN 开启且 `route-exclude-address` 有值：重启一次核心（GUI 开关 TUN，或管道 API `POST /restart`），路由表只在核心启动时重建。

## 恢复后按需调整

- **内网网段**：`Merge.yaml` 的 `tun.route-exclude-address` 是源机器的内网段，新机器内网段不同必须改（改后重启核心）。
- **订阅节点**：需要 IPLC.VIP / 哆啦ā梦时重新导入订阅 URL（Verge → 订阅 → 新建），与本地 profile 不冲突。
- **进程白名单**：`Script.js` 里的 Feishu.exe 直连规则随包恢复，无需操作。

排障细节见 skill 正文 [../SKILL.md](../SKILL.md) 与 [../references/windows.md](../references/windows.md)。
