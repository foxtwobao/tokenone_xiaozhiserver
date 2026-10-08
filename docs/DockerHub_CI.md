# GitHub Actions 构建 Docker Hub 镜像

仓库的 **Settings → Secrets and variables → Actions → Secrets** 配置：

| 名称 | 内容 |
| --- | --- |
| `DOCKERHUB_USERNAME` | Docker Hub 用户名，也支持配置为同名 Actions Variable |
| `DOCKERHUB_TOKEN` | 具有镜像读写权限的 Docker Hub Access Token |

凭据放在仓库级别。Workflow 不绑定 GitHub Environment，仅放在某个 Environment 下的凭据不会被读取。

## 触发构建

- 推送 `main`：自动构建并推送 `server-base`、`server_latest`、`web_latest`。
- 推送 `v1.2.3` 格式的版本标签：发布 `server_1.2.3`、`web_1.2.3`，不覆盖 `main` 的 latest 镜像。
- Actions → **Docker Image CI** → **Run workflow**：选择分支和目标架构后运行。

默认架构为 `linux/amd64`。手动运行可选 `linux/arm64` 或 `linux/amd64,linux/arm64`。
同名标签会指向本次所选架构；需要两种架构共用标签时选择双架构构建。

所有镜像推送到 `docker.io/<DOCKERHUB_USERNAME>/tokenone_xiaozhiserver`。
每次构建还会发布 `server-base_sha-<完整提交SHA>`、`server_sha-<完整提交SHA>`、`web_sha-<完整提交SHA>`，方便定位构建版本。

基础镜像从当前提交的 `Dockerfile-server-base` 和 `requirements.txt` 构建；语音服务使用此次基础镜像的 digest，避免误用上游或其他并发构建的基础镜像。三个镜像分别缓存构建层，首次构建需要下载 Python、Node 和 Maven 依赖，耗时较长。

**Build Base Image** 可单独手动运行，但只构建基础镜像；完整发布使用 **Docker Image CI**。

## 拉取镜像

将 `你的DockerHub用户名` 替换为实际用户名：

```bash
docker pull 你的DockerHub用户名/tokenone_xiaozhiserver:server_latest
docker pull 你的DockerHub用户名/tokenone_xiaozhiserver:web_latest
```

`server_latest` 是语音服务，`web_latest` 包含智控台前端和 Java API。
线上 Compose 的两个应用服务使用上述 `image`，并保留所需数据库、Redis、端口、配置文件、模型文件与持久化卷。`compose.local.yaml` 用于本地源码部署，不会自动切换到 Docker Hub 镜像。

构建完成后在 Actions 运行摘要查看镜像标签与 digest。该 workflow 负责构建和发布镜像，不会自动重启线上服务。
