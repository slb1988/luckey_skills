# P4 自助诊断与运维指南

> 面向"服务器能连但行为异常"的场景（CPU 飙高、命令卡死、僵尸 stream 等），
> 区别于 `p4d-server.md`（容器/存储层故障）。操作入口见 `../SKILL.md`。

## 前置：连接方式

### 原生 p4d（当前）

```bash
export P4PORT=192.168.50.2:1666
p4 info
```

无需 ticket 认证，直接可用。

### Docker p4d（旧，待下线）

P4PORT: `192.168.50.2:1666`。管理员账号 `p4admin`，`security=2` 需要 ticket 认证：

```bash
export P4PORT=192.168.50.2:1666
export P4USER=p4admin
p4 login   # 交互式输入密码
```

## 诊断命令（只读，随时可以跑，无风险）

```bash
p4 monitor show -a -l        # 看所有活跃命令、锁状态、运行时长 —— CPU 异常时第一件事
p4 configure show            # 看当前配置的护栏参数（MaxScanRows/MaxResults/MaxLockTime/server.maxcommands）
p4 stream -o <stream_path>   # 看某个 stream 详情（类型、创建时间等）
p4 changes -m 5 -s submitted <stream_path>/...   # 看某 stream 最近提交时间，判断是否僵尸
```

`p4 monitor show -a -l` 是排查"CPU 突然飙高"最关键的入口，能看到哪个用户、哪条命令、跑了多久、有没有锁表。

### 排查三连（CPU 异常时按顺序跑）

1. `p4 monitor show -a -l` — 找出运行时间异常长、反复出现的命令和涉及的用户/路径
2. `p4 configure show` — 确认是否有护栏（没有的话说明缺乏限制，容易被单条命令拖垮）
3. `p4 stream -o <可疑路径>` + `p4 changes -m 5 -s submitted <可疑路径>/...` — 确认该 stream 是否是僵尸（长期无提交却被频繁访问）

### 僵尸 task stream 判断标准

- 长期（数月）无实际提交（`p4 changes` 结果陈旧）
- 但在 `p4 monitor show` 中被同一批命令（尤其是 `istat -Af`，强制刷新不走缓存）反复访问
- 常见触发源：P4V「流视图/Stream Graph」功能自动刷新，对着这类 stream 反复发 `istat -Af`，导致对 parent 的全量历史扫描

## 运维命令（有副作用，每次执行前建议二次确认，因为是生产系统）

```bash
p4 monitor terminate <pid>                      # 杀掉卡死的命令
p4 unload -s <stream_path>                      # 优先用这个而不是 -d，可用 p4 reload 恢复
p4 stream -d <stream_path>                       # 真正删除，不可逆，仅在确认无用后用
p4 configure set MaxScanRows=<N> -g <group>      # 护栏参数，按用户组设置
p4 configure set MaxLockTime=<ms> -g <group>
p4 configure set MaxResults=<N> -g <group>
```

**注意**: `p4 monitor terminate` 依赖 `monitor` 这个 configurable 的级别。若默认只有 `monitor=1`（基础展示），terminate 可能不生效，需要 `p4 configure set monitor=2` 才能启用完整的监控/终止能力。建议先测试一次 terminate，不生效再升级级别。

## 事件记录

### 2026-07: PublisherReview 僵尸 task stream 引发 istat CPU 风暴

- **现象**: QNAP 主机 CPU ~50%，9 个 `istat -a -Af //../PublisherReview` 卡死（8 个来自 LiangZhikai，运行 16-31 分钟；1 个来自 LiPing，运行 72 分钟）
- **根因**: task stream `PublisherReview`（创建于 2025/05/14，最后一次真实提交 2025/12/08，僵尸期 7 个月）被 P4V 流视图自动刷新反复触发 `istat -Af` 全量扫描
- **辅助因素**: `p4 configure show` 当时只有 `monitor=1`，没有 `MaxScanRows`/`MaxResults`/`MaxLockTime`/`server.maxcommands` 任何护栏
- **提出的补救方案**（未执行，待确认）:
  1. `p4 monitor terminate 2004 2008 4236 5648 7028 7540 7544 7920 5896` 终止卡死进程
  2. `p4 unload -s //CyanCookOfficialDepot/PublisherReview`（或 `p4 stream -d`），并让 LiangZhikai/LiPing 关闭 P4V 流视图自动刷新
  3. 为相关用户组加 `MaxScanRows`/`MaxLockTime` 护栏
