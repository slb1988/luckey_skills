# RAGFlow Ubuntu 服务器搭建指南

基于 v0.26.4，在一台已运行多个 Docker 服务的 Ubuntu 24.04 服务器上部署 RAGFlow 的完整流程和踩坑记录。

---

## 环境前提

- Ubuntu 24.04，Docker 已安装，docker compose v2
- 服务器已运行 nginx(:80)、minio(:9000)、redis(:6379)、多个 MySQL 实例
- Docker daemon 配置了 HTTP_PROXY=http://192.168.2.70:7897（代理翻墙）
- Docker daemon 配置了 registry mirror：`https://docker.xuanyuan.me`

---

## 核心部署流程

### 1. 克隆仓库

```bash
mkdir -p /data/ragflow
git clone --depth 1 --branch v0.26.4 https://github.com/infiniflow/ragflow.git /data/ragflow/repo
```

用 `--depth 1 --branch v0.26.4` 浅克隆，速度快；不用 main 分支。

### 2. 端口规划（避开现有服务）

先摸清已有端口占用：

```bash
ss -tlnp | grep -E ':(80|443|3306|6379|9000|9001|938[0-6])\b'
docker ps --format '{{.Names}} {{.Ports}}'
```

已知冲突及映射方案：

| 服务 | 默认端口 | 冲突原因 | 改为 |
|------|---------|---------|------|
| RAGFlow Web | 80 | 宿主机 nginx | 9386 |
| MinIO API | 9000 | 已有 minio 容器 | 9004（后改复用） |
| Redis | 6379 | 已有 redis | 6380 |
| MySQL | 3306 | 已有多个 MySQL | 14307 |

### 3. 修改 .env

```bash
cd /data/ragflow/repo/docker
```

编辑 `.env`，修改以下字段：

```ini
# 端口
SVR_WEB_HTTP_PORT=9386
MINIO_PORT=9004
REDIS_PORT=6380
EXPOSE_MYSQL_PORT=14307

# 向量数据库——选 elasticsearch（infinity 在国内镜像拉取有问题）
DOC_ENGINE=elasticsearch

# RAGFlow 镜像（不改，走 Docker Hub + mirror）
RAGFLOW_IMAGE=infiniflow/ragflow:v0.26.4
```

### 4. 拉取镜像（关键踩坑步骤）

**不要直接 `docker compose up -d`**——国内网络拉 Docker Hub 大镜像必超时。分批拉取：

```bash
# 1. mysql、valkey 从轩辕 mirror 拉（快）
docker pull docker.xuanyuan.me/library/mysql:8.0.39
docker tag docker.xuanyuan.me/library/mysql:8.0.39 mysql:8.0.39
docker pull docker.xuanyuan.me/valkey/valkey:8  # 自动 tag

# 2. Elasticsearch 从 docker.elastic.co 拉（不走 Docker Hub，免限流）
docker pull docker.elastic.co/elasticsearch/elasticsearch:8.11.3
docker tag docker.elastic.co/elasticsearch/elasticsearch:8.11.3 elasticsearch:8.11.3

# 3. MinIO 从 Docker Hub 走 mirror
docker pull pgsty/minio:RELEASE.2026-03-25T00-00-00Z

# 4. RAGFlow 主镜像（1.2GB，约需 20 分钟）——最后拉
docker pull infiniflow/ragflow:v0.26.4
```

### 5. 启动

```bash
cd /data/ragflow/repo/docker
docker compose -f docker-compose.yml up -d
```

### 6. 验证

```bash
docker logs -f docker-ragflow-cpu-1
# 看到 "Running on http://0.0.0.0:9380" 和 "RAGFlow server is ready" 即成功
curl -sI http://localhost:9386  # 应返回 200
```

### 7. 首次登录

RAGFlow v0.26.4 无预设账号。打开 http://localhost:9386，点 "Sign up" 注册新账号，第一个注册用户自动成为管理员。

---

## （可选）复用已有 MinIO

如果宿主机已有 MinIO 实例，可停掉 RAGFlow 自带的，改为复用。

### 停止 RAGFlow 的 MinIO

```bash
docker compose -f /data/ragflow/repo/docker/docker-compose.yml stop minio
docker rm docker-minio-1
```

### 修改 .env 指向宿主机 MinIO

```ini
MINIO_HOST=host.docker.internal   # RAGFlow 容器已配此 hosts 映射
MINIO_PORT=9000                   # 宿主机 MinIO API 端口
MINIO_USER=cyancook               # 宿主机 MinIO 账号
MINIO_PASSWORD=xxx                # 宿主机 MinIO 密码
```

