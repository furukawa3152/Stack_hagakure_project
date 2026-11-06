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
