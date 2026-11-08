import asyncio
import struct

import pytest
from google.genai import types

from hagakure.audio.mock import resample_s16le
from hagakure.audio.stream import StreamResampler

from hagakure.adapters.voice import (
    DEFAULT_MODEL,
    GeminiLiveBackend,
    events_from_message,
    live_connect_config,
)
from hagakure.config import load_settings


class _Inline:
    def __init__(self, data: bytes, mime_type: str) -> None:
        self.data = data
        self.mime_type = mime_type


class _Part:
    def __init__(self, data: bytes, mime_type: str) -> None:
        self.inline_data = _Inline(data, mime_type)


class _Turn:
    def __init__(self, parts: list[_Part]) -> None:
        self.parts = parts


class _Transcription:
    def __init__(self, text: str) -> None:
        self.text = text


class _Content:
    def __init__(
        self,
        parts: list[_Part],
        interrupted: bool = False,
        input_text: str = "",
        interim_text: str = "",
        output_text: str = "",
    ) -> None:
        self.model_turn = _Turn(parts)
        self.interrupted = interrupted
        self.input_transcription = _Transcription(input_text) if input_text else None
        self.interim_input_transcription = _Transcription(interim_text) if interim_text else None
        self.output_transcription = _Transcription(output_text) if output_text else None


class _Message:
    def __init__(self, content: _Content) -> None:
        self.server_content = content


class _Session:
    def __init__(self, messages: list[_Message]) -> None:
        self.messages = messages
        self.sent: list[tuple[bytes, str]] = []
        self.closed = False

    async def send_realtime_input(self, *, audio=None, **_kwargs) -> None:
        self.sent.append((audio.data, audio.mime_type))

    async def receive(self):
        for message in self.messages:
            yield message

    async def aclose(self) -> None:
        self.closed = True


def test_empty_key_does_not_open_a_session() -> None:
    async def check() -> None:
        backend = GeminiLiveBackend()
        with pytest.raises(RuntimeError, match="接続していません"):
            await backend.connect()

    asyncio.run(check())


def test_live_config_is_audio_only_and_has_no_tools() -> None:
    config = live_connect_config()
    assert config.response_modalities == [types.Modality.AUDIO]
    assert config.speech_config.language_code == "ja-JP"
    assert config.speech_config.voice_config.prebuilt_voice_config.voice_name == "Puck"
    assert config.realtime_input_config.automatic_activity_detection.disabled is True
    assert config.tools is None
    assert "HAGAKURE君" in config.system_instruction
    assert "拙者" in config.system_instruction
    assert "日本語だけ" in config.system_instruction
    assert config.input_audio_transcription.language_codes == ["ja-JP"]
    assert "はがくれ君" in config.input_audio_transcription.custom_vocabulary
    assert config.output_audio_transcription is None
    assert live_connect_config(transcribe_output=True).output_audio_transcription is not None


def test_pcm_roundtrip_uses_16k_up_and_24k_down() -> None:
    session = _Session(
        [
            _Message(_Content([_Part(b"\x01\x00\x02\x00", "audio/pcm;rate=24000")])),
        ]
    )

    async def open_session() -> _Session:
        return session

    async def check() -> None:
        backend = GeminiLiveBackend(api_key="unused", opener=open_session)
        await backend.connect()
        await backend.send_audio(b"")
        await backend.send_audio(b"\x03\x00")
        events = [event async for event in backend.receive_events()]
        await backend.close()
        assert session.sent == [(b"\x03\x00", "audio/pcm;rate=16000")]
        assert events == [{"type": "audio", "pcm": b"\x01\x00\x02\x00", "sample_rate": 24000}]
        assert session.closed

    asyncio.run(check())


def test_interrupted_event_has_no_audio_bytes() -> None:
    events = events_from_message(_Message(_Content([], interrupted=True)))
    assert events == [{"type": "interrupted"}]


