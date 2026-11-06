"""C方式の発言判断。段階Aは名前を呼ばれたときだけ話す。

書き起こし本文は保存しない。理由コードだけを返す。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PolicyConfig:
    character_name: str = "はがくれ君"
    call_names: tuple[str, ...] = ("はがくれ君", "はがくれ", "ちょんまげ君")
    language: str = "ja"
    mode: str = "stage_a"
    proactive_enabled: bool = False
    proactive_threshold: float = 0.85
    minimum_silence_seconds: float = 2.0
    proactive_cooldown_seconds: float = 60.0
    max_proactive_utterances_per_5min: int = 1
    max_proactive_utterance_seconds: float = 15.0
    barge_in_enabled: bool = False
    store_raw_audio: bool = False


@dataclass(frozen=True)
class TurnContext:
    transcript: str
    human_speaking: bool
    silence_seconds: float
    mic_enabled: bool
    ai_speaking: bool = False
    usefulness_score: float = 0.0
    pending_turn: bool = False
    now: float = 0.0


@dataclass(frozen=True)
class Decision:
    action: str
    reason: str
    addressed: bool


def _folded(text: str) -> str:
    return "".join(text.split()).casefold()


@dataclass
class ConversationPolicy:
    config: PolicyConfig = field(default_factory=PolicyConfig)
    _proactive_at: list[float] = field(default_factory=list)

    def addressed(self, transcript: str) -> bool:
        folded = _folded(transcript)
        if not folded:
            return False
        for name in self.config.call_names:
            token = _folded(name)
            if token and token in folded:
                return True
        return False

    def decide(self, ctx: TurnContext) -> Decision:
        is_addressed = self.addressed(ctx.transcript)
        if not ctx.mic_enabled:
            return Decision("silence", "mic_off", is_addressed)
        # AEC 未評価のため、設定が true でも人の発話には被せない。
        if ctx.ai_speaking:
            return Decision("silence", "ai_speaking", is_addressed)
        if ctx.human_speaking and ctx.pending_turn:
            return Decision("cancel", "human_started", is_addressed)
        if ctx.human_speaking:
            return Decision("silence", "human_speaking", is_addressed)
        if not ctx.transcript.strip():
            return Decision("silence", "low_confidence", False)
        if is_addressed:
            return Decision("speak", "addressed", True)
        if not self.config.proactive_enabled:
            return Decision("silence", "proactive_off", False)
        if ctx.usefulness_score < self.config.proactive_threshold:
            return Decision("silence", "low_value", False)
        if ctx.silence_seconds < self.config.minimum_silence_seconds:
            return Decision("silence", "not_enough_silence", False)
        window_start = ctx.now - 300.0
        self._proactive_at = [stamp for stamp in self._proactive_at if stamp >= window_start]
        if self._proactive_at and ctx.now - self._proactive_at[-1] < self.config.proactive_cooldown_seconds:
            return Decision("silence", "cooldown", False)
        if len(self._proactive_at) >= self.config.max_proactive_utterances_per_5min:
            return Decision("silence", "rate_limited", False)
        self._proactive_at.append(ctx.now)
        return Decision("speak", "proactive", False)
