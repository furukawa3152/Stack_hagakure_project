"""画面と音声が共有する状態。許可した遷移以外は進まない。"""

from __future__ import annotations


class IllegalTransition(Exception):
    pass


# 仕様 4.3 の状態名。値はプロトコルでも使う。
PHASES = (
    "idle",
    "listening",
    "thinking",
    "waiting_turn",
    "speaking",
    "interrupted",
    "muted",
    "disconnected",
    "error",
)

_TRANSITIONS: dict[tuple[str, str], str] = {
    ("disconnected", "connect"): "muted",
    ("muted", "unmute"): "idle",
    ("idle", "mute"): "muted",
    ("listening", "mute"): "muted",
    ("thinking", "mute"): "muted",
    ("waiting_turn", "mute"): "muted",
    ("speaking", "mute"): "muted",
    ("interrupted", "mute"): "muted",
    ("error", "mute"): "muted",
    ("idle", "speech_start"): "listening",
    ("listening", "speech_end"): "idle",
    ("listening", "address"): "thinking",
    ("idle", "address"): "thinking",
    ("thinking", "wait"): "waiting_turn",
    ("thinking", "speak_start"): "speaking",
    ("waiting_turn", "speak_start"): "speaking",
    ("waiting_turn", "cancel_turn"): "idle",
    ("speaking", "speak_end"): "idle",
    ("speaking", "interrupt"): "interrupted",
    ("interrupted", "settle"): "idle",
    ("error", "recover"): "muted",
}


class SessionState:
    def __init__(self, phase: str = "disconnected") -> None:
        if phase not in PHASES:
            raise ValueError(f"未知の状態です: {phase}")
        self.phase = phase

    def transition(self, event: str) -> str:
        if event == "disconnect":
            self.phase = "disconnected"
            return self.phase
        if event == "fail":
            self.phase = "error"
            return self.phase
        nxt = _TRANSITIONS.get((self.phase, event))
        if nxt is None:
            raise IllegalTransition(f"{self.phase} から {event} には進めません")
        self.phase = nxt
        return self.phase
