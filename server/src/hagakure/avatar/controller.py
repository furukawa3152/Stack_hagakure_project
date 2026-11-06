"""原画そのものはここでは描かない。状態名と口の開きだけを決める。"""

from __future__ import annotations


EXPRESSIONS = {
    "idle": "neutral",
    "listening": "listen",
    "thinking": "thinking",
    "waiting_turn": "waiting",
    "speaking": "speak",
    "interrupted": "surprised",
    "muted": "muted",
    "disconnected": "sleep",
    "error": "error",
}


class AvatarController:
    def expression_for(self, phase: str) -> str:
        return EXPRESSIONS.get(phase, "neutral")

    def mouth_open_from_rms(self, rms: float) -> float:
        opened = max(0.0, rms) * 6.0
        if opened > 1:
            return 1.0
        return round(opened, 3)
