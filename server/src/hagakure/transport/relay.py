"""Gemini の音声チャンクを、判断が付き次第 20 ms フレームにして返す。

PCM はメモリにだけ置く。呼び名が付くまでフレームは出さない。
ターンが終わっても書き起こしが空で音声があるときは、まとめて出す。
"""

from __future__ import annotations

from hagakure.audio.stream import StreamResampler
from hagakure.conversation.policy import Decision
from hagakure.transport.session import DeviceSession


class DownlinkRelay:
    def __init__(self, session: DeviceSession) -> None:
        self.session = session
        self.resampler = StreamResampler(24000, session.settings.sample_rate)
        self.pending = bytearray()
        self.action: str | None = None
        self.reason = ""
        self.saw_audio = False

    def push_audio(self, pcm: bytes, sample_rate: int, transcript: str) -> list[bytes]:
        if not pcm:
            return []
        self.saw_audio = True
        if sample_rate == self.session.settings.sample_rate:
            piece = pcm
        else:
            if sample_rate != self.resampler.source_rate:
                self.resampler = StreamResampler(sample_rate, self.session.settings.sample_rate)
            piece = self.resampler.push(pcm)
        if self.session.talk_mode == "gb":
            if self.action is None:
                self._commit(Decision("silence", "grok_unimplemented", False))
            self.pending.clear()
            return []
        if self.action == "silence":
            return []
        self.pending.extend(piece)
        if self.session.talk_mode == "cb" and self.action is None:
            self._commit(Decision("speak", "chat", False))
        elif self.action != "speak" and transcript.strip() and self.session.policy.addressed(transcript):
            decision = self.session.live_decision(transcript, True)
            if decision.action == "speak":
                self._commit(decision)
        if self.action == "speak":
            return self.session.take_speaker_frames(self.pending, pad=False)
        return []

    def finish(self, transcript: str) -> list[bytes]:
        self.pending.extend(self.resampler.flush())
        if self.action == "silence":
            self.pending.clear()
            return []
        if self.action != "speak" and self.session.talk_mode == "cb" and self.saw_audio:
            self._commit(Decision("speak", "chat", False))
        elif self.action != "speak":
            self._commit(self.session.live_decision(transcript, self.saw_audio))
        if self.action != "speak":
            self.pending.clear()
            return []
        return self.session.take_speaker_frames(self.pending, pad=True)

    def _commit(self, decision: Decision) -> None:
        if self.action is not None:
            return
        self.action = decision.action
        self.reason = decision.reason
        self.session.decision_log.append({"action": decision.action, "reason": decision.reason})
