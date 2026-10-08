from enum import Enum


class TextMessageType(Enum):
    """消息类型枚举"""
    MEDIA = "media"
    HELLO = "hello"
    ABORT = "abort"
    LISTEN = "listen"
    IOT = "iot"
    MCP = "mcp"
    SERVER = "server"
    PING = "ping"
