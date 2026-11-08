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


def resample_s16le(pcm: bytes, source_rate: int, target_rate: int) -> bytes:
    """16bit リトルエンディアンを線形補間で詰め直す。レートが同じならそのまま返す。"""
    if source_rate <= 0 or target_rate <= 0:
        raise ValueError("サンプルレートが不正です")
    count = len(pcm) // 2
    if count == 0 or source_rate == target_rate:
        return pcm[: count * 2]
    samples = struct.unpack("<" + "h" * count, pcm[: count * 2])
    out_count = count * target_rate // source_rate
    if out_count <= 0:
        return b""
    last = count - 1
    out: list[int] = []
    for index in range(out_count):
        pos = index * source_rate / target_rate
        left = int(pos)
        if left >= last:
            mixed = samples[last]
        else:
            frac = pos - left
            mixed = round(samples[left] * (1.0 - frac) + samples[left + 1] * frac)
        if mixed > 32767:
            mixed = 32767
        elif mixed < -32768:
            mixed = -32768
        out.append(mixed)
    return struct.pack("<" + "h" * out_count, *out)


def mean_abs_s16le(pcm: bytes) -> int:
    """サンプルの絶対値の平均。空や端数バイトは 0。"""
    count = len(pcm) // 2
    if count == 0:
        return 0
    samples = struct.unpack("<" + "h" * count, pcm[: count * 2])
    return sum(abs(sample) for sample in samples) // count


def rms_s16le(pcm: bytes) -> float:
    """0.0 から 1.0 程度の振幅。空や端数バイトは 0。"""
    count = len(pcm) // 2
    if count == 0:
        return 0.0
    samples = struct.unpack("<" + "h" * count, pcm[: count * 2])
    total = sum(sample * sample for sample in samples)
    return math.sqrt(total / count) / 32768.0
