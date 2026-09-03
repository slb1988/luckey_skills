# NAS 上的 pyauto-computer agent

pyAutomation 平台在 NAS（10.77.77.6）上以 `~/.local/bin/pyauto-computer` 跑了一个受管 agent
（agent 名 `nas`，监听端口 **9100**），平台侧地址 `PYAUTO_PLATFORM_URL=http://10.77.77.4:5000`
（写在 NAS 的 `~/.profile` 里）。

## 根因：NAS 重启后 agent 不自启

QTS 上**没有 systemd user session**，`pyauto-computer service install` 那套自启模型在 QNAP 上不生效。
**NAS 每次重启后 agent 进程不会自动拉起**，平台判该 agent offline。目前已确认发生过一次，
如复发频繁可配 QTS crontab `@reboot` 或 autorun 兜底（尚未实施）。

## 恢复步骤

```bash
ssh admin@10.77.77.6   # 或 slb1988@（本机 key 未授权，需要密码）

source ~/.profile                              # 加载 PYAUTO_PLATFORM_URL
~/.local/bin/pyauto-computer agent start nas   # 拉起 agent
~/.local/bin/pyauto-computer agent list        # 确认 nas 在跑
```

拉起后平台状态自动变回 online。

## 快速定位

- 平台侧 agent offline + `nc -z 10.77.77.6 9100` 不通 → agent 进程没跑，SSH 上去按上面恢复。
- NAS 本体正常（ping 通、22 开、Docker 容器如 memory-hub 9287/9288 健康）**不等于** agent 正常，两者相互独立。
- NAS 外网 IP（当前 180.173.75.150）扫出来的开放端口是**假开**（TCP 能握手但无任何服务响应/banner），不能作为恢复通道，必须走内网 SSH。
