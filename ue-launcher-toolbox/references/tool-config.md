# 软件条目配置逻辑（tools.json 手工维护）

配置是**导入入口**，数据库才是运行时事实源；没有服务启动自动导入，避免覆盖线上修改。字段细节以 `pyAutomation/doc/ue-launcher-api-spec.md` 为准。

## 位置与操作（在 auto-server 上）

```bash
cd /data/py_automation/backend && source venv/bin/activate
# 预览差异（不写库）：
DISABLE_SCHEDULER=1 python -m flask --app manage.py ue-launcher import \
  --file /data/py_automation_data/ue_launcher/config/tools.json --dry-run
# 确认后应用（按 id 幂等 upsert，缺项不删除）：
DISABLE_SCHEDULER=1 python -m flask --app manage.py ue-launcher import \
  --file /data/py_automation_data/ue_launcher/config/tools.json --apply
# 导出当前 DB 配置（回滚/重新生成手工源用）：
DISABLE_SCHEDULER=1 python -m flask --app manage.py ue-launcher export
```

目录布局：`config/tools.json`、`config/packages/`（待发布本地包）、`config/portable/`（便携原件暂存）、`config/icons/`（可选图标源）。导入前备份/导出在 `backups/<时间戳>/`。

## 条目格式

```json
{
  "configVersion": 1,
  "tools": [
    {
      "id": "example-editor",
      "name": "示例编辑器",
      "description": "tips：用途与首次使用提醒，悬浮和详情共用",
      "category": "开发工具",
      "version": "1.2.3",
      "installerType": "exe",
      "download": { "kind": "local", "file": "packages/EditorSetup-1.2.3-x64.exe" },
      "icon": { "file": "icons/example-editor.png" },
      "installArgs": [],
      "launchCandidates": ["%ProgramFiles%\\ExampleEditor\\ExampleEditor.exe"]
    }
  ]
}
```

## 人工填什么、系统算什么

| 人工填写 | 发布时系统生成/校验 |
|---|---|
| id（稳定）、name、description、category、version | fileName、sizeBytes、sha256（本地包读文件；外链发布期抓取计算，之后不重算） |
| installerType（显式声明，不从扩展名推断 exe 是安装器还是便携） | downloadUrl（外链显式优先；托管包按 UE_LAUNCHER_PUBLIC_BASE_URL 拼接） |
| download：`kind:local`+`file` 或 `kind:external`+`url`（稳定直链，优先 HTTPS） | 不可变落盘 `ue_launcher_packages/<id>/<sha16>__<file>` |
| entryPoint（portable=单 EXE 名；zip=包内相对 .exe 路径） | entryPoint 安全校验（见 architecture 路径规则） |
| launchCandidates（exe/msi 必填至少一个，指向**主程序**不是安装器） | 完整 manifest 校验，任一条失败不发布 |
| icon 可选（`file` 或 `url` 二选一） | 托管图标落 `ue_launcher_icons/` 并给只读路由 |
| installArgs 可选数组（portable/zip 必须空） | — |

## 包型要点

- **exe/msi**：官方安装向导，保留正常 UAC；launchCandidates 写默认安装路径，非默认路径靠客户端定向发现/手选（见 client-runtime）。
- **portable**：单文件 EXE，`entryPoint` 填文件名（如 `mTail.exe`），可无 launchCandidates。
- **zip**：普通 Store/Deflate 压缩包，`entryPoint` 填包内主程序相对路径（如 `bin/tool.exe`），多 EXE 也不猜，必须显式指定。不支持 7z/RAR/加密/分卷/自解压。
- 上传 `.exe` 时服务端保留显式 `portable`，不会按扩展名改写成 `exe`。

## 发布与下架边界

- dry-run 输出 created/updated/unchanged/errors，**0 错误才 apply**；同样输入重复 apply 幂等。
- 缺项默认不删除；删除/禁用要显式操作。
- 新包型（portable/zip）条目：先确认所有目录消费者客户端已升级（旧客户端会整份拒收），不能确认就保持未发布。
- 修改/下架前用 export 留快照；回滚恢复记录指向，不原地覆盖同 URL 的包内容。

## 未来 Web 管理预留

现有 POST/PUT/DELETE/upload 接口已够管理页使用；前端挂载点为 `frontend/src/api/ueLauncher.ts` + `views/ue_launcher/` + router 注册（仿既有模块）。写接口鉴权已实现。Web 页面本身未实施。
