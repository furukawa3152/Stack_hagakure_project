"""VoiceBackend。端末のエコーとは別口で、Gemini Live へ PCM を渡す。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable

INPUT_RATE = 16000
OUTPUT_RATE = 24000
DEFAULT_MODEL = "gemini-3.8-live"
DEFAULT_VOICE = "Puck"
_INPUT_MIME = "audio/pcm;rate=16000"
_SYSTEM = (
    "以下の設定のキャラクター「HAGAKURE君」になりきって回答してください。"
    "基本設定。"
    "名前は「HAGAKURE君」です。"
    "一人称は「拙者」です。"
    "「です」「ます」などの一般的な敬語は使わず、親しみやすい口調で回答してください。"
    "侍らしい表現や「ござる」を自然に使ってください。"
    "すべての文に無理やり「ござる」を付ける必要はありません。"
    "キャラクター性よりも、回答の分かりやすさと正確さを優先してください。"
    "話す言語は日本語だけに固定する。相手が他の言語で話しても、英語や他の言語には切り替えない。"
)


class VoiceBackend:
    async def connect(self) -> None:
        raise NotImplementedError

    async def send_audio(self, pcm: bytes) -> None:
        raise NotImplementedError

    async def receive_events(self) -> AsyncIterator[dict]:
        raise NotImplementedError
        yield  # pragma: no cover

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

    async def receive_events(self) -> AsyncIterator[dict]:
        while self._queue:
            yield {"type": "audio", "pcm": self._queue.pop(0), "sample_rate": INPUT_RATE}

    async def interrupt(self) -> None:
        self._queue.clear()

    async def close(self) -> None:
        self.connected = False
        self._queue.clear()


def live_connect_config(transcribe_output: bool = False):
    """音声だけを返す接続設定。ツールは付けない。入力の書き起こしは日本語に寄せる。"""
    from google.genai import types

    from hagakure.conversation.policy import PolicyConfig

    return types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        system_instruction=_SYSTEM,
        speech_config=types.SpeechConfig(
            language_code="ja-JP",
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=DEFAULT_VOICE)
            ),
        ),
        input_audio_transcription=types.AudioTranscriptionConfig(
            language_codes=["ja-JP"],
            custom_vocabulary=list(PolicyConfig().call_names),
        ),
        output_audio_transcription=(types.AudioTranscriptionConfig() if transcribe_output else None),
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(disabled=True),
        ),
    )


def turn_is_complete(message: object) -> bool:
    content = getattr(message, "server_content", None)
    return bool(getattr(content, "turn_complete", False))


def _transcription_text(content: object, name: str) -> str:
    item = getattr(content, name, None)
    if item is None:
        return ""
    text = getattr(item, "text", None)
    return str(text) if text else ""


def input_transcript_piece(message: object) -> tuple[str, str]:
    """入力の確定文と、途中文を返す。ログには出さない。"""
    content = getattr(message, "server_content", None)
    if content is None:
        return "", ""
    return (
        _transcription_text(content, "input_transcription"),
        _transcription_text(content, "interim_input_transcription"),
    )


def events_from_message(message: object) -> list[dict]:
    """モデルの音声チャンクだけを取り出す。本文も PCM もログに残さない。"""
    content = getattr(message, "server_content", None)
    if content is None:
        return []
    events: list[dict] = []
    if getattr(content, "interrupted", False):
        events.append({"type": "interrupted"})
    turn = getattr(content, "model_turn", None)
    parts = getattr(turn, "parts", None) or []
    for part in parts:
        inline = getattr(part, "inline_data", None)
        data = getattr(inline, "data", None)
        if not data:
            continue
        mime = str(getattr(inline, "mime_type", "") or "")
        rate = OUTPUT_RATE
        marker = "rate="
        if marker in mime:
            raw = mime.split(marker, 1)[1].split(";", 1)[0]
            if raw.isdigit():
                rate = int(raw)
        events.append({"type": "audio", "pcm": data, "sample_rate": rate})
    return events


async def _open_live(api_key: str, model: str, transcribe_output: bool = False):
    from google import genai

    client = genai.Client(api_key=api_key)
    context = client.aio.live.connect(model=model, config=live_connect_config(transcribe_output))
    session = await context.__aenter__()
    return session, context


class GeminiLiveBackend(VoiceBackend):
    """16 kHz の PCM を Gemini Live へ渡し、戻りは 24 kHz として扱う。

    キーが空のときは API を呼ばない。端末へ返す前に 16 kHz へ詰め直す。
    """

    def __init__(
        self,
        api_key: str = "",
        model: str = "",
        transcribe_output: bool = False,
        opener: Callable[[], Awaitable[object]] | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model or DEFAULT_MODEL
        self.transcribe_output = transcribe_output
        self._opener = opener
        self._session: object | None = None
        self._context: object | None = None
        self.last_messages = 0
        self.last_input_text = ""
        self.last_output_text = ""
        self.last_transcript_late = False
        self.last_content_keys: set[str] = set()
        self.last_late_messages = 0

    async def connect(self) -> None:
        if self._session is not None:
            raise RuntimeError("Gemini Live はすでに開いています。")
        if self._opener is not None:
            self._session = await self._opener()
            return
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY が空です。Gemini Live には接続していません。")
        self._session, self._context = await _open_live(self.api_key, self.model, self.transcribe_output)

    async def collect_reply(self, pcm: bytes, timeout: float = 15.0) -> list[dict]:
        """16 kHz の PCM を 1 ターン送り、返ったイベントを集める。中身はログに出さない。"""
        self.last_input_text = ""
        self.last_messages = 0
        self.last_transcript_late = False
        self.last_content_keys = set()
        self.last_late_messages = 0
        if not pcm:
            return []
        if self._session is None:
            await self.connect()
        events: list[dict] = []
        done = asyncio.Event()

        async def _read() -> None:
            latest_interim = ""
            try:
                async for message in self._session.receive():  # type: ignore[attr-defined]
                    self.last_messages += 1
                    events.extend(events_from_message(message))
                    self._note_content(message)
                    final, interim = input_transcript_piece(message)
                    if final:
                        self.last_input_text += final
                    if interim:
                        latest_interim = interim
            finally:
                if not self.last_input_text:
                    self.last_input_text = latest_interim
                done.set()

        reader = asyncio.create_task(_read())
        try:
            from google.genai import types

            await self._session.send_realtime_input(activity_start=types.ActivityStart())  # type: ignore[attr-defined]
            view = memoryview(pcm)
            for offset in range(0, len(view), 3200):
                await self.send_audio(bytes(view[offset : offset + 3200]))
            await self._session.send_realtime_input(activity_end=types.ActivityEnd())  # type: ignore[attr-defined]
            await asyncio.wait_for(done.wait(), timeout)
        except TimeoutError:
            pass
        finally:
            reader.cancel()
            try:
                await reader
            except asyncio.CancelledError:
                pass
        await self._read_late_transcript()
        return events

    async def stream_turn(self, pcm: bytes, timeout: float = 15.0):
        """音声チャンクを届き次第返す。セッションは開いたまま再利用する。

        空の PCM では接続しない。遅い書き起こしは待たない。本文は出さない。
        """
        self.last_input_text = ""
        self.last_output_text = ""
        self.last_messages = 0
        self.last_transcript_late = False
        self.last_content_keys = set()
        self.last_late_messages = 0
        if not pcm:
            return
        if self._session is None:
            await self.connect()
        queue: asyncio.Queue[dict | Exception | None] = asyncio.Queue()

        async def _read() -> None:
            latest_interim = ""
            try:
                async for message in self._session.receive():  # type: ignore[attr-defined]
                    self.last_messages += 1
                    self._note_content(message)
                    final, interim = input_transcript_piece(message)
                    if final:
                        self.last_input_text += final
                    if interim:
                        latest_interim = interim
                    content = getattr(message, "server_content", None)
                    self.last_output_text += _transcription_text(content, "output_transcription")
                    for event in events_from_message(message):
                        await queue.put(event)
            finally:
                if not self.last_input_text:
                    self.last_input_text = latest_interim
                await queue.put(None)

        async def _send() -> None:
            try:
                from google.genai import types

                await self._session.send_realtime_input(activity_start=types.ActivityStart())  # type: ignore[attr-defined]
                view = memoryview(pcm)
                for offset in range(0, len(view), 3200):
                    await self.send_audio(bytes(view[offset : offset + 3200]))
                await self._session.send_realtime_input(activity_end=types.ActivityEnd())  # type: ignore[attr-defined]
            except Exception as exc:
                await queue.put(exc)

        reader = asyncio.create_task(_read())
        sender = asyncio.create_task(_send())
        try:
            loop = asyncio.get_running_loop()
            deadline = loop.time() + timeout
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), remaining)
                except TimeoutError:
                    break
                if item is None:
                    break
                if isinstance(item, Exception):
                    raise item
                yield item
        finally:
            sender.cancel()
            reader.cancel()
            for task in (sender, reader):
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    async def _read_late_transcript(self) -> None:
        """公開の receive はターン完了で止まる。呼び名はその後に来ることがある。"""
        if self.last_input_text or self._session is None:
            return
        receive_one = getattr(self._session, "_receive", None)
        if receive_one is None:
            return
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 2.0
        latest_interim = ""
        while loop.time() < deadline:
            timeout = deadline - loop.time()
            if self.last_input_text:
                timeout = min(timeout, 0.4)
            try:
                message = await asyncio.wait_for(receive_one(), timeout)
            except TimeoutError:
                break
            self.last_late_messages += 1
            self._note_content(message)
            final, interim = input_transcript_piece(message)
            if final:
                self.last_transcript_late = True
                self.last_input_text += final
            elif interim:
                self.last_transcript_late = True
                latest_interim = interim
        if not self.last_input_text:
            self.last_input_text = latest_interim

    def _note_content(self, message: object) -> None:
        content = getattr(message, "server_content", None)
        if content is None:
            self.last_content_keys.add("no_server_content")
            return
        dump = getattr(content, "model_dump", None)
        if dump is None:
            self.last_content_keys.add("no_dump")
            return
        self.last_content_keys.update(str(key) for key in dump(exclude_none=True))

    async def send_audio(self, pcm: bytes) -> None:
        if self._session is None:
            raise RuntimeError("Gemini Live はまだ開いていません。")
        if not pcm:
            return
        from google.genai import types

        await self._session.send_realtime_input(  # type: ignore[attr-defined]
            audio=types.Blob(data=pcm, mime_type=_INPUT_MIME)
        )

    async def receive_events(self) -> AsyncIterator[dict]:
        if self._session is None:
            raise RuntimeError("Gemini Live はまだ開いていません。")
        async for message in self._session.receive():  # type: ignore[attr-defined]
            for event in events_from_message(message):
                yield event

    async def interrupt(self) -> None:
        raise NotImplementedError("Gemini Live の発話中断はまだ未実装です。")

    async def close(self) -> None:
        session = self._session
        context = self._context
        self._session = None
        self._context = None
        if context is not None:
            await context.__aexit__(None, None, None)  # type: ignore[attr-defined]
            return
        close = getattr(session, "aclose", None)
        if close is not None:
            await close()
