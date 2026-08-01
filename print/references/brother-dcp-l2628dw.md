# Brother DCP-L2628DW（家庭打印机）

## 基本信息

- **型号**: Brother DCP-L2628DW
- **位置**: 家庭
- **连接方式**: 网络（Wi-Fi，内网）
- **设备 URI**: `dnssd://Brother%20DCP-L2628DW._ipps._tcp.local./?uuid=e3248000-80ce-11db-8000-94ddf8ed94c4`

## 系统配置

- **系统名称**: `Brother_DCP_L2628DW`
- **状态**: 已启用，就绪
- **协议**: IPPS（IPPS over Bonjour）

## 打印命令

```bash
# 打印文件
lp -d Brother_DCP_L2628DW /path/to/file

# 查看打印队列
lpstat -o Brother_DCP_L2628DW

# 查看打印机状态
lpstat -p Brother_DCP_L2628DW
```

## 说明

- 支持自动双面打印
- 支持彩色打印
- macOS 已自动配置好驱动，直接使用 `lp` 命令即可
