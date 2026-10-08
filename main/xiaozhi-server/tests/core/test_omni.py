"""Offline regression tests for native media ingress and Qwen HTTP requests."""
import base64
import copy
import io
import wave
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from core.utils.multimodal import validate_content, content_summary
from core.utils.dialogue import Dialogue, Message


def media_blocks():
    return [
        {"type": "text", "text": "结合画面和声音回答"},
        {"type": "image_url", "image_url": {"url": "https://example.com/a.jpg"}},
        {"type": "input_audio", "input_audio": {"data": "data:audio/wav;base64,YWJj", "format": "wav"}},
        {"type": "video_url", "video_url": {"url": "https://example.com/a.mp4"}},
    ]


def test_media_validation_and_history_separate_display_from_payload():
    blocks = media_blocks()
    validated = validate_content(blocks)
    d = Dialogue()
    message = Message("user", content_summary(blocks), model_content=validated)
    d.put(message)
    assert d.get_llm_dialogue()[0]["content"] == blocks
    assert "base64" not in message.content
    assert "未转录" in message.content
    validated[0]["text"] = "changed"
    assert blocks[0]["text"] != "changed"


@pytest.mark.parametrize("content", [
    None, [], [{"type": "tool", "content": "bad"}],
    [{"type": "image_url", "image_url": {"url": "file:///etc/passwd"}}],
    [{"type": "image_url", "image_url": {"url": "data:image/png;base64,!!!"}}],
    [{"type": "input_audio", "input_audio": {"data": "https://example.com/a", "format": "exe"}}],
    [{"type": "text", "text": "a"}] * 9,
])
def test_rejects_invalid_media(content):
    with pytest.raises(ValueError):
        validate_content(content)


def test_media_limit(monkeypatch):
    import core.utils.multimodal as mm
    monkeypatch.setattr(mm, "MAX_CONTENT_BYTES", 8)
    with pytest.raises(ValueError, match="限制"):
        validate_content([{"type": "text", "text": "123456789"}])


def test_old_media_is_evicted_but_text_and_tool_history_survive():
    d = Dialogue()
    for i in range(6):
        d.put(Message("user", f"[图片 {i}]", model_content=media_blocks()))
    d.put(Message("assistant", tool_calls=[{"id": "t", "type": "function", "function": {"name": "test", "arguments": "{}"}}]))
    d.put(Message("tool", "ok", tool_call_id="t"))
    out = d.get_llm_dialogue()
    assert out[0]["content"] == "[图片 0]"
    assert out[1]["content"] == "[图片 1]"
    assert isinstance(out[2]["content"], list)
    assert out[-1]["content"] == "ok"


@pytest.fixture
def provider(monkeypatch):
    from core.providers.llm.qwen_omni.qwen_omni import LLMProvider
    import core.providers.llm.openai.openai as compat
    client = Mock()
    monkeypatch.setattr(compat.openai, "OpenAI", Mock(return_value=client))
    return LLMProvider({"api_key": "test-key", "base_url": "https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"})


class FakeStream:
    def __init__(self, chunks):
        self.chunks = chunks
        self.closed = False

    def __iter__(self):
        yield from self.chunks

    def close(self):
        self.closed = True


def test_omni_stream_keeps_native_content_and_uses_38_parameters(provider):
    messages = [{"role": "user", "content": media_blocks()}]
    original = copy.deepcopy(messages)
    stream = FakeStream([SimpleNamespace(choices=[]), SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="回答"))])])
    provider.client.chat.completions.create.return_value = stream
    assert list(provider.response("s", messages)) == ["回答"]
    request = provider.client.chat.completions.create.call_args.kwargs
    assert request["model"] == "qwen3.8-omni-flash"
    assert request["reasoning_effort"] == "none"
    assert request["modalities"] == ["text"]
    assert "enable_thinking" not in request.get("extra_body", {})
    assert request["messages"] == original == messages
    assert stream.closed


def test_tools_and_stream_cancellation(provider):
    call = SimpleNamespace(index=0, id="t", function=SimpleNamespace(name="test", arguments="{}"))
    stream = FakeStream([SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None, tool_calls=[call]))])])
    provider.client.chat.completions.create.return_value = stream
    tools = [{"type": "function", "function": {"name": "test", "parameters": {"type": "object"}}}]
    gen = provider.response_with_functions("s", [{"role": "user", "content": media_blocks()}], tools)
    assert next(gen) == (None, [call])
    gen.close()
    assert stream.closed
    assert provider.client.chat.completions.create.call_args.kwargs["tools"] == tools


def test_plain_openai_parameters_unchanged():
    from core.providers.llm.openai.openai import LLMProvider
    old = object.__new__(LLMProvider)
    old.base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    request = {}
    old._apply_thinking_disabled(request)
    assert request == {"extra_body": {"enable_thinking": False}}


@pytest.fixture
def audio_module():
    import core.providers.asr.omni_audio as audio
    return audio


@pytest.fixture
def ingress_module():
    import core.handle.multimodalHandle as ingress
    return ingress


