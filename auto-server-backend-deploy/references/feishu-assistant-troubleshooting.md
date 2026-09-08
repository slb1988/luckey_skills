# 飞书 AI 助手（feishu pi_runner）日志归属与排查

## 日志为什么不在 app.log

`server.applications.feishu` 包 logger 挂了**独立 RotatingFileHandler 且 `propagate=False`**，
只写 `backend/.logs/feishu.log`，**不向 root logger 传播** → 在 `logs/app.log` 里 grep
飞书助手相关报错永远找不到。台账（每条请求的最终finished/failed 记录）在
`backend/.logs/feishu_assistant_transcript.log`。

请求生命周期按 stage 打点、同一 `trace_id`（`fsai_*`）串联：

```
request_started → agent_selected → pi_started/pi_failed → request_completed
```

## pi_failed 的两种签名（含义完全不同）

| 签名 | 含义 | 处置 |
|------|------|------|
| `pi 启动失败: [Errno 2] No such file or directory: 'pi'` | PATH 找不到 pi（2026-08-29 已修，见 SKILL.md 陷阱 0） | 查进程环境变量 PATH / FEISHU_ASSISTANT_PI_BIN |
| `pi 工作区不存在: '<path>'` 且 `elapsed_ms=0` | pi_runner 启动前预检 workspace 目录存在性，缺失直接拒跑，**pi 根本没启动** | 查 workspace 目录为何消失（见下） |

## 根因实例（2026-09-05）：workspace 被 TeamCity 清理器回收

feishu 助手的 pi workspace（`prod.py` 配置）曾指向
`/mnt/disk2/TeamCity/buildAgent/work/DefaultAgent_MainDev`——手工建在 TC buildAgent
`work/` 下的命名目录。该目录**不在 TC 的 directory.map 里**，被 DirectoryMap 清理器
（192h checkout 清理，机制见 teamcity-tool skill）当作无主目录回收，当天
`directory.map.bak.20260905` 即清理痕迹。

**规则：任何需要持久存在的 P4 workspace / 数据目录都不要放在 TC buildAgent `work/` 下**
——清理器只认 directory.map，手工建的目录迟早被收。应放 TC work/ 之外的稳定路径再改
`prod.py` 指过去。

## 排查命令

```bash
# 按 trace 看 stage 链（比 grep 关键字更可靠）
grep '"pi_failed"' /data/py_automation/backend/.logs/feishu.log | tail -5
grep fsai_<trace_id>  /data/py_automation/backend/.logs/feishu.log

# 台账最终状态
tail -20 /data/py_automation/backend/.logs/feishu_assistant_transcript.log

# workspace 是否还在（预检拦截时第一个要确认的）
ls -ld <prod.py 中配置的 workspace 路径>
```
