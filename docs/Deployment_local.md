# 本机完整部署

在仓库根目录运行：

```bash
docker compose --env-file .env.local -f compose.local.yaml up -d
docker compose --env-file .env.local -f compose.local.yaml ps
```

语音服务挂载 `main/xiaozhi-server` 源码，智控台使用本仓库构建的镜像。
MySQL、Redis、上传文件保存在 Docker 命名卷中；数据库和 Redis 不映射宿主机端口。
`.env.local` 保存监听地址和数据库密码，已加入本地 Git 忽略规则。

## 访问地址

- 智控台：http://192.168.10.38:8002
- 设备 OTA：http://192.168.10.38:8002/xiaozhi/ota/
- WebSocket：`ws://192.168.10.38:8000/xiaozhi/v1/`
- 视觉接口：http://192.168.10.38:8003/mcp/vision/explain

首次打开智控台后注册账号，第一个账号为管理员。
在「模型配置 → 大语言模型 → DeepSeek」中填写 API 密钥。
默认模型为 `deepseek-flash`，API 地址为 `https://api.deepseek.com`。
密钥未填写前无法完成智能对话。

语音识别使用本地 SenseVoiceSmall，语音合成使用 EdgeTTS。
服务端与智控台的连接配置在 `main/xiaozhi-server/data/.config.yaml`，
完整部署的对话模型配置在智控台中修改。

## 日常操作

```bash
# 查看日志
docker compose --env-file .env.local -f compose.local.yaml logs --tail=100 server web

# 配置更新后重启语音服务
docker compose --env-file .env.local -f compose.local.yaml restart server

# 重新构建并启动智控台
docker compose --env-file .env.local -f compose.local.yaml up -d --build web

# 停止服务（保留数据）
docker compose --env-file .env.local -f compose.local.yaml stop
```

容器配置为 `unless-stopped`，会随 Docker 服务恢复启动。
