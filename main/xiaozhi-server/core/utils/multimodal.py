"""Bounded, provider-neutral Chat Completions content validation."""
import base64
import copy
from urllib.parse import urlparse

MAX_CONTENT_BYTES = 10 * 1024 * 1024
MAX_BLOCKS = 8


def validate_content(content):
    if not isinstance(content, list) or not 1 <= len(content) <= MAX_BLOCKS:
        raise ValueError("content 必须包含 1 到 8 个内容块")
    result = []
    total = 0
    for block in content:
        if not isinstance(block, dict):
            raise ValueError("内容块必须是对象")
        kind = block.get("type")
        if kind == "text":
            value = block.get("text")
            if not isinstance(value, str) or not value.strip():
                raise ValueError("text 不能为空")
            clean = {"type": kind, "text": value}
        elif kind in {"image_url", "video_url", "input_audio"}:
            payload = block.get(kind)
            if not isinstance(payload, dict):
                raise ValueError("媒体内容必须是对象")
            key = "data" if kind == "input_audio" else "url"
            value = payload.get(key)
            if not isinstance(value, str) or not value:
                raise ValueError("媒体地址不能为空")
            # The application never fetches remote URLs or local files itself.
            parsed = urlparse(value)
            if parsed.scheme == "data":
                header, sep, encoded = value.partition(",")
                if not sep or not header.endswith(";base64"):
                    raise ValueError("媒体数据必须使用 Base64 data URL")
                if len(encoded) > MAX_CONTENT_BYTES:
                    raise ValueError("媒体内容超过 10 MiB 限制")
                try:
                    decoded = base64.b64decode(encoded, validate=True)
                except ValueError as exc:
                    raise ValueError("无效的 Base64 媒体") from exc
                if not decoded:
                    raise ValueError("媒体数据为空")
            elif parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("媒体地址必须是 HTTPS URL 或 Base64 data URL")
            clean = {"type": kind, kind: {key: value}}
            if kind == "input_audio":
                fmt = payload.get("format")
                if fmt not in {"wav", "mp3"}:
                    raise ValueError("音频格式必须为 wav 或 mp3")
                clean[kind]["format"] = fmt
        else:
            raise ValueError("不支持的多模态内容类型")
        total += len(value.encode("utf-8"))
        if total > MAX_CONTENT_BYTES:
            raise ValueError("内容超过 10 MiB 限制")
        result.append(clean)
    return copy.deepcopy(result)


def content_summary(content):
    labels = {"image_url": "[图片]", "video_url": "[视频]", "input_audio": "[音频，未转录]"}
    return " ".join(b["text"] if b["type"] == "text" else labels[b["type"]] for b in content)


def image_mime_type(data):
    """Detect supported image headers without requiring Pillow at runtime."""
    signatures = (
        (b"\xff\xd8\xff", "image/jpeg"),
        (b"\x89PNG\r\n\x1a\n", "image/png"),
        (b"GIF87a", "image/gif"), (b"GIF89a", "image/gif"),
        (b"BM", "image/bmp"),
        (b"II*\x00", "image/tiff"), (b"MM\x00*", "image/tiff"),
    )
    for header, mime in signatures:
        if data.startswith(header):
            return mime
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    raise ValueError("不支持的图片格式")