**原理**：`docker-compose.yml` 中 ragflow-cpu 配置了 `extra_hosts: ["host.docker.internal:host-gateway"]`，容器内可通过 `host.docker.internal` 访问宿主机上的所有端口。

### 重启 RAGFlow

```bash
docker compose -f /data/ragflow/repo/docker/docker-compose.yml up -d ragflow-cpu
```

验证连通性：

```bash
docker exec docker-ragflow-cpu-1 curl -sI http://host.docker.internal:9000/minio/health/live
# 应返回 HTTP/1.1 200 OK
```

---

## 踩坑记录

### 坑 1：infinity 镜像拉取反复卡死

**现象**：`docker pull infiniflow/infinity:v0.7.0` 反复卡在 layer `d9e56a463048`，其余层下载完后停滞不动，超时也无效。

**原因**：推断是 Docker Hub 通过代理访问时，大 blob 下载连接被中断（可能是代理限速/断流），Docker daemon 不重试导致假死。

**解决**：放弃 infinity，改用 elasticsearch。ES 可从 `docker.elastic.co`（不经过 Docker Hub）拉取，速度快且稳定。

### 坑 2：RAGFlow 主镜像 1.2GB 拉取频繁超时

**现象**：`docker pull infiniflow/ragflow:v0.26.4` 超时（bash timeout=1800s 仍无输出），但 `busybox` 和 `nginx:alpine` 等小镜像秒下。

**原因**：代理速度约 1MB/s，1.2GB 理论上 20 分钟。但 Docker Hub 的 auth token 有有效期，大文件下载过程中 token 过期后 docker daemon 静默失败（不重试也不报错），加上代理本身可能断流。

**解决**：直接用 `docker compose up -d` 触发拉取（compose 内部重试机制更强），耐心等待约 15-20 分钟。

### 坑 3：轩辕 mirror 只对部分镜像有效

**现象**：`docker.xuanyuan.me` mirror 能成功拉取 `mysql:8.0.39` 和 `valkey/valkey:8`，但拉 `infiniflow/infinity`、`pgsty/minio`、`infiniflow/ragflow` 时只输出广告（"如需稳定高速的镜像拉取服务……"）不实际下载。

**原因**：轩辕免费版只镜像 `library/*`（Docker 官方镜像），不镜像第三方组织的镜像。之前 free tier 可能支持更广，但当前已收紧。

**解决**：library 类镜像走 mirror，第三方镜像走代理 + Docker Hub 直连。

### 坑 4：阿里云/华为云 registry 注册表不全

**现象**：`.env` 中的备选镜像地址：
- `registry.cn-hangzhou.aliyuncs.com/infiniflow/ragflow:v0.26.4` → `toomanyrequests`（也走 Docker Hub 限流）
- `swr.cn-north-4.myhuaweicloud.com/infiniflow/ragflow:v0.26.4` → 超时（可能已下架或未同步）

**解决**：不使用这些，直接用 Docker Hub 原生 tag + 代理。

### 坑 5：Elasticsearch 官方镜像已从 Docker Hub 下架

**现象**：`library/elasticsearch:8.11.3` 在 Docker Hub 上已不可用（Elastic 从 Docker Hub 下架了所有版本）。

**解决**：从 `docker.elastic.co/elasticsearch/elasticsearch:8.11.3` 拉取后 tag 为 `elasticsearch:8.11.3`。docker.elastic.co 直连速度正常，不受 Docker Hub 限流影响。

---

## 端口最终映射

| 服务 | 容器端口 | 宿主机端口 | 备注 |
|------|---------|-----------|------|
| RAGFlow Web | 80 | **9386** | 避开 nginx :80 |
| RAGFlow HTTPS | 443 | 443 | 未冲突 |
| RAGFlow API | 9380 | 9380 | |
| Admin Server | 9381 | 9381 | |
| Elasticsearch | 9200 | 1200 | |
| MySQL | 3306 | **14307** | 避开已有 MySQL |
| MinIO API | 9000 | 9000 | **复用宿主机已有 minio** |
| MinIO Console | 9001 | 9003 | 复用宿主机已有 |
| Redis | 6379 | **6380** | 避开已有 redis |

---

## 管理命令

```bash
# 项目目录
cd /data/ragflow/repo/docker

# 查看状态
docker compose -f docker-compose.yml ps

# 查看日志
docker compose -f docker-compose.yml logs -f ragflow-cpu

# 重启
docker compose -f docker-compose.yml up -d

# 停止
docker compose -f docker-compose.yml down
```
