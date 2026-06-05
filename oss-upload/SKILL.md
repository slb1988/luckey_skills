---
name: oss-upload
description: 上传本地文件到阿里云 OSS，返回公网访问地址。用于截图、图片、附件等需要生成外链的场景。当用户提到"上传图片"、"上传文件"、"OSS"、"上传到云端"、"生成图片链接"、"图床"、"picgo"、"获取外链"时触发。即使用户只说"帮我把这张图传上去"也应该考虑使用此 Skill。
---

# oss-upload

上传本地文件到阿里云 OSS，输出可直接使用的公网访问地址。

## 快速使用

```bash
python .claude/skills/oss-upload/scripts/oss_upload.py /path/to/file.png
```

成功后输出：
```
OSS_URL: https://your-bucket.oss-cn-shanghai.aliyuncs.com/images/1749174722196.png
```

`OSS_URL:` 开头的行是访问地址，供后续流程提取使用：

```bash
# macOS/Linux
URL=$(python3 .claude/skills/oss-upload/scripts/oss_upload.py /path/to/file.png | grep "^OSS_URL:" | cut -d' ' -f2)
```

```powershell
# Windows PowerShell
$output = python .claude\skills\oss-upload\scripts\oss_upload.py C:\path\to\file.png
$URL = ($output | Select-String "^OSS_URL:").Line -replace "OSS_URL: ", ""
```

## 首次配置

脚本会自动检查 `~/.claude/oss_config.env`：

- **文件不存在**：自动从模版复制并提示填写
- **含占位符 `your_*`**：提示用户手动编辑后重试

配置模版位于 `config/oss_config.env.template`，字段说明：

| 字段 | 说明 | 示例 |
|------|------|------|
| `OSS_ACCESS_KEY_ID` | 阿里云 AccessKey ID | `LTAI5t...` |
| `OSS_ACCESS_KEY_SECRET` | 阿里云 AccessKey Secret | `NEXDx...` |
| `OSS_BUCKET` | Bucket 名称 | `my-bucket` |
| `OSS_ENDPOINT` | 地域 Endpoint | `oss-cn-shanghai.aliyuncs.com` |
| `OSS_PREFIX` | 存储路径前缀 | `images` |

## ossutil 自动安装

脚本启动时检查 ossutil 是否可用，若未安装则自动下载对应平台版本并安装到 `~/bin/`：

| 平台 | 下载包 | 安装路径 |
|------|--------|---------|
| macOS | `ossutil-2.3.0-mac-amd64.zip` | `~/bin/ossutil` |
| Windows | `ossutil-2.3.0-windows-amd64.zip` | `%USERPROFILE%\bin\ossutil.exe` |
| Linux | `ossutil-2.3.0-linux-amd64.zip` | `~/bin/ossutil` |

## 文件命名规则

上传文件名固定为毫秒时间戳 + 原始扩展名，例如 `20260605143022196.png`，确保不冲突。

## 脚本路径

- 主脚本：`scripts/oss_upload.py`（Python 3.6+，无第三方依赖，跨平台）
- 配置模版：`config/oss_config.env.template`
- 运行时配置：`~/.claude/oss_config.env`（用户手动填写，不纳入版本控制）
