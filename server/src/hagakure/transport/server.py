"""認証付き WebSocket。echo は PCM を返し、gemini は名前があるときだけ返す。"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime
from pathlib import Path

import websockets

from hagakure.adapters.voice import GeminiLiveBackend
from hagakure.audio.mock import mean_abs_s16le
from hagakure.config import Settings
from hagakure.conversation.policy import ConversationPolicy
from hagakure.transport.relay import DownlinkRelay
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


def _utterance_end(message: str | bytes) -> bool:
    if not isinstance(message, str):
        return False
    try:
        data = json.loads(message)
    except json.JSONDecodeError:
        return False
    return isinstance(data, dict) and data.get("type") == "utterance_end"


def cloud_skip_reason(pcm: bytes, talk_mode: str) -> str:
    """クラウドへ送らない理由。空文字なら送る。サンプルは残さない。"""
    if talk_mode == "gb":
        return "grok_unimplemented"
    if not pcm:
        return "empty"
    return ""


def should_call_cloud(pcm: bytes) -> bool:
    """空の録音は Gemini を開かない。中身の有無だけを見て、サンプルは残さない。"""
    return cloud_skip_reason(pcm, "ag") == ""


def _mark(started: float, name: str, **fields: object) -> None:
    elapsed = int((time.monotonic() - started) * 1000)
    tail = " ".join(f"{key}={value}" for key, value in fields.items())
    print(f"latency mark={name} t_ms={elapsed} {tail}".rstrip(), flush=True)


def _save_transcript(directory: Path, session_id: str, human: str, assistant: str) -> None:
    """会話専用ファイルへ保存。本文を通常ログや端末へは送らない。"""
    if not human and not assistant:
        return
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / f"{session_id}.txt"
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    lines = [f"[{stamp}]", f"あなた: {human or '（書き起こしなし）'}", f"はがくれ君: {assistant or '（書き起こしなし）'}", ""]
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as output:
        output.write("\n".join(lines) + "\n")


async def _gemini_turn(ws, session: DeviceSession, backend: GeminiLiveBackend | None) -> None:
    pcm = session.take_mic()
    started = time.monotonic()
    level = mean_abs_s16le(pcm)
    _mark(started, "utterance_end", bytes_in=len(pcm), level=level)
    print(f"voice_turn bytes_in={len(pcm)}", flush=True)
    skip = cloud_skip_reason(pcm, session.talk_mode)
    if skip:
        _mark(started, "cloud_skip", reason=skip)
        print(f"cloud_send=0 reason={skip}", flush=True)
        await _send_all(ws, [session._json({"type": "reply_done"})])
        return
    if backend is None:
        await _send_all(ws, session._error("voice_unavailable", "Gemini Live のキーがありません"))
        await _send_all(ws, [session._json({"type": "reply_done"})])
        return
    relay = DownlinkRelay(session)
    sent_frames = 0
    noted = False

    def note_decision() -> None:
        nonlocal noted
        if noted or relay.action is None:
            return
        noted = True
        _mark(
            started,
            "decision",
            action=relay.action,
            reason=relay.reason,
            chars=len(backend.last_input_text),
        )

    async def send_frames(frames: list[bytes]) -> None:
        nonlocal sent_frames
        if not frames:
            return
        if sent_frames == 0:
            _mark(started, "downlink_first", frames=len(frames))
        sent_frames += len(frames)
        await _send_all(ws, frames)

    _mark(started, "cloud_send")
    print("cloud_send=1", flush=True)
    try:
        async for event in backend.stream_turn(pcm):
            if event.get("type") != "audio":
                continue
            heard_before = relay.saw_audio
            frames = relay.push_audio(
                event.get("pcm") or b"",
                int(event.get("sample_rate") or 24000),
                backend.last_input_text,
            )
            if relay.saw_audio and not heard_before:
                _mark(started, "gemini_first_audio")
            note_decision()
            await send_frames(frames)
    except Exception as exc:
        text = str(exc)
        if backend.api_key:
            text = text.replace(backend.api_key, "[redacted]")
        print(f"voice_failed {type(exc).__name__} {text[:180]}", flush=True)
        await _send_all(ws, session._error("voice_failed", "音声の返答を取得できませんでした"))
        await _send_all(ws, [session._json({"type": "reply_done"})])
        return
    transcript = backend.last_input_text
    output_text = backend.last_output_text
    await send_frames(relay.finish(transcript))
    note_decision()
    backend.last_input_text = ""
    backend.last_output_text = ""
    if session.settings.save_transcripts and session.settings.transcript_dir is not None:
        try:
            _save_transcript(session.settings.transcript_dir, session.session_id, transcript, output_text)
        except OSError as exc:
            print(f"transcript_save_failed type={type(exc).__name__}", flush=True)
    notice = session._json(
        {
            "type": "policy_decision",
            "session_id": session.session_id,
            "action": relay.action,
            "reason": relay.reason,
            "addressed": relay.reason == "addressed",
            "phase": session.state.phase,
        }
    )
    _mark(started, "gemini_done", frames=sent_frames)
    print(
        "voice_decision "
        f"action={relay.action} reason={relay.reason} "
        f"chars={len(transcript)} level={level} late={int(backend.last_transcript_late)} "
        f"late_messages={backend.last_late_messages} "
        f"keys={','.join(sorted(backend.last_content_keys))}",
        flush=True,
    )
    print(
        f"voice_reply frames={sent_frames} bytes={sent_frames * 640} messages={backend.last_messages}",
        flush=True,
    )
    await _send_all(ws, [notice])
    await _send_all(ws, [session._json({"type": "reply_done"})])


async def handle_connection(ws, settings: Settings, policy: ConversationPolicy) -> None:
    if request_path(ws) not in {"/device", "/device/"}:
        await ws.close(1008, "not_found")
        return
    session = DeviceSession(settings, policy, header_token=bearer_token(ws))
    backend = None
    if settings.voice == "gemini" and settings.gemini_api_key:
        backend = GeminiLiveBackend(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            transcribe_output=settings.save_transcripts,
        )
    try:
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
                if settings.voice == "gemini" and _utterance_end(incoming):
                    await _gemini_turn(ws, session, backend)
                else:
                    await _send_all(ws, session.on_message(incoming))
                if session.closed:
                    await ws.close(session.close_code, session.close_reason)
                    return
        except websockets.ConnectionClosed:
            return
    finally:
        if backend is not None:
            await backend.close()


async def _send_all(ws, messages: list[str | bytes]) -> None:
    for item in messages:
        await ws.send(item)


async def start_server(settings: Settings, policy: ConversationPolicy):
    async def handler(ws) -> None:
        await handle_connection(ws, settings, policy)

    return await websockets.serve(handler, settings.host, settings.port)
