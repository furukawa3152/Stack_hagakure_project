"""Core2 と Gateway の音声フレーム。

20 バイトのリトルエンディアンヘッダの後ろに PCM ペイロードを置く。
JSON の制御メッセージとは混ぜない。
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

MAGIC = b"HG"
VERSION = 1
KIND_MIC = 1
KIND_SPEAKER = 2
HEADER = struct.Struct("<2sBBIIHHI")
HEADER_SIZE = HEADER.size  # 20


@dataclass(frozen=True)
class AudioFrame:
    kind: int
    sequence: int
    timestamp_ms: int
    sample_rate: int
    generation: int
    pcm: bytes


def pack_audio(
    kind: int,
    sequence: int,
    timestamp_ms: int,
    sample_rate: int,
    pcm: bytes,
    generation: int = 0,
) -> bytes:
    if kind not in (KIND_MIC, KIND_SPEAKER):
        raise ValueError("音声の種別が不正です")
    if len(pcm) > 65535:
        raise ValueError("音声フレームが大きすぎます")
    header = HEADER.pack(
        MAGIC,
        VERSION,
        kind,
        sequence & 0xFFFFFFFF,
        timestamp_ms & 0xFFFFFFFF,
        sample_rate & 0xFFFF,
        len(pcm),
        generation & 0xFFFFFFFF,
    )
    return header + pcm


def unpack_audio(frame: bytes) -> AudioFrame:
    if len(frame) < HEADER_SIZE:
        raise ValueError("音声フレームが短すぎます")
    magic, version, kind, sequence, timestamp_ms, sample_rate, nbytes, generation = HEADER.unpack_from(
        frame
    )
    if magic != MAGIC or version != VERSION:
        raise ValueError("音声ヘッダが不正です")
    if kind not in (KIND_MIC, KIND_SPEAKER):
        raise ValueError("音声の種別が不正です")
    payload = frame[HEADER_SIZE:]
    if len(payload) != nbytes:
        raise ValueError("音声の長さが一致しません")
    return AudioFrame(
        kind=kind,
        sequence=sequence,
        timestamp_ms=timestamp_ms,
        sample_rate=sample_rate,
        generation=generation,
        pcm=payload,
    )