def test_interrupt_is_not_implemented() -> None:
    async def check() -> None:
        backend = GeminiLiveBackend(opener=_ready)
        await backend.connect()
        with pytest.raises(NotImplementedError):
            await backend.interrupt()

    async def _ready() -> _Session:
        return _Session([])

    asyncio.run(check())


def test_resample_24k_constant_becomes_16k() -> None:
    source = struct.pack("<" + "h" * 240, *([1000] * 240))
    output = resample_s16le(source, 24000, 16000)
    samples = struct.unpack("<" + "h" * (len(output) // 2), output)
    assert samples == tuple([1000] * 160)
    assert resample_s16le(source, 16000, 16000) == source


def test_collect_reply_sends_16k_and_stops_at_turn_end() -> None:
    sent: list[tuple[str, object]] = []

    class _Session:
        async def send_realtime_input(
            self, *, audio=None, activity_start=None, activity_end=None, **_kwargs
        ) -> None:
            if activity_start is not None:
                sent.append(("start", True))
            if audio is not None:
                sent.append(("audio", audio.data, audio.mime_type))
            if activity_end is not None:
                sent.append(("end", True))

        async def receive(self):
            yield _Message(_Content([_Part(b"\x02\x00" * 24, "audio/pcm;rate=24000")]))
            content = _Content([])
            content.turn_complete = True
            yield _Message(content)

    async def open_session() -> _Session:
        return _Session()

    async def check() -> None:
        backend = GeminiLiveBackend(api_key="x", opener=open_session)
        events = await backend.collect_reply(b"\x03\x00" * 160)
        assert sent[0] == ("start", True)
        assert sent[1] == ("audio", b"\x03\x00" * 160, "audio/pcm;rate=16000")
        assert sent[2] == ("end", True)
        assert events[0]["sample_rate"] == 24000
        assert len(events[0]["pcm"]) == 48

    asyncio.run(check())


def test_collect_reply_keeps_input_text_out_of_events() -> None:
    class _Session:
        async def send_realtime_input(self, *, audio=None, **_kwargs) -> None:
            return None

        async def receive(self):
            yield _Message(
                _Content(
                    [_Part(b"\x02\x00" * 24, "audio/pcm;rate=24000")],
                    input_text="はがくれ",
                )
            )
            yield _Message(_Content([], input_text="君"))
            content = _Content([])
            content.turn_complete = True
            yield _Message(content)

    async def open_session() -> _Session:
        return _Session()

    async def check() -> None:
        backend = GeminiLiveBackend(api_key="x", opener=open_session)
        events = await backend.collect_reply(b"\x03\x00" * 160)
        assert backend.last_input_text == "はがくれ君"
        assert events[0]["type"] == "audio"
        assert all("はがくれ" not in str(event) for event in events)

    asyncio.run(check())


def test_collect_reply_uses_interim_text_when_final_is_empty() -> None:
    class _Session:
        async def send_realtime_input(self, *, audio=None, **_kwargs) -> None:
            return None

        async def receive(self):
            yield _Message(_Content([], interim_text="はが"))
            yield _Message(_Content([], interim_text="はがくれ"))
            content = _Content([])
            content.turn_complete = True
            yield _Message(content)

    async def open_session() -> _Session:
        return _Session()

    async def check() -> None:
        backend = GeminiLiveBackend(api_key="x", opener=open_session)
        events = await backend.collect_reply(b"\x03\x00" * 160)
        assert events == []
        assert backend.last_input_text == "はがくれ"

    asyncio.run(check())


def test_collect_reply_reads_a_transcript_that_arrives_after_the_turn() -> None:
    class _Session:
        def __init__(self) -> None:
            self.extra = _Message(_Content([], input_text="はがくれ君"))

        async def send_realtime_input(self, *, audio=None, **_kwargs) -> None:
            return None

        async def receive(self):
            content = _Content([])
            content.turn_complete = True
            yield _Message(content)

        async def _receive(self):
            message = self.extra
            self.extra = None
            if message is None:
                await asyncio.sleep(5)
            return message

    async def open_session() -> _Session:
        return _Session()

    async def check() -> None:
        backend = GeminiLiveBackend(api_key="x", opener=open_session)
        events = await backend.collect_reply(b"\x03\x00" * 160)
        assert events == []
        assert backend.last_input_text == "はがくれ君"
        assert backend.last_transcript_late is True

    asyncio.run(check())


def test_stream_resampler_keeps_a_constant_across_chunks() -> None:
    source = struct.pack("<" + "h" * 240, *([1000] * 240))
    whole = StreamResampler(24000, 16000)
    one_shot = whole.push(source) + whole.flush()
    split = StreamResampler(24000, 16000)
    halved = split.push(source[: len(source) // 2])
    halved += split.push(source[len(source) // 2 :])
    halved += split.flush()
    assert one_shot == halved
    assert set(struct.unpack("<" + "h" * (len(one_shot) // 2), one_shot)) == {1000}


def test_stream_turn_yields_before_the_model_finishes() -> None:
    class _Live:
        def __init__(self) -> None:
            self.hold = asyncio.Event()

        async def send_realtime_input(self, *, audio=None, **_kwargs) -> None:
            return None

        async def receive(self):
            yield _Message(_Content([_Part(b"\x02\x00" * 24, "audio/pcm;rate=24000")]))
            await self.hold.wait()
            content = _Content([])
            content.turn_complete = True
            yield _Message(content)

    live = _Live()

    async def open_session() -> _Live:
        return live

    async def check() -> None:
        backend = GeminiLiveBackend(api_key="x", opener=open_session)
        async for event in backend.stream_turn(b"\x03\x00" * 160):
            assert event["type"] == "audio"
            assert live.hold.is_set() is False
            live.hold.set()
            break

    asyncio.run(asyncio.wait_for(check(), 1))


def test_stream_turn_reuses_one_session_and_skips_empty_pcm() -> None:
    opens = 0

    class _Live:
        def __init__(self) -> None:
            self.turns = 0

        async def send_realtime_input(self, *, audio=None, **_kwargs) -> None:
            return None

        async def receive(self):
            self.turns += 1
            content = _Content([])
            content.turn_complete = True
            yield _Message(content)

    live = _Live()

    async def open_session() -> _Live:
        nonlocal opens
        opens += 1
        return live

    async def check() -> None:
        backend = GeminiLiveBackend(api_key="x", opener=open_session)
        assert [event async for event in backend.stream_turn(b"")] == []
        assert opens == 0
        assert [event async for event in backend.stream_turn(b"\x03\x00" * 160)] == []
        assert [event async for event in backend.stream_turn(b"\x03\x00" * 160)] == []
        assert opens == 1
        assert live.turns == 2

    asyncio.run(check())


def test_stream_turn_collects_output_transcription_without_emitting_it() -> None:
    class _Live:
        async def send_realtime_input(self, **_kwargs) -> None:
            return None

        async def receive(self):
            yield _Message(_Content([], output_text="x"))
            content = _Content([])
            content.turn_complete = True
            yield _Message(content)

    async def check() -> None:
        backend = GeminiLiveBackend(opener=_open, transcribe_output=True)
        events = [event async for event in backend.stream_turn(b"\x01\x00" * 320)]
        assert events == []
        assert len(backend.last_output_text) == 1

    async def _open() -> _Live:
        return _Live()

    asyncio.run(check())


def test_settings_keep_the_key_and_default_model() -> None:
    source = {"GEMINI_API_KEY": "x", "GEMINI_MODEL": ""}
    settings = load_settings(source)
    assert settings.gemini_api_key == source["GEMINI_API_KEY"]
    assert settings.gemini_model == DEFAULT_MODEL
