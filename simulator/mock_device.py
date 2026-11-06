"""Core2 の代わりにダミー PCM を送り、エコーが返るか確認する。

使い方（リポジトリのルートで、server の仮想環境から）:

    server/.venv/Scripts/python simulator/mock_device.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server" / "src"))

from hagakure.audio.mock import pcm_s16le_tone  # noqa: E402
from hagakure.protocol import KIND_MIC, pack_audio, unpack_audio  # noqa: E402


async def run(url: str, token: str) -> None:
    import websockets

    pcm = pcm_s16le_tone()
    async with websockets.connect(url) as ws:
        await ws.send(
            json.dumps(
                {
                    "type": "hello",
                    "protocol_version": 1,
                    "device_id": "mock-core2",
                    "token": token,
                    "audio_in": {"rate": 16000, "channels": 1, "format": "pcm_s16le"},
                }
            )
        )
        ack = json.loads(await ws.recv())
        if ack.get("type") != "hello_ack":
            raise SystemExit(f"hello_ack ではありません: {ack}")
        if ack.get("mic_enabled") is not False:
            raise SystemExit("開始時はマイク OFF である必要があります")
        await ws.send(json.dumps({"type": "mute", "mic_enabled": True}))
        mute = json.loads(await ws.recv())
        if mute.get("mic_enabled") is not True:
            raise SystemExit(f"マイクを有効にできません: {mute}")
        await ws.send(pack_audio(KIND_MIC, 1, 0, 16000, pcm))
        first = await asyncio.wait_for(ws.recv(), timeout=2)
        second = await asyncio.wait_for(ws.recv(), timeout=2)
        binary = first if isinstance(first, bytes) else second
        frame = unpack_audio(binary)
        if frame.pcm != pcm:
            raise SystemExit("エコーの PCM が送信データと違います")
        print(f"確認: session={ack['session_id']} echo_bytes={len(frame.pcm)} cloud={ack['cloud_active']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="はがくれ君 Gateway への音声エコー確認")
    parser.add_argument("--url", default="ws://127.0.0.1:8775/device")
    parser.add_argument("--token", default="")
    args = parser.parse_args()
    asyncio.run(run(args.url, args.token))


if __name__ == "__main__":
    main()
