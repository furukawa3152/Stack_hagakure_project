import pytest

from hagakure.conversation.state import IllegalTransition, SessionState


def test_connect_starts_muted() -> None:
    state = SessionState()
    assert state.transition("connect") == "muted"
    assert state.transition("unmute") == "idle"


def test_listen_think_speak_cycle() -> None:
    state = SessionState()
    state.transition("connect")
    state.transition("unmute")
    assert state.transition("speech_start") == "listening"
    assert state.transition("address") == "thinking"
    assert state.transition("wait") == "waiting_turn"
    assert state.transition("speak_start") == "speaking"
    assert state.transition("speak_end") == "idle"


def test_mute_from_speaking_and_interrupt() -> None:
    state = SessionState()
    state.transition("connect")
    state.transition("unmute")
    state.transition("address")
    state.transition("speak_start")
    assert state.transition("interrupt") == "interrupted"
    assert state.transition("settle") == "idle"
    state.transition("address")
    state.transition("speak_start")
    assert state.transition("mute") == "muted"


def test_cancel_waiting_turn() -> None:
    state = SessionState()
    state.transition("connect")
    state.transition("unmute")
    state.transition("address")
    state.transition("wait")
    assert state.transition("cancel_turn") == "idle"


def test_cannot_speak_from_idle() -> None:
    state = SessionState()
    state.transition("connect")
    state.transition("unmute")
    with pytest.raises(IllegalTransition):
        state.transition("speak_start")


def test_disconnect_and_fail() -> None:
    state = SessionState()
    state.transition("connect")
    assert state.transition("fail") == "error"
    assert state.transition("recover") == "muted"
    assert state.transition("disconnect") == "disconnected"
