# 附加已有开发宿主的方案

以下仅是待执行步骤，未改配置、编译或操作进程。项目专用配置名、源码函数名及构建目录未知。

**1．先确认端口，不能全部改成 27099。** 仅凭监听无法判断进程身份。下面以 CLI 的 `--inspect-extensions=9333` 对应扩展宿主、独立 Node 语言服务器的 `--inspect=6009` 对应语言服务为前提，须核对实际启动参数。两者都是源码调试入口，不是可随意互换的业务端口；若参数不符，应按实际进程纠正。`--remote-debugging-port` 则是 Chromium 调试入口，不能当作扩展宿主 Inspector。

**2．三个窗口分工。** 日常 VSCode 保持不动；CLI 开发宿主打开 AS 工程、触发代码提示；扩展源码窗口设置 JS/TS 断点并附加。不要在日常窗口验证这个开发实例，也不要选“启动扩展”类配置再开一个宿主。

**3．在源码窗口附加。** 已有等效 attach 配置就直接选；否则可在该窗口的 `.vscode/launch.json` 使用以下方案，名称是这里自定义的：

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Attach extension host",
      "type": "extensionHost",
      "request": "attach",
      "port": 9333,
      "sourceMaps": true
    },
    {
      "name": "Attach language server",
      "type": "node",
      "request": "attach",
      "port": 6009,
      "sourceMaps": true
    }
  ]
}
```

在实际补全处理代码的可执行行按 **F9**；**Ctrl+Shift+D** 打开运行和调试，补全若在独立语言服务器中，就选第二项按 **F5**。客户端逻辑才选第一项；跨进程跟踪需要分别附加。然后切到 CLI 开发宿主，在 AS 文件中按 **Ctrl+Space**，或通过命令面板执行 `Trigger Suggest`。命中后回源码窗口查看调用栈，**F10/F11** 单步，**F5** 继续。

**4．确认确实是自己的源码。** 核对 CLI 的 `--extensionDevelopmentPath` 指向当前源码对应的扩展目录；暂停后检查“已加载脚本”和调用栈的绝对路径，确认执行的是本地构建 JS，映射回当前 TS。只有开发宿主标题或扩展已激活还不够。灰色未绑定断点先查进程、构建产物及 source map；必要时将 `outFiles` 指向真实 JS 输出目录，不猜 `out` 或 `dist`。

**5．修改后继续调。** 保存源码，按项目已有构建/watch 脚本生成最新 JS 和映射；仅保存 TS 不代表运行中的 JS 已更新。在 CLI 开发宿主按 **Ctrl+Shift+P** 执行 `Developer: Reload Window`，使扩展及其管理的语言服务器重载，再回源码窗口重新附加并触发提示。用修改后的行为或局部值确认新代码已加载。

**6．这不是 AS 业务断点。** 上述断点暂停 VSCode 侧扩展/语言服务，不会自动暂停引擎中的 `.as` 执行。业务断点需 AS 调试适配器连接运行时；题干不足以确认 27099 的项目约定，若它是引擎调试端口，就只配置在对应业务连接中，不能替换 9333、6009。
