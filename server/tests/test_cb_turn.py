import asyncio
import json

from hagakure.config import Settings
from hagakure.conversation.policy import ConversationPolicy
from hagakure.protocol import KIND_MIC, pack_audio
from hagakure.transport.server import _gemini_turn
from hagakure.transport.session import DeviceSession


def test_cb_replies_end_and_continue_without_name() -> None:
    class Socket:
        def __init__(self):
            self.sent = []

        async def send(self, item):
            self.sent.append(item)

    class Backend:
        api_key = ""
        last_input_text = ""
        last_output_text = ""
        last_transcript_late = False
        last_late_messages = 0
        last_content_keys = set()
        last_messages = 1

        async def stream_turn(self, pcm):
            assert pcm
            self.last_input_text = ""
            yield {"type": "audio", "pcm": b"\x01\x00" * 480, "sample_rate": 24000}

    async def run():
        session = DeviceSession(Settings(device_token="secret", voice="gemini"), ConversationPolicy())
        session.on_message(json.dumps({"type": "hello", "token": "secret"}))
        session.on_message(json.dumps({"type": "mute", "mic_enabled": True}))
        session.on_message(json.dumps({"type": "mode", "value": "cb"}))
        ws = Socket()
        backend = Backend()
        for sequence in (1, 2):
            session.on_message(pack_audio(KIND_MIC, sequence, 0, 16000, b"\x01\x00" * 320))
            await _gemini_turn(ws, session, backend)
        notices = [json.loads(item) for item in ws.sent if isinstance(item, str)]
        assert [item["type"] for item in notices].count("reply_done") == 2
        assert [item["reason"] for item in notices if item["type"] == "policy_decision"] == ["chat", "chat"]
        assert len([item for item in ws.sent if isinstance(item, bytes)]) == 2

    asyncio.run(run())
