# 应用管家 Web 命令桥

## 两条独立链路

- **直连**：Mac adb → 学习机 adbd 实际端口 → shell。适合持续操作、二进制输出、文件传输。
- **网页桥**：Mac HTTP → 应用管家 9898 → 命令终端 → 内部 ADB 客户端或普通应用 shell。可用于外部端口未知时的自举，不是独立常驻远程 shell。

采样版本：`com.yunpan.appmanage` 1.7.7，versionCode 1777。

## 执行前提：HTTP 可访问还不够

实测可以出现首页和 `/cmd` 均返回 HTTP 200，但结果文件不生成。设备在桌面或管家首页时复现；进入管家 **“执行命令”** 页面后，Web→ADB 和 Web→本机命令均成功。

已观察到的组件：

- 管家首页：`com.yunpan.appmanage/.ui.ActivityHome`
- 命令终端：`com.yunpan.appmanage/.ui.ActivityShell`

要求用户打开“执行命令”页，并核对管家内部 ADB 显示已连接。不同版本可能另有“监听命令”开关，按实际 UI 核实；不要无条件宣称后台也能接收。当前证据只证明上述页面状态与执行结果的关系，没有证明 Activity 销毁/广播实现等内部根因。

已经有 ADB 时，可先说明会切换前台，再启动已确认的首页，按实际截图/控件进入“执行命令”；不硬编码点击坐标，也不假设内部 Activity 对外导出。

## 实测 HTTP 契约

`cmd.html` 内联脚本的行为是 `POST /cmd`，表单字段只有 `shareUrl`，值为**一位模式前缀 + 原始命令**。

| 模式 | 字段示例 | 执行身份 / 注意事项 |
|---|---|---|
| `0` 本机命令 | `shareUrl=0id` | 实测 `uid=10088(u0_a88)`、普通应用域；不是 root |
| `1` ADB 命令 | `shareUrl=1id` | 实测 `uid=2000(shell)`；无需 `adb shell` 前缀 |
| `2` 剪贴板 | 文本前缀 2 | 修改设备剪贴板，不是 shell；诊断默认不用 |

```bash
curl --noproxy '*' --max-time 10 \
  --data-urlencode 'shareUrl=1id' \
  "http://${DEVICE_IP}:9898/cmd"
```

响应 `200 OK`、正文 `OK` 只是“已接收”，**不是命令 stdout 或退出码**。当前页面只尝试显示发送提示，没有执行结果渲染逻辑；别用提示是否弹出判断执行成功。

文件页面 `/` 使用：

- `GET /file/<相对目录>` / `/refile/<相对目录>`：目录列表。不要为了诊断浏览用户所有文件。
- `GET /down/<相对路径>`：下载文件，例如 `/down/Download/<本次输出>.txt`。
- `POST /upload`：页面的上传/安装功能；本次未验证，也不用于只读排查。

协议从设备当前页面脚本直接读取；版本变化后重新核对，不根据 URL 名称猜 API。

## Mac 取回命令输出

使用 [web_shell.py](../scripts/web_shell.py)，Python 3 标准库即可，无第三方依赖：

```bash
python3 scripts/web_shell.py --base-url "http://${DEVICE_IP}:9898" \
  'id; getprop service.adb.tls.port; ss -lnt'

python3 scripts/web_shell.py --base-url "http://${DEVICE_IP}:9898" \
  --mode local 'id'
```

脚本机制：

1. 为这一次执行生成唯一文件 `/sdcard/Download/mac-webshell-<随机值>.txt`。
2. 提交一次命令，捕获 stdout/stderr，并写入唯一完成标记及退出码。
3. 轮询该文件的下载 URL，看到完成标记才判定执行完成。
4. 输出真实结果，并以设备命令退出码退出；随后提交仅删除自己生成文件的清理命令。

实测：ADB 模式 `id` 成功；本机模式 `id` 显示普通应用 UID；`printf ... >&2; exit 7` 能在 Mac 返回错误输出与退出码 7。

限制与失败语义：

- 命令应是短时间、文本输出；超过 2MiB 不自动回传。二进制用直连 `adb exec-out` / `pull`。
- 默认等待 30 秒，`--wait-seconds` 只控制等待输出，**不会杀掉设备上的命令**。
- 超时/网络错误返回 125，打印阶段和唯一文件路径，不自动重发。命令退出码 125 时也可返回 125，需结合错误提示区分。
- 文件未创建时服务器实测可返回 HTTP **500**，脚本只在下载轮询中把 404/500 视为暂未就绪；一直不出现完成标记则报未确认。
- 脚本绕过环境代理；不读取或发送密码/cookie。不要把这理解为服务有安全认证。
- 需要应用共享存储可访问。超时留下的文件按脚本输出的精确路径处理，不执行通配删除。
- 清理请求收到 ACK 不等于已验证删除；需要严格确认时用已有 ADB 检查该精确路径。

## 优先排障顺序

1. Web 页面可达？是否直连当前局域网 IP，未被代理带走？
2. 设备是否处于“执行命令”页，内部 ADB 是否已连接？
3. 模式前缀正确？是否误加了 `adb shell`？
4. 结果文件是否生成，是否有权限、路径、shell 语法错误？
5. 成功查询当前 ADB 端口后，优先转为 Mac 原生 ADB。

辅助说明：[应用管家作者的 ADB 连接教程](https://pd.qq.com/g/updata3927/post/B_b1f41467e2ea08001441152196442023080X60)。一般 Android 教程只作背景，本固件以实测为准。
