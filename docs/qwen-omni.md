# Omni 多模态接入

## 配置入口

模型配置页面有独立的 **Omni 多模态模型** 分类，统一维护地址、密钥、模型名称和参数。智能体选择 `分开接入` 或 `Omni 多模态`：

| 模式 | 生效的输入模型 | 其他功能 |
| --- | --- | --- |
| 分开接入（默认） | ASR、LLM、VLLM | 原配置、原调用链 |
| Omni 多模态 | 所选的一个 Omni 模型，处理文本、音频、图片、视频 | 原有 VAD、Intent、TTS、Memory、SLM、RAG、工具机制 |

两组模型选择分别保存。Omni 模式不调用已停用的独立 ASR/LLM/VLLM，不会在失败时回退到它们。当前 `qwen3.8-omni-flash` 适配器通过 HTTP Chat Completions 输入媒体、流式输出文字，语音回复使用原 TTS。它不是双向 Realtime 音频接口。

## 智控台

1. 在模型配置 → Omni 多模态模型填写接口地址和密钥。
2. 在智能体配置选择 Omni 多模态，再选择该模型。
3. 保留所需的意图模式、工具、记忆和 TTS 音色，保存后重新连接设备。

不需要在 ASR、LLM、VLLM 中重复配置 Omni，也不需要单独选择 OmniAudio。音频包装适配器是内部实现。

`202610042300` 迁移添加 `ai_agent.model_mode`、`omni_model_id`。普通智能体默认 `separate`，不修改其原模型选择。此前通过 QwenOmni LLM 启用的智能体迁移到 `omni`；模型记录和密钥复用原 ID，分类改为 OMNI。这类智能体的旧 LLM 槽位恢复为已启用的普通 LLM（优先默认模型），切回分开模式时可以重新选择。历史 Omni 快照同步转换。旧 OmniAudio 记录移到内部类别，不再作为用户可选的 ASR。

## 文件配置

```yaml
model_mode: omni
selected_module:
  OMNI: QwenOmni
  # 原 ASR/LLM/VLLM 的选择可以保留，Omni 模式不使用它们。
  Intent: function_call
  # VAD/TTS/Memory 等继续使用现有配置。
OMNI:
  QwenOmni:
    type: qwen_omni
    model_name: qwen3.8-omni-flash
    base_url: https://你的兼容接口地址/v1
    api_key: 你的密钥
    reasoning_effort: none
    max_tokens: 2048
    max_audio_seconds: 60
```

`model_mode` 缺省或为 `separate` 时使用原链路，即使配置文件中有 OMNI 节点也不加载它。统一模式仅在内部配置副本中映射到已有会话接口，不覆盖持久化的独立模型选择。地址/密钥为空时可读取 `DASHSCOPE_BASE_URL` / `DASHSCOPE_API_KEY`。

## 意图和拍照

- `function_call`：由当前主模型按原工具流程决定调用。
- `intent_llm`：保留原文字意图识别；专用 `llm` 留空时使用当前主模型，填写时使用指定模型。Omni 模式录音先由同一个 Omni 转录，再进入原文字意图流程，多一次模型请求。独立意图模型的地址和密钥也必须有效。
- `nointent`：沿用原普通对话。
- 拍照仍由原设备 MCP 工具触发。图片上传到原 `/mcp/vision/explain`；只有显式 Omni 模式才交给 Omni，其他模式执行原 VLLM 分支。识图结果按原工具结果格式返回，不新增拍照规则、强制工具选择或图片意图识别。
- 旧相机 HTTP 接口是独立识图，原图不进入聊天历史。WebSocket 媒体消息可保留最近四轮媒体用于追问。
- 轮次、打断、工具执行和 TTS 使用原机制；本次没有修改取消语义，不能保证正在执行的设备动作会撤销。

## 原生媒体

原 Opus 设备音频按 16 kHz 单声道 PCM 包装为 WAV，在 VAD 结束或 `listen.stop` 后提交。默认一段最长 60 秒，可配置 1–120 秒。原生音频不启用独立 ASR 的声纹处理。

启用 Omni 的 WebSocket 连接可发送：

```json
{
  "type": "media",
  "content": [
    {"type": "text", "text": "结合画面和声音解释"},
    {"type": "image_url", "image_url": {"url": "https://example.com/photo.jpg"}},
    {"type": "input_audio", "input_audio": {"data": "https://example.com/audio.wav", "format": "wav"}},
    {"type": "video_url", "video_url": {"url": "https://example.com/video.mp4"}}
  ]
}
```

地址需能被模型服务访问，也支持 Base64 data URL。输入限 1–8 块、总字符串载荷 10 MiB；仅 Omni 连接放宽 WebSocket 消息上限到 12 MiB。分开模式保留原限制并拒绝原生媒体消息。音频支持 WAV/MP3。此接口不读取客户端本地文件，日志和上报不保存 Base64。

纯图片/视频消息用于内容理解，不额外进行意图分类；含音频的 `intent_llm` 请求先转录用户指令再进入原意图处理。没有独立转录的轮次显示 `[音频，未转录]`，不将占位文字当作真实转录。

## 维护边界

- `core/multimodal/routing.py`：显式模式配置投影，分开模式返回原对象。
- `core/multimodal/vision.py`：Omni 独立识图；原 VLLM 代码保留在原 HTTP handler 分支。
- `core/handle/multimodalHandle.py`：Omni 媒体校验、音频指令与原会话衔接。
- `core/providers/asr/omni_audio.py`：内部录音包装，不是独立识别模型。
- `core/providers/llm/qwen_omni/`：供应商 API 格式和参数，不包含相机策略。

测试覆盖配置隔离、模式切换、快照校验、媒体载荷、模型请求参数和相机路由。测试环境请用 `PYTEST_CONFIG_FILE` 指向隔离配置，避免接触运行配置。