@pytest.mark.asyncio
async def test_audio_is_wav_16khz_not_output_rate(monkeypatch, audio_module):
    audio = audio_module
    submit = AsyncMock()
    monkeypatch.setattr(audio, "start_multimodal_chat", submit)
    adapter = audio.ASRProvider({})
    conn = SimpleNamespace(sample_rate=24000)
    pcm = b"\x01\x00" * 1600
    await adapter.handle_voice_stop(conn, [pcm])
    content = submit.call_args.args[1]
    data = content[0]["input_audio"]["data"].split(",", 1)[1]
    with wave.open(io.BytesIO(base64.b64decode(data))) as wav:
        assert wav.getframerate() == 16000
        assert wav.readframes(1600) == pcm
    with pytest.raises(NotImplementedError):
        await adapter.speech_to_text([], "s")


@pytest.mark.asyncio
async def test_media_uses_existing_chat_with_summary_and_original_blocks(monkeypatch, ingress_module):
    ingress = ingress_module
    monkeypatch.setattr(ingress, "send_stt_message", AsyncMock())
    monkeypatch.setattr(ingress, "enqueue_asr_report", Mock())
    abort = AsyncMock()
    monkeypatch.setattr(ingress, "handleAbortMessage", abort)
    conn = SimpleNamespace(config={"model_mode": "omni"}, intent_type="function_call", need_bind=False, llm=SimpleNamespace(supports_multimodal=True),
                           max_output_size=0, client_is_speaking=True, client_listen_mode="auto",
                           executor=Mock(), chat=Mock(), current_speaker="old", client_abort=True)
    await ingress.start_multimodal_chat(conn, media_blocks())
    abort.assert_awaited_once_with(conn)
    args = conn.executor.submit.call_args.args
    assert args[0] is conn.chat
    assert args[2] == 0
    assert args[3] == media_blocks()
    assert "base64" not in args[1]
    assert conn.current_speaker is None
    assert conn.client_abort is False
    conn.llm.supports_multimodal = False
    with pytest.raises(ValueError, match="QwenOmni"):
        await ingress.start_multimodal_chat(conn, media_blocks())


@pytest.fixture
def vision_module():
    import core.multimodal.vision
    import core.api.vision_handler as vision
    return vision


@pytest.mark.asyncio
@pytest.mark.parametrize("use_omni", [False, True])
async def test_legacy_camera_routes_by_selected_llm(monkeypatch, vision_module, use_omni):
    import json
    import builtins
    import core.providers.llm.qwen_omni.qwen_omni as omni
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j2ioAAAAASUVORK5CYII=")
    original_import = builtins.__import__
    def without_pillow(name, *args, **kwargs):
        if name == "PIL" or name.startswith("PIL."):
            raise ModuleNotFoundError("No module named 'PIL'")
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", without_pillow)
    reader = SimpleNamespace(next=AsyncMock(side_effect=[
        SimpleNamespace(text=AsyncMock(return_value="这是什么")),
        SimpleNamespace(read=AsyncMock(return_value=png)),
    ]))
    request = SimpleNamespace(headers={"Device-Id": "device", "Client-Id": "client"},
                              multipart=AsyncMock(return_value=reader))
    config = {"model_mode": "omni" if use_omni else "separate",
              "OMNI": {"chosen": {"type": "qwen_omni"}},
              "selected_module": {"OMNI": "chosen", "LLM": "chosen", "VLLM": "legacy"},
              "LLM": {"chosen": {"type": "qwen_omni" if use_omni else "openai"}},
              "VLLM": {"legacy": {"type": "openai"}}}
    handler = object.__new__(vision_module.VisionHandler)
    handler.config = config
    handler.logger = Mock()
    handler._verify_auth_token = lambda request: (True, "device")
    omni_provider = Mock()
    omni_provider.response.return_value = iter(["图像", "回答"])
    omni_factory = Mock(return_value=omni_provider)
    monkeypatch.setattr(omni, "LLMProvider", omni_factory)
    old_provider = Mock()
    old_provider.response.return_value = "原视觉回答"
    old_factory = Mock(return_value=old_provider)
    monkeypatch.setattr(vision_module, "create_instance", old_factory)
    response = await handler.handle_post(request)
    data = json.loads(response.text)
    assert data["success"] is True
    if use_omni:
        assert data["response"] == "图像回答"
        old_factory.assert_not_called()
        payload = omni_provider.response.call_args.args[1][0]["content"]
        assert payload[1]["image_url"]["url"].startswith("data:image/png;base64,")
        omni_provider.client.close.assert_called_once()
    else:
        assert data["response"] == "原视觉回答"
        omni_factory.assert_not_called()
        old_factory.assert_called_once_with("openai", {"type": "openai"})


