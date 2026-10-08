import json
import time
from core.handle.textMessageHandler import TextMessageHandler
from core.handle.textMessageType import TextMessageType
from core.handle.multimodalHandle import start_multimodal_chat


class MediaMessageHandler(TextMessageHandler):
    @property
    def message_type(self):
        return TextMessageType.MEDIA

    async def handle(self, conn, msg_json):
        try:
            await start_multimodal_chat(conn, msg_json.get("content"))
            conn.last_activity_time = time.time() * 1000
        except ValueError as exc:
            await conn.websocket.send(json.dumps({
                "type": "error", "code": "invalid_media", "message": str(exc),
                "session_id": conn.session_id,
            }, ensure_ascii=False))
