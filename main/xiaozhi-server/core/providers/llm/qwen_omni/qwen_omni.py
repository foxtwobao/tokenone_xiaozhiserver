"""Qwen Omni HTTP adapter: native multimodal input, streaming text/tools."""
import copy
import os

from core.providers.llm.openai.openai import LLMProvider as OpenAIProvider
from core.utils.multimodal import validate_content


class LLMProvider(OpenAIProvider):
    supports_multimodal = True

    def __init__(self, config):
        config = dict(config)
        config.setdefault("model_name", "qwen3.8-omni-flash")
        config["api_key"] = config.get("api_key") or os.getenv("DASHSCOPE_API_KEY", "")
        config["base_url"] = config.get("base_url") or os.getenv("DASHSCOPE_BASE_URL", "")
        if not config["base_url"]:
            raise ValueError("QwenOmni 需要配置所在工作空间的 base_url")
        self.reasoning_effort = config.get("reasoning_effort") or "none"
        if self.reasoning_effort not in {"none", "minimal", "low", "medium", "high", "xhigh", "max"}:
            raise ValueError("无效的 reasoning_effort")
        super().__init__(config)

    @staticmethod
    def normalize_dialogue(dialogue):
        messages = copy.deepcopy(dialogue)
        for message in messages:
            message.setdefault("content", "")
            if isinstance(message["content"], list):
                if message["role"] != "user":
                    raise ValueError("多模态内容仅允许出现在 user 消息中")
                message["content"] = validate_content(message["content"])
        return messages

    def _apply_thinking_disabled(self, request_params):
        # 3.8 uses reasoning_effort, not the older enable_thinking parameter.
        request_params["reasoning_effort"] = self.reasoning_effort
        request_params["modalities"] = ["text"]
        request_params["stream_options"] = {"include_usage": True}
