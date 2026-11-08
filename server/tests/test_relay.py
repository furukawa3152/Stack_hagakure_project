import json

from hagakure.config import Settings
from hagakure.conversation.policy import ConversationPolicy
from hagakure.protocol import KIND_SPEAKER, unpack_audio
from hagakure.transport.relay import DownlinkRelay
from hagakure.transport.server import cloud_skip_reason, should_call_cloud
from hagakure.transport.session import DeviceSession


def _relay() -> DownlinkRelay:
    session = DeviceSession(
        Settings(host="127.0.0.1", device_token="secret", voice="gemini", gemini_api_key="x"),
        ConversationPolicy(),
    )
    session.on_message(
        json.dumps(
            {
                "type": "hello",
                "protocol_version": 1,
                "device_id": "core2-001",
                "token": "secret",
                "audio_in": {"rate": 16000, "format": "pcm_s16le"},
            }
        )
    )
    session.on_message(json.dumps({"type": "mute", "mic_enabled": True}))
    return DownlinkRelay(session)


def test_named_audio_is_released_before_the_turn_ends() -> None:
    relay = _relay()
    pcm = b"\x10\x00" * 960
    assert relay.push_audio(pcm, 24000, "") == []
    frames = relay.push_audio(pcm, 24000, "はがくれ君")
    assert frames
    assert relay.action == "speak"
    assert relay.reason == "addressed"
    assert "はがくれ君" not in json.dumps(relay.session.decision_log, ensure_ascii=False)
    assert unpack_audio(frames[0]).kind == KIND_SPEAKER
    assert len(unpack_audio(frames[0]).pcm) == 640


def test_words_without_the_name_send_nothing() -> None:
    relay = _relay()
    heard = "今日は暑い"
    assert relay.push_audio(b"\x10\x00" * 960, 24000, heard) == []
    assert relay.finish(heard) == []
    assert relay.action == "silence"
    assert relay.reason == "proactive_off"
    assert heard not in json.dumps(relay.session.decision_log, ensure_ascii=False)


def test_empty_transcript_still_releases_the_reply() -> None:
    relay = _relay()
    assert relay.push_audio(b"\x10\x00" * 960, 24000, "") == []
    frames = relay.finish("")
    assert frames
    assert relay.action == "speak"
    assert relay.reason == "heard"


def test_only_an_empty_buffer_skips_the_cloud() -> None:
    assert should_call_cloud(b"") is False
    assert should_call_cloud(b"\x00\x00") is True
    assert cloud_skip_reason(b"\x00\x00", "gb") == "grok_unimplemented"
    assert cloud_skip_reason(b"\x00\x00", "cb") == ""


def test_chat_mode_speaks_without_the_name() -> None:
    relay = _relay()
    relay.session.talk_mode = "cb"
    frames = relay.push_audio(b"\x10\x00" * 960, 24000, "今日は暑い")
    assert frames
    assert relay.action == "speak"
    assert relay.reason == "chat"
    assert "今日は暑い" not in json.dumps(relay.session.decision_log, ensure_ascii=False)


def test_grok_mode_drops_audio() -> None:
    relay = _relay()
    relay.session.talk_mode = "gb"
    assert relay.push_audio(b"\x10\x00" * 960, 24000, "はがくれ君") == []
    assert relay.finish("はがくれ君") == []
    assert relay.reason == "grok_unimplemented"
