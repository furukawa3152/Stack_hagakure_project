"""実機マイクの代わりに使う PCM。ディスクには書かない。"""

from __future__ import annotations

import math
import struct


def pcm_s16le_tone(
    frequency: float = 440.0,
    seconds: float = 0.02,
    sample_rate: int = 16000,
    amplitude: float = 0.2,
) -> bytes:
    """20ms なら 640 バイトになる 16 kHz / 16bit / mono のサイン波。"""
    count = int(sample_rate * seconds)
    samples = []
    for i in range(count):
        value = amplitude * math.sin(2 * math.pi * frequency * i / sample_rate)
        samples.append(int(max(-1.0, min(1.0, value)) * 32767))
    return struct.pack("<" + "h" * count, *samples)


def pcm_s16le_silence(seconds: float = 0.02, sample_rate: int = 16000) -> bytes:
    count = int(sample_rate * seconds)
    return b"\x00\x00" * count


def rms_s16le(pcm: bytes) -> float:
    """0.0 から 1.0 程度の振幅。空や端数バイトは 0。"""
    count = len(pcm) // 2
    if count == 0:
        return 0.0
    samples = struct.unpack("<" + "h" * count, pcm[: count * 2])
    total = sum(sample * sample for sample in samples)
    return math.sqrt(total / count) / 32768.0
