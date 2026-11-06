"""VoiceBackend。Phase 1 はエコーだけで、Gemini には接続しない。"""

from __future__ import annotations


class VoiceBackend:
    async def connect(self) -> None:
        raise NotImplementedError

    async def send_audio(self, pcm: bytes) -> None:
        raise NotImplementedError

    async def receive_events(self):
        raise NotImplementedError

    async def interrupt(self) -> None:
        raise NotImplementedError

    async def close(self) -> None:
        raise NotImplementedError


class EchoVoiceBackend(VoiceBackend):
    """受け取った PCM をそのまま返す。モデル呼び出しではない。"""

    def __init__(self) -> None:
        self.connected = False
        self._queue: list[bytes] = []

    async def connect(self) -> None:
        self.connected = True

    async def send_audio(self, pcm: bytes) -> None:
        if not self.connected:
            raise RuntimeError("エコー用の音声口が開いていません")
        self._queue.append(pcm)

    async def receive_events(self):
        while self._queue:
            yield {"type": "audio", "pcm": self._queue.pop(0)}

    async def interrupt(self) -> None:
        self._queue.clear()

    async def close(self) -> None:
        self.connected = False
        self._queue.clear()


class GeminiLiveBackend(VoiceBackend):
    """接続口だけ。キーがあっても、この段階では API を呼ばない。"""

    async def connect(self) -> None:
        raise NotImplementedError("Gemini Live は Phase 3 で接続します。現在は未実装です。")
