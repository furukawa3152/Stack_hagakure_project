"""1 台の Core2 とのセッション。Gemini のときはエコーせず、名前があるときだけ返す。"""

from __future__ import annotations

import json
import secrets
import time
import uuid
from dataclasses import dataclass, field

from hagakure.audio.mock import resample_s16le, rms_s16le
from hagakure.avatar.controller import AvatarController
from hagakure.config import Settings
from hagakure.conversation.policy import ConversationPolicy, Decision, TurnContext
from hagakure.conversation.state import SessionState
from hagakure.protocol import KIND_MIC, KIND_SPEAKER, pack_audio, unpack_audio

_LOOPBACK = {"127.0.0.1", "localhost", "::1"}
_FRAME_BYTES = 640
_MAX_MIC_BYTES = 16000 * 2 * 10


@dataclass
class DeviceSession:
    settings: Settings
    policy: ConversationPolicy
    header_token: str = ""
    avatar: AvatarController = field(default_factory=AvatarController)
    state: SessionState = field(default_factory=SessionState)
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    authed: bool = False
    mic_enabled: bool = False
    talk_mode: str = "ag"
    closed: bool = False
    close_code: int = 1000
    close_reason: str = ""
    device_id: str = ""
    downlink_seq: int = 0
    generation: int = 1
    decision_log: list[dict[str, str]] = field(default_factory=list)
    mic_dropped: int = 0
    _mic: bytearray = field(default_factory=bytearray)

    def on_message(self, message: str | bytes) -> list[str | bytes]:
        if self.closed:
            return []
        if isinstance(message, bytes):
            return self._on_binary(message)
        return self._on_text(message)

    def _on_text(self, message: str) -> list[str | bytes]:
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return self._fail("bad_json", "JSONとして読めません")
        if not isinstance(data, dict) or not isinstance(data.get("type"), str):
            return self._error("bad_message", "type が必要です")
        kind = data["type"]
        if not self.authed:
            if kind != "hello":
                return self._fail("hello_required", "最初のメッセージは hello です")
            return self._hello(data)
        handlers = {
            "ping": self._ping,
            "mute": self._mute,
            "device_state": self._device_state,
            "touch": self._touch,
            "mode": self._mode,
            "transcript": self._transcript,
            "interrupt": self._interrupt,
            "utterance_end": self._utterance_end,
        }
        if kind == "hello":
            return self._error("already_open", "セッションは開始済みです")
        handler = handlers.get(kind)
        if handler is None:
            return self._error("unknown_type", "未対応の type です")
        return handler(data)

    def _hello(self, data: dict) -> list[str | bytes]:
        if data.get("protocol_version", 1) != 1:
            return self._fail("bad_version", "protocol_version 1 のみです")
        presented = str(data.get("token") or self.header_token or "")
        if not self._token_ok(presented):
            self.closed = True
            self.close_code = 4001
            self.close_reason = "unauthorized"
            return [self._json({"type": "error", "code": "unauthorized", "message": "認証に失敗しました"})]
        audio = data.get("audio_in") or {}
        if audio.get("format") not in (None, "pcm_s16le"):
            return self._fail("bad_audio_format", "音声は pcm_s16le のみ受け付けます")
        rate = int(audio.get("rate") or self.settings.sample_rate)
        if rate != self.settings.sample_rate:
            return self._fail("bad_sample_rate", "入力は 16000 Hz です")
        self.authed = True
        self.device_id = str(data.get("device_id") or "")
        self.mic_enabled = False
        self.state.transition("connect")
        return [
            self._json(
                {
                    "type": "hello_ack",
                    "protocol_version": 1,
                    "session_id": self.session_id,
                    "gateway": "hagakure",
                    "device_id": self.device_id,
                    "mic_enabled": False,
                    "phase": self.state.phase,
                    "cloud_active": self.cloud_armed,
                    "audio_out": {
                        "rate": self.settings.sample_rate,
                        "channels": 1,
                        "format": "pcm_s16le",
                    },
                }
            )
        ]

    def _token_ok(self, presented: str) -> bool:
        expected = self.settings.device_token
        if not expected:
            return self.settings.host in _LOOPBACK
        if len(presented) != len(expected):
            return False
        return secrets.compare_digest(presented, expected)

    def _ping(self, _data: dict) -> list[str | bytes]:
        return [self._json({"type": "pong", "session_id": self.session_id})]

    def _mute(self, data: dict) -> list[str | bytes]:
        enabled = bool(data.get("mic_enabled", False))
        self.mic_enabled = enabled
        if enabled and self.state.phase == "muted":
            self.state.transition("unmute")
        elif not enabled and self.state.phase != "muted":
            self.state.transition("mute")
            self.generation += 1
        return [
            self._json(
                {
                    "type": "mute_ack",
                    "session_id": self.session_id,
                    "mic_enabled": self.mic_enabled,
                    "phase": self.state.phase,
                    "expression": self.avatar.expression_for(self.state.phase),
                }
            )
        ]

    def _device_state(self, _data: dict) -> list[str | bytes]:
        return [
            self._json(
                {
                    "type": "device_state_ack",
                    "session_id": self.session_id,
                    "mic_enabled": self.mic_enabled,
                    "phase": self.state.phase,
                }
            )
        ]

    def _mode(self, data: dict) -> list[str | bytes]:
        value = data.get("value")
        if value not in ("cb", "ag", "gb"):
            return self._error("bad_mode", "mode は cb ag gb です")
        self.talk_mode = str(value)
        return [
            self._json(
                {
                    "type": "mode_ack",
                    "session_id": self.session_id,
                    "value": self.talk_mode,
                    "available": self.talk_mode != "gb",
                }
            )
        ]

    def _touch(self, data: dict) -> list[str | bytes]:
        gesture = data.get("gesture") if isinstance(data.get("gesture"), str) else ""
        return [
            self._json(
                {
                    "type": "touch_ack",
                    "session_id": self.session_id,
                    "gesture": gesture,
                }
            )
        ]

    def _transcript(self, data: dict) -> list[str | bytes]:
        ctx = TurnContext(
            transcript=str(data.get("text") or ""),
            human_speaking=bool(data.get("human_speaking", False)),
            silence_seconds=float(data.get("silence_seconds") or 0),
            mic_enabled=self.mic_enabled,
            ai_speaking=self.state.phase == "speaking",
            usefulness_score=float(data.get("usefulness_score") or 0),
            pending_turn=self.state.phase == "waiting_turn",
            now=time.monotonic(),
        )
        decision = self.policy.decide(ctx)
        self.decision_log.append({"action": decision.action, "reason": decision.reason})
        if decision.action == "cancel" and self.state.phase == "waiting_turn":
            self.state.transition("cancel_turn")
        return [
            self._json(
                {
                    "type": "policy_decision",
                    "session_id": self.session_id,
                    "action": decision.action,
                    "reason": decision.reason,
                    "addressed": decision.addressed,
                    "phase": self.state.phase,
                }
            )
        ]

    @property
    def cloud_armed(self) -> bool:
        return self.settings.voice == "gemini" and bool(self.settings.gemini_api_key)

    def _remember_mic(self, pcm: bytes) -> None:
        room = _MAX_MIC_BYTES - len(self._mic)
        if room <= 0:
            self.mic_dropped += 1
            return
        if len(pcm) > room:
            self._mic.extend(pcm[:room])
            self.mic_dropped += 1
            return
        self._mic.extend(pcm)

    def take_mic(self) -> bytes:
        pcm = bytes(self._mic)
        self._mic.clear()
        return pcm

    def live_decision(self, transcript: str, has_audio: bool) -> Decision:
        """段階A。空の書き起こしで音声があるときだけ heard にする。本文は残さない。"""
        decision = self.policy.decide(
            TurnContext(
                transcript=transcript,
                human_speaking=False,
                silence_seconds=0.0,
                mic_enabled=self.mic_enabled,
                ai_speaking=False,
                now=time.monotonic(),
            )
        )
        if decision.reason == "low_confidence" and has_audio:
            return Decision("speak", "heard", False)
        return decision

    def take_speaker_frames(self, pending: bytearray, *, pad: bool) -> list[bytes]:
        """16 kHz の余りをまたいで 640 バイトにする。pad のとき最後を無音で埋める。"""
        frames: list[bytes] = []
        while len(pending) >= _FRAME_BYTES:
            frames.append(self._speaker_frame(bytes(pending[:_FRAME_BYTES])))
            del pending[:_FRAME_BYTES]
        if pad and pending:
            frames.append(self._speaker_frame(bytes(pending).ljust(_FRAME_BYTES, b"\x00")))
            pending.clear()
        return frames

    def _speaker_frame(self, pcm: bytes) -> bytes:
        self.downlink_seq += 1
        return pack_audio(
            kind=KIND_SPEAKER,
            sequence=self.downlink_seq,
            timestamp_ms=self.downlink_seq * 20,
            sample_rate=self.settings.sample_rate,
            pcm=pcm,
            generation=self.generation,
        )

    def speaker_frames(self, events: list[dict]) -> list[bytes]:
        pcm = bytearray()
        for event in events:
            if event.get("type") != "audio":
                continue
            rate = int(event.get("sample_rate") or self.settings.sample_rate)
            pcm.extend(resample_s16le(event["pcm"], rate, self.settings.sample_rate))
        if not pcm:
            return []
        pending = bytearray(pcm)
        frames = self.take_speaker_frames(pending, pad=True)
        return frames

    def timed_reply(self, events: list[dict], transcript: str) -> list[str | bytes]:
        """段階A。呼び名が書き起こしにあるときだけ、その有無で黙る。

        書き起こしが空のときは、モデルが返した音声を捨てない。本文は載せず、理由だけ返す。
        """
        has_audio = any(event.get("type") == "audio" for event in events)
        decision = self.live_decision(transcript, has_audio)
        self.decision_log.append({"action": decision.action, "reason": decision.reason})
        notice = self._json(
            {
                "type": "policy_decision",
                "session_id": self.session_id,
                "action": decision.action,
                "reason": decision.reason,
                "addressed": decision.addressed,
                "phase": self.state.phase,
            }
        )
        if decision.action != "speak":
            return [notice]
        return [notice, *self.speaker_frames(events)]

    def _utterance_end(self, _data: dict) -> list[str | bytes]:
        return [
            self._json(
                {
                    "type": "utterance_ack",
                    "session_id": self.session_id,
                    "mic_bytes": len(self._mic),
                }
            )
        ]

    def _interrupt(self, _data: dict) -> list[str | bytes]:
        self.generation += 1
        if self.state.phase == "speaking":
            self.state.transition("interrupt")
        return [
            self._json(
                {
                    "type": "interrupt_ack",
                    "session_id": self.session_id,
                    "generation": self.generation,
                    "phase": self.state.phase,
                }
            )
        ]

    def _on_binary(self, message: bytes) -> list[str | bytes]:
        if not self.authed:
            return self._fail("hello_required", "hello の前に音声は送れません")
        try:
            frame = unpack_audio(message)
        except ValueError as exc:
            return self._error("bad_frame", str(exc))
        if frame.kind != KIND_MIC:
            return self._error("bad_frame_kind", "端末からの音声はマイク種別だけです")
        if not self.mic_enabled:
            return []
        if frame.sample_rate != self.settings.sample_rate:
            return self._error("bad_sample_rate", "サンプルレートが一致しません")
        if self.settings.voice == "gemini":
            self._remember_mic(frame.pcm)
            mouth = self.avatar.mouth_open_from_rms(rms_s16le(frame.pcm))
            return [
                self._json(
                    {
                        "type": "expression",
                        "session_id": self.session_id,
                        "value": "listening",
                        "mouth": mouth,
                        "generation": self.generation,
                    }
                )
            ]
        mouth = self.avatar.mouth_open_from_rms(rms_s16le(frame.pcm))
        self.downlink_seq += 1
        echo = pack_audio(
            kind=KIND_SPEAKER,
            sequence=self.downlink_seq,
            timestamp_ms=frame.timestamp_ms,
            sample_rate=frame.sample_rate,
            pcm=frame.pcm,
            generation=self.generation,
        )
        notice = self._json(
            {
                "type": "expression",
                "session_id": self.session_id,
                "value": "listening",
                "mouth": mouth,
                "generation": self.generation,
            }
        )
        return [echo, notice]

    def _json(self, payload: dict) -> str:
        return json.dumps(payload, ensure_ascii=False)

    def _error(self, code: str, message: str) -> list[str]:
        return [self._json({"type": "error", "code": code, "message": message})]

    def _fail(self, code: str, message: str) -> list[str]:
        self.closed = True
        self.close_code = 1008
        self.close_reason = code
        return self._error(code, message)