@pytest.mark.asyncio
async def test_media_binding_and_quota_are_enforced(monkeypatch, ingress_module):
    ingress = ingress_module
    binding, quota = AsyncMock(), AsyncMock()
    monkeypatch.setattr(ingress, "check_bind_device", binding)
    monkeypatch.setattr(ingress, "max_out_size", quota)
    monkeypatch.setattr(ingress, "check_device_output_limit", Mock(return_value=True))
    conn = SimpleNamespace(need_bind=True, executor=Mock())
    await ingress.start_multimodal_chat(conn, media_blocks())
    binding.assert_awaited_once_with(conn)
    conn.need_bind = False
    conn.config = {"model_mode": "omni"}
    conn.intent_type = "function_call"
    conn.llm = SimpleNamespace(supports_multimodal=True)
    conn.max_output_size = 100
    conn.headers = {"device-id": "device"}
    await ingress.start_multimodal_chat(conn, media_blocks())
    quota.assert_awaited_once_with(conn)
    conn.executor.submit.assert_not_called()


@pytest.mark.asyncio
async def test_audio_buffer_is_bounded(monkeypatch, audio_module):
    adapter = audio_module.ASRProvider({"max_audio_seconds": 1})
    adapter.handle_voice_stop = AsyncMock()
    conn = SimpleNamespace(asr_audio=[b"\0" * 32000], reset_audio_states=Mock())
    await adapter.receive_audio(conn, b"\0\0", True)
    conn.reset_audio_states.assert_called_once()
    adapter.handle_voice_stop.assert_awaited_once()



@pytest.mark.parametrize("data,mime", [
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF89a", "image/gif"),
    (b"RIFF\x00\x00\x00\x00WEBP", "image/webp"),
])
def test_image_mime_without_external_dependencies(data, mime):
    from core.utils.multimodal import image_mime_type
    assert image_mime_type(data) == mime


def test_riff_audio_is_not_an_image():
    from core.utils.multimodal import image_mime_type
    with pytest.raises(ValueError):
        image_mime_type(b"RIFF\x00\x00\x00\x00WAVE")


def test_separate_route_is_identity_even_with_omni_settings():
    from core.multimodal.routing import prepare_config
    config = {"selected_module": {"ASR": "asr", "LLM": "old", "VLLM": "vision"},
              "OMNI": {"unused": {"type": "invalid"}}}
    original = copy.deepcopy(config)
    assert prepare_config(config) is config
    assert config == original
    config["model_mode"] = "separate"
    assert prepare_config(config) is config


def test_omni_projection_keeps_saved_choices_and_auxiliary_models():
    from core.multimodal.routing import prepare_config
    config = {"model_mode": "omni", "selected_module": {
        "OMNI": "native", "ASR": "old-asr", "LLM": "old-llm", "VLLM": "old-vision", "Intent": "intent"},
        "OMNI": {"native": {"type": "qwen_omni"}},
        "LLM": {"intent-model": {"type": "openai"}}}
    original = copy.deepcopy(config)
    effective = prepare_config(config)
    assert config == original
    assert effective["selected_module"]["LLM"] == "native"
    assert effective["selected_module"]["ASR"] == "__omni_audio__"
    assert "VLLM" not in effective["selected_module"]
    assert "intent-model" in effective["LLM"]
    assert effective["ASR"]["__omni_audio__"]["max_audio_seconds"] == 60
    assert prepare_config(effective) == effective


def test_incomplete_omni_configuration_cannot_fall_back_to_legacy():
    from core.multimodal.routing import prepare_config
    with pytest.raises(ValueError, match="OMNI"):
        prepare_config({"model_mode": "omni", "selected_module": {"LLM": "old"}})


def test_omni_adapter_does_not_add_camera_policies(provider):
    functions = [{"type": "function", "function": {"name": "self_camera_take_photo"}}]
    messages = [{"role": "system", "content": "原角色提示词"}, {"role": "user", "content": "重新拍张照片"}]
    provider.client.chat.completions.create.return_value = FakeStream([])
    list(provider.response_with_functions("s", messages, functions))
    request = provider.client.chat.completions.create.call_args.kwargs
    assert "tool_choice" not in request
    assert request["messages"] == messages
    assert request["tools"] == functions


@pytest.mark.asyncio
async def test_native_audio_intent_uses_original_text_entry(monkeypatch, ingress_module):
    ingress = ingress_module
    start = AsyncMock()
    monkeypatch.setattr(ingress, "startToChat", start)
    monkeypatch.setattr(ingress, "enqueue_asr_report", Mock())
    conn = SimpleNamespace(config={"model_mode": "omni"}, need_bind=False, max_output_size=0,
                           intent_type="intent_llm", session_id="s", executor=Mock(),
                           llm=SimpleNamespace(supports_multimodal=True, response=Mock(return_value=iter(["重新拍张照片"]))))
    audio = [media_blocks()[2]]
    await ingress.start_multimodal_chat(conn, audio)
    start.assert_awaited_once_with(conn, "重新拍张照片")
    conn.executor.submit.assert_not_called()
    request = conn.llm.response.call_args.args[1]
    assert request[-1]["content"] == audio


@pytest.mark.asyncio
async def test_media_is_rejected_outside_explicit_mode(ingress_module):
    conn = SimpleNamespace(need_bind=False, config={}, executor=Mock())
    with pytest.raises(ValueError, match="启用 Omni"):
        await ingress_module.start_multimodal_chat(conn, media_blocks())
    conn.executor.submit.assert_not_called()
