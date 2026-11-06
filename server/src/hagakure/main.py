"""Gateway と、原画プレビュー用のローカル HTTP を起動する。"""

from __future__ import annotations

import asyncio
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from hagakure import __version__
from hagakure.config import config_path, load_dotenv, load_policy, load_settings, project_root
from hagakure.conversation.policy import ConversationPolicy
from hagakure.transport.server import start_server


class _PreviewHandler(SimpleHTTPRequestHandler):
    directory: str

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=self.directory, **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/", "/index.html"}:
            self.send_response(302)
            self.send_header("Location", "/simulator/preview.html")
            self.end_headers()
            return
        super().do_GET()

    def log_message(self, fmt: str, *args) -> None:
        print(f"[preview] {self.address_string()} {fmt % args}")


def start_preview(root: Path, port: int) -> ThreadingHTTPServer:
    handler = type("BoundPreviewHandler", (_PreviewHandler,), {"directory": str(root)})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, name="hagakure-preview", daemon=True)
    thread.start()
    return server


def _check() -> int:
    root = project_root()
    load_dotenv(root / ".env")
    settings = load_settings()
    policy = ConversationPolicy(load_policy(config_path(root)))
    print(f"hagakure {__version__}")
    print(f"config: {config_path(root)}")
    print(f"listen: ws://{settings.host}:{settings.port}/device")
    print(f"preview: http://127.0.0.1:{settings.preview_port}/simulator/preview.html")
    print(f"character: {policy.config.character_name}")
    print(f"proactive_enabled: {str(policy.config.proactive_enabled).lower()}")
    print(f"token_required: {str(bool(settings.device_token)).lower()}")
    print("cloud: not_connected")
    return 0


async def _run() -> None:
    root = project_root()
    load_dotenv(root / ".env")
    settings = load_settings()
    policy = ConversationPolicy(load_policy(config_path(root)))
    if policy.config.store_raw_audio:
        print("store_raw_audio は true ですが、この版は音声を保存しません。")
    preview = start_preview(root, settings.preview_port)
    server = await start_server(settings, policy)
    sockets = server.sockets or []
    port = sockets[0].getsockname()[1] if sockets else settings.port
    print(f"はがくれ君 Gateway {__version__}", flush=True)
    print(f"音声: ws://{settings.host}:{port}/device", flush=True)
    print(f"プレビュー: http://127.0.0.1:{preview.server_address[1]}/simulator/preview.html", flush=True)
    print("クラウド API には接続していません。音声は保存しません。Ctrl+C で停止します。", flush=True)
    await server.serve_forever()


def main() -> None:
    if "--check" in sys.argv:
        raise SystemExit(_check())
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        print("停止しました。")
