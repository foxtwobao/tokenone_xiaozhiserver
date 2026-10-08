"""Audio capture adapter. Sends the utterance to the selected Omni LLM."""
import base64
import io
import wave

from core.providers.asr.base import ASRProviderBase
from core.providers.asr.dto.dto import InterfaceType
from core.handle.multimodalHandle import start_multimodal_chat


class ASRProvider(ASRProviderBase):
    def __init__(self, config, delete_audio_file=True):
        super().__init__()
        self.interface_type = InterfaceType.NON_STREAM
        self.max_audio_seconds = int(config.get("max_audio_seconds", 60))
        if not 1 <= self.max_audio_seconds <= 120:
            raise ValueError("max_audio_seconds 必须在 1 到 120 之间")

    async def open_audio_channels(self, conn):
        if conn.config.get("model_mode") != "omni" or not getattr(conn.llm, "supports_multimodal", False):
            raise ValueError("OmniAudio 必须搭配 QwenOmni LLM")
        await super().open_audio_channels(conn)

    async def receive_audio(self, conn, pcm_frame, audio_have_voice):
        # Bound buffering even if manual stop / VAD endpoint never arrives.
        rate = 16000  # ConnectionHandler decodes input Opus at 16 kHz
        buffered = sum(map(len, conn.asr_audio)) + len(pcm_frame)
        if buffered > rate * 2 * self.max_audio_seconds:
            frames = conn.asr_audio + [pcm_frame]
            conn.reset_audio_states()
            await self.handle_voice_stop(conn, frames)
            return
        await super().receive_audio(conn, pcm_frame, audio_have_voice)

    async def handle_voice_stop(self, conn, asr_audio_task):
        pcm = b"".join(asr_audio_task)
        if not pcm:
            return
        with io.BytesIO() as output:
            with wave.open(output, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(pcm)
            data = base64.b64encode(output.getvalue()).decode("ascii")
        content = [{
            "type": "input_audio",
            "input_audio": {"data": "data:audio/wav;base64," + data, "format": "wav"},
        }]
        await start_multimodal_chat(conn, content)

    async def speech_to_text(self, opus_data, session_id, artifacts=None):
        raise NotImplementedError("OmniAudio 直接理解音频，不提供独立转录")
