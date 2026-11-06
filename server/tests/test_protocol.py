from hagakure.audio.mock import pcm_s16le_silence, pcm_s16le_tone, rms_s16le
from hagakure.protocol import KIND_MIC, KIND_SPEAKER, pack_audio, unpack_audio


def test_twenty_millisecond_frame_is_640_bytes() -> None:
    pcm = pcm_s16le_tone()
    assert len(pcm) == 640


def test_audio_frame_roundtrip() -> None:
    pcm = pcm_s16le_tone()
    raw = pack_audio(KIND_MIC, 7, 40, 16000, pcm, generation=3)
    frame = unpack_audio(raw)
    assert frame.kind == KIND_MIC
    assert frame.sequence == 7
    assert frame.timestamp_ms == 40
    assert frame.sample_rate == 16000
    assert frame.generation == 3
    assert frame.pcm == pcm


def test_speaker_kind_roundtrip() -> None:
    pcm = pcm_s16le_silence()
    frame = unpack_audio(pack_audio(KIND_SPEAKER, 1, 0, 16000, pcm))
    assert frame.kind == KIND_SPEAKER
    assert rms_s16le(frame.pcm) == 0


def test_short_frame_is_rejected() -> None:
    try:
        unpack_audio(b"HG")
    except ValueError as exc:
        assert "短" in str(exc)
    else:
        raise AssertionError("短いフレームを受け付けました")
