"""Explicit Omni opt-in. Separate-mode configuration passes through unchanged."""
import copy


def is_omni(config):
    return config.get("model_mode", "separate") == "omni"


def omni_settings(config):
    name = config.get("selected_module", {}).get("OMNI")
    settings = config.get("OMNI", {}).get(name)
    if not name or not isinstance(settings, dict):
        raise ValueError("Omni 模式需要选择并配置 OMNI 模型")
    if settings.get("type") != "qwen_omni":
        raise ValueError("不支持的 Omni 供应器")
    return name, settings


def prepare_config(config):
    """Project only the opted-in mode onto the existing conversation interfaces.

    The projection is a private copy, never saved back over the user's independent
    ASR/LLM/VLLM choices. Original mode doesn't copy, validate or modify anything.
    """
    if not is_omni(config):
        return config
    name, settings = omni_settings(config)
    result = copy.deepcopy(config)
    result.setdefault("LLM", {})[name] = dict(settings)
    result["selected_module"]["LLM"] = name
    result["selected_module"]["ASR"] = "__omni_audio__"
    result["selected_module"].pop("VLLM", None)
    result["ASR"] = {"__omni_audio__": {
        "type": "omni_audio", "max_audio_seconds": settings.get("max_audio_seconds") or 60,
    }}
    return result
