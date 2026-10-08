"""Omni-only camera adapter; the legacy VLLM branch stays in its original handler."""
import asyncio
import base64
from core.multimodal.routing import omni_settings
from core.utils.multimodal import image_mime_type
from core.utils import llm


async def describe_image(config, image_data, question):
    _, settings = omni_settings(config)
    encoded = base64.b64encode(image_data).decode("ascii")
    def run():
        provider = llm.create_instance(settings["type"], settings)
        try:
            return "".join(provider.response("vision", [{"role": "user", "content": [
                {"type": "text", "text": (question or "请描述这张图片") + "(请使用中文回复)"},
                {"type": "image_url", "image_url": {
                    "url": f"data:{image_mime_type(image_data)};base64,{encoded}",
                }},
            ]}]))
        finally:
            provider.client.close()
    return await asyncio.to_thread(run)
