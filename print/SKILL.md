---
name: print
description: 打印文件（图片、PDF、文档等）到本地或网络打印机。当用户提到"打印"、"打印机"、"打出来"、"打印图片"、"打印文件"、"打张图"、"print"、"打印到"、"帮我打印"、"发送到打印机"时触发。即使用户只说"把这个打印出来"、"帮我把这张图打出来"也应考虑使用此 Skill。
compatibility:
  - lp
  - lpstat
---

# print — 打印文件

使用 CUPS 系统的 `lp` 命令打印文件。支持图片（PNG、JPG）、PDF、文本文件等常见格式。

## 流程

1. **确认打印机** — 先跑 `lpstat -p` 查看可用打印机列表
2. **读取参考文件** — 根据打印机名称读取 `references/<printer-name>.md` 获取连接信息（如果有）
3. **打印** — 使用 `lp -d <printer-name> <file>` 发送打印任务

## 多打印机支持

- 每台打印机对应 `references/<打印机标识>.md` 文件
- 如果用户只说"打印"而没有指定打印机，用 `lpstat -p` 列出可用打印机让用户选择
- 如果打印文件很大（>20MB），先告知用户文件大小

## 打印机配置参考文件结构

每台打印机在 `references/` 下有一个独立的 `.md` 文件，包含：
- 打印机名称和型号
- 连接方式（USB / 网络）
- 设备 URI（dnssd:// / ipp:// / usb:// 等）
- 备注（家庭/公司/位置等）

## 常用命令

```bash
# 列出可用打印机
lpstat -p

# 列出默认打印机及详情
lpstat -s

# 打印文件到指定打印机
lp -d 打印机名称 文件路径

# 查看打印任务状态
lpstat -o 打印机名称
```

<memory category="core-rules">
不要把 PDF 直发打印机 9100 原始端口——PCL6/BR-Script3 激光机不保证能解析 PDF。PDF 必须由客户端渲染（Windows 用 SumatraPDF）或经 CUPS 过滤链转换；CUPS/lp 下选页用 `-o page-ranges=1-3,7`。
</memory>

<memory category="common-patterns">
Windows（无 CUPS）CLI 打印入口：装打印机用 `Microsoft IPP Class Driver` 即可（`Add-PrinterPort` + `Add-Printer`）；打印用 SumatraPDF 便携版 `SumatraPDF -print-to "<打印机名>" -print-settings "1-3,7" -silent file.pdf`（支持选页/份数/双面，也能直接打 jpg/png）。图片备选 `mspaint /pt image.png "<打印机名>"`。系统自带 `lpr.exe` 只能发 PCL/PS 原始流、不能选页，不推荐。
</memory>
