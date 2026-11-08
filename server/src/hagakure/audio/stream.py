"""24 kHz のチャンクを、境界をまたいだまま 16 kHz へ詰める。ディスクには書かない。"""

from __future__ import annotations

import struct


class StreamResampler:
    """線形補間を、入力チャンクの途中で打ち切らない。"""

    def __init__(self, source_rate: int, target_rate: int) -> None:
        if source_rate <= 0 or target_rate <= 0:
            raise ValueError("サンプルレートが不正です")
        self.source_rate = source_rate
        self.target_rate = target_rate
        self._src: list[int] = []
        self._origin = 0
        self._next = 0

    def push(self, pcm: bytes) -> bytes:
        count = len(pcm) // 2
        if count:
            self._src.extend(struct.unpack("<" + "h" * count, pcm[: count * 2]))
        return self._pull(final=False)

    def flush(self) -> bytes:
        output = self._pull(final=True)
        self._src.clear()
        self._origin = 0
        self._next = 0
        return output

    def _pull(self, final: bool) -> bytes:
        if self.source_rate == self.target_rate:
            if not self._src:
                return b""
            output = struct.pack("<" + "h" * len(self._src), *self._src)
            self._origin += len(self._src)
            self._src.clear()
            return output
        output: list[int] = []
        while self._src:
            left = (self._next * self.source_rate) // self.target_rate
            local = left - self._origin
            if local < 0:
                self._next += 1
                continue
            if local >= len(self._src):
                break
            if local == len(self._src) - 1 and not final:
                break
            if local == len(self._src) - 1:
                mixed = self._src[local]
            else:
                frac = (self._next * self.source_rate) % self.target_rate
                mixed = (
                    self._src[local] * (self.target_rate - frac) + self._src[local + 1] * frac
                ) // self.target_rate
            if mixed > 32767:
                mixed = 32767
            elif mixed < -32768:
                mixed = -32768
            output.append(mixed)
            self._next += 1
        if self._src and not final:
            left = (self._next * self.source_rate) // self.target_rate
            drop = left - self._origin
            if drop > 0:
                del self._src[:drop]
                self._origin += drop
        if not output:
            return b""
        return struct.pack("<" + "h" * len(output), *output)
