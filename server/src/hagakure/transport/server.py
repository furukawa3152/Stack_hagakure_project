"""認証付き WebSocket。音声はエコーするだけで、ファイルには残さない。"""

from __future__ import annotations

import asyncio

import websockets

from hagakure.config import Settings
from hagakure.conversation.policy import ConversationPolicy
from hagakure.transport.session import DeviceSession


def request_path(ws) -> str:
    request = getattr(ws, "request", None)
    raw = getattr(request, "path", None) or getattr(ws, "path", "/") or "/"
    return str(raw).split("?", 1)[0]


def bearer_token(ws) -> str:
    request = getattr(ws, "request", None)
    headers = getattr(request, "headers", None)
    if headers is None:
        headers = getattr(ws, "request_headers", None)
    if headers is None:
        return ""
    auth = headers.get("Authorization") or headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


async def handle_connection(ws, settings: Settings, policy: ConversationPolicy) -> None:
    if request_path(ws) not in {"/device", "/device/"}:
        await ws.close(1008, "not_found")
        return
    session = DeviceSession(settings, policy, header_token=bearer_token(ws))
    try:
        incoming = await asyncio.wait_for(ws.recv(), timeout=10)
    except TimeoutError:
        await ws.close(1008, "hello_timeout")
        return
    except websockets.ConnectionClosed:
        return
    await _send_all(ws, session.on_message(incoming))
    if session.closed:
        await ws.close(session.close_code, session.close_reason)
        return
    try:
        async for incoming in ws:
            await _send_all(ws, session.on_message(incoming))
            if session.closed:
                await ws.close(session.close_code, session.close_reason)
                return
    except websockets.ConnectionClosed:
        return


async def _send_all(ws, messages: list[str | bytes]) -> None:
    for item in messages:
        await ws.send(item)


async def start_server(settings: Settings, policy: ConversationPolicy):
    async def handler(ws) -> None:
        await handle_connection(ws, settings, policy)

    return await websockets.serve(handler, settings.host, settings.port)
