import json

from hagakure.audio.mock import pcm_s16le_tone
from hagakure.config import Settings
from hagakure.conversation.policy import ConversationPolicy
from hagakure.protocol import KIND_MIC, KIND_SPEAKER, pack_audio, unpack_audio
from hagakure.transport.session import DeviceSession


def _hello(token: str = "secret") -> str:
    return json.dumps(
        {
            "type": "hello",
            "protocol_version": 1,
            "device_id": "core2-001",
            "token": token,
            "audio_in": {"rate": 16000, "channels": 1, "format": "pcm_s16le"},
        },
        ensure_ascii=False,
    )


def _session(token: str = "secret", host: str = "127.0.0.1") -> DeviceSession:
    return DeviceSession(Settings(host=host, device_token=token), ConversationPolicy())


def test_hello_starts_muted_and_mic_off_drops_audio() -> None:
    session = _session()
    ack = json.loads(session.on_message(_hello())[0])
    assert ack["type"] == "hello_ack"
    assert ack["mic_enabled"] is False
    assert ack["phase"] == "muted"
    assert ack["cloud_active"] is False
    pcm = pcm_s16le_tone()
    assert session.on_message(pack_audio(KIND_MIC, 1, 0, 16000, pcm)) == []


def test_enabled_mic_echoes_pcm_without_storing_text() -> None:
    session = _session()
    session.on_message(_hello())
    session.on_message(json.dumps({"type": "mute", "mic_enabled": True}))
    pcm = pcm_s16le_tone()
    binary, notice = session.on_message(pack_audio(KIND_MIC, 4, 20, 16000, pcm, generation=9))
    frame = unpack_audio(binary)
    assert frame.kind == KIND_SPEAKER
    assert frame.pcm == pcm
    assert frame.generation == 1
    payload = json.loads(notice)
    assert payload["type"] == "expression"
    assert payload["mouth"] > 0


def test_bad_token_closes_without_echo() -> None:
    session = _session()
    error = json.loads(session.on_message(_hello("nope"))[0])
    assert error["code"] == "unauthorized"
    assert session.closed is True
    assert session.on_message(pack_audio(KIND_MIC, 1, 0, 16000, pcm_s16le_tone())) == []


def test_open_token_is_rejected_off_loopback() -> None:
    session = _session(token="", host="0.0.0.0")
    error = json.loads(session.on_message(_hello(""))[0])
    assert error["code"] == "unauthorized"


def test_policy_response_omits_transcript() -> None:
    session = _session()
    session.on_message(_hello())
    session.on_message(json.dumps({"type": "mute", "mic_enabled": True}))
    secret = "はがくれ君、この文章は残さない"
    raw = session.on_message(
        json.dumps(
            {
                "type": "transcript",
                "text": secret,
                "human_speaking": False,
                "silence_seconds": 1,
            },
            ensure_ascii=False,
        )
    )[0]
    assert secret not in raw
    decision = json.loads(raw)
    assert decision["reason"] == "addressed"
    assert all("text" not in item for item in session.decision_log)


def test_header_token_is_accepted_when_hello_omits_it() -> None:
    session = DeviceSession(
        Settings(device_token="secret"),
        ConversationPolicy(),
        header_token="secret",
    )
    body = json.dumps(
        {
            "type": "hello",
            "protocol_version": 1,
            "device_id": "core2-001",
            "audio_in": {"rate": 16000, "format": "pcm_s16le"},
        }
    )
    ack = json.loads(session.on_message(body)[0])
    assert ack["type"] == "hello_ack"


def test_mode_ack_keeps_the_three_buttons() -> None:
    session = _session()
    session.on_message(_hello())
    ack = json.loads(session.on_message(json.dumps({"type": "mode", "value": "cb"}))[0])
    assert ack["type"] == "mode_ack"
    assert ack["value"] == "cb"
    assert ack["available"] is True
    assert session.talk_mode == "cb"
    missing = json.loads(session.on_message(json.dumps({"type": "mode", "value": "gb"}))[0])
    assert missing["value"] == "gb"
    assert missing["available"] is False
    rejected = json.loads(session.on_message(json.dumps({"type": "mode", "value": "nope"}))[0])
    assert rejected["code"] == "bad_mode"
    assert session.talk_mode == "gb"


