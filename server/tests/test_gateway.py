import asyncio
import json

import pytest
import websockets

from hagakure.audio.mock import pcm_s16le_tone
from hagakure.avatar.controller import AvatarController
from hagakure.adapters.task_agent import GrokBotTaskAgent
from hagakure.adapters.voice import EchoVoiceBackend, GeminiLiveBackend
from hagakure.config import Settings
from hagakure.conversation.policy import ConversationPolicy
from hagakure.protocol import KIND_MIC, pack_audio, unpack_audio
from hagakure.transport.server import start_server


def _hello() -> str:
    return json.dumps(
        {
            "type": "hello",
            "protocol_version": 1,
            "device_id": "mock-core2",
            "token": "secret",
            "audio_in": {"rate": 16000, "channels": 1, "format": "pcm_s16le"},
        }
    )


def test_websocket_echo_roundtrip() -> None:
    asyncio.run(_echo())


async def _echo() -> None:
    settings = Settings(host="127.0.0.1", port=0, device_token="secret")
    server = await start_server(settings, ConversationPolicy())
    port = server.sockets[0].getsockname()[1]
    pcm = pcm_s16le_tone()
    try:
        async with websockets.connect(f"ws://127.0.0.1:{port}/device") as ws:
            await ws.send(_hello())
            ack = json.loads(await ws.recv())
            assert ack["gateway"] == "hagakure"
            assert ack["cloud_active"] is False
            await ws.send(json.dumps({"type": "mute", "mic_enabled": True}))
            assert json.loads(await ws.recv())["mic_enabled"] is True
            await ws.send(pack_audio(KIND_MIC, 1, 0, 16000, pcm))
            first = await asyncio.wait_for(ws.recv(), timeout=2)
            second = await asyncio.wait_for(ws.recv(), timeout=2)
            messages = [first, second]
            binary = next(item for item in messages if isinstance(item, bytes))
            text = json.loads(next(item for item in messages if isinstance(item, str)))
            assert unpack_audio(binary).pcm == pcm
            assert text["type"] == "expression"
        async with websockets.connect(f"ws://127.0.0.1:{port}/other") as ws:
            with pytest.raises(websockets.ConnectionClosed):
                await asyncio.wait_for(ws.recv(), timeout=2)
    finally:
        server.close()
        await server.wait_closed()


def test_expression_names_cover_the_spec_phases() -> None:
    avatar = AvatarController()
    for phase in (
        "idle",
        "listening",
        "thinking",
        "waiting_turn",
        "speaking",
        "interrupted",
        "muted",
        "disconnected",
        "error",
    ):
        assert avatar.expression_for(phase)


def test_cloud_adapters_are_not_connected() -> None:
    async def check() -> None:
        echo = EchoVoiceBackend()
        await echo.connect()
        await echo.send_audio(b"\x00\x00")
        events = [event async for event in echo.receive_events()]
        assert events[0]["pcm"] == b"\x00\x00"
        with pytest.raises(RuntimeError):
            await GeminiLiveBackend().connect()
        with pytest.raises(NotImplementedError):
            await GrokBotTaskAgent().submit_task("調べて")

    asyncio.run(check())