def test_gemini_mode_keeps_mic_and_repacks_24k_audio() -> None:
    session = DeviceSession(
        Settings(host="127.0.0.1", device_token="secret", voice="gemini", gemini_api_key="x"),
        ConversationPolicy(),
    )
    ack = json.loads(session.on_message(_hello())[0])
    assert ack["cloud_active"] is True
    session.on_message(json.dumps({"type": "mute", "mic_enabled": True}))
    pcm = pcm_s16le_tone()
    replies = session.on_message(pack_audio(KIND_MIC, 1, 20, 16000, pcm))
    assert all(isinstance(item, str) for item in replies)
    assert session.take_mic() == pcm
    frames = session.speaker_frames(
        [{"type": "audio", "pcm": b"\x10\x00" * 24, "sample_rate": 24000}]
    )
    frame = unpack_audio(frames[0])
    assert frame.kind == KIND_SPEAKER
    assert frame.sample_rate == 16000
    assert len(frame.pcm) == 640
    assert frame.pcm != pcm


def _named_session() -> DeviceSession:
    session = _session()
    session.on_message(_hello())
    session.on_message(json.dumps({"type": "mute", "mic_enabled": True}))
    return session


def test_unnamed_clip_is_not_spoken() -> None:
    session = _named_session()
    events = [{"type": "audio", "pcm": b"\x01\x00" * 320, "sample_rate": 16000}]
    out = session.timed_reply(events, "今日は暑い")
    assert len(out) == 1
    body = json.loads(out[0])
    assert body["action"] == "silence"
    assert body["reason"] == "proactive_off"
    assert "今日は暑い" not in out[0]
    assert session.decision_log == [{"action": "silence", "reason": "proactive_off"}]


def test_named_clip_is_spoken_without_echoing_the_name() -> None:
    session = _named_session()
    events = [{"type": "audio", "pcm": b"\x01\x00" * 320, "sample_rate": 16000}]
    heard = "はがくれ君"
    out = session.timed_reply(events, heard)
    body = json.loads(next(item for item in out if isinstance(item, str)))
    frames = [item for item in out if isinstance(item, bytes)]
    assert body["action"] == "speak"
    assert body["reason"] == "addressed"
    assert heard not in body.values()
    assert frames
    assert unpack_audio(frames[0]).kind == KIND_SPEAKER


def test_loud_clip_without_transcript_is_spoken() -> None:
    session = _named_session()
    events = [{"type": "audio", "pcm": b"\x01\x00" * 320, "sample_rate": 16000}]
    out = session.timed_reply(events, "")
    body = json.loads(next(item for item in out if isinstance(item, str)))
    assert body["action"] == "speak"
    assert body["reason"] == "heard"
    assert any(isinstance(item, bytes) for item in out)


def test_recognized_speech_without_the_name_stays_silent() -> None:
    session = _named_session()
    events = [{"type": "audio", "pcm": b"\x01\x00" * 320, "sample_rate": 16000}]
    heard = "今日は暑い"
    out = session.timed_reply(events, heard)
    body = json.loads(out[0])
    assert body["action"] == "silence"
    assert body["reason"] == "proactive_off"
    assert heard not in out[0]


def test_empty_transcript_keeps_the_reply() -> None:
    session = _named_session()
    out = session.timed_reply(
        [{"type": "audio", "pcm": b"\x01\x00" * 320, "sample_rate": 16000}],
        "",
    )
    body = json.loads(next(item for item in out if isinstance(item, str)))
    assert body["action"] == "speak"
    assert body["reason"] == "heard"
    assert any(isinstance(item, bytes) for item in out)
