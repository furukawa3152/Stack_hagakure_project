from pathlib import Path

from hagakure.config import load_policy
from hagakure.conversation.policy import ConversationPolicy, PolicyConfig, TurnContext


def _ctx(**kwargs) -> TurnContext:
    base = dict(
        transcript="",
        human_speaking=False,
        silence_seconds=3.0,
        mic_enabled=True,
        ai_speaking=False,
        usefulness_score=0.0,
        pending_turn=False,
        now=0.0,
    )
    base.update(kwargs)
    return TurnContext(**base)


def test_example_config_is_stage_a() -> None:
    root = Path(__file__).resolve().parents[2]
    policy = load_policy(root / "config" / "config.example.yaml")
    assert policy.character_name == "はがくれ君"
    assert "はがくれ" in policy.call_names
    assert policy.proactive_enabled is False
    assert policy.store_raw_audio is False


def test_name_is_answered_and_plain_talk_is_not() -> None:
    policy = ConversationPolicy()
    named = policy.decide(_ctx(transcript="はがくれ君、どう思う？"))
    assert named.action == "speak"
    assert named.reason == "addressed"
    plain = policy.decide(_ctx(transcript="今度の勉強会どうしよう", usefulness_score=0.95))
    assert plain.action == "silence"
    assert plain.reason == "proactive_off"


def test_mic_off_and_overlap_block_speech() -> None:
    policy = ConversationPolicy()
    muted = policy.decide(_ctx(transcript="はがくれ君", mic_enabled=False))
    assert muted.reason == "mic_off"
    assert muted.addressed is True
    talking = policy.decide(_ctx(transcript="はがくれ君", human_speaking=True))
    assert talking.reason == "human_speaking"
    overlap = policy.decide(_ctx(transcript="はがくれ君", ai_speaking=True))
    assert overlap.reason == "ai_speaking"


def test_barge_in_flag_does_not_talk_over_a_person() -> None:
    policy = ConversationPolicy(PolicyConfig(barge_in_enabled=True))
    decision = policy.decide(_ctx(transcript="はがくれ君", human_speaking=True))
    assert decision.action == "silence"
    assert decision.reason == "human_speaking"


def test_pending_turn_is_cancelled_when_a_person_starts() -> None:
    policy = ConversationPolicy(PolicyConfig(proactive_enabled=True))
    decision = policy.decide(_ctx(transcript="続きがある", human_speaking=True, pending_turn=True))
    assert decision.action == "cancel"
    assert decision.reason == "human_started"


def test_proactive_respects_threshold_silence_and_cooldown() -> None:
    policy = ConversationPolicy(
        PolicyConfig(
            proactive_enabled=True,
            proactive_threshold=0.85,
            minimum_silence_seconds=2.0,
            proactive_cooldown_seconds=60,
            max_proactive_utterances_per_5min=1,
        )
    )
    low = policy.decide(_ctx(transcript="資料の抜けがある", usefulness_score=0.4, silence_seconds=3))
    assert low.reason == "low_value"
    early = policy.decide(_ctx(transcript="資料の抜けがある", usefulness_score=0.95, silence_seconds=0.4))
    assert early.reason == "not_enough_silence"
    first = policy.decide(_ctx(transcript="資料の抜けがある", usefulness_score=0.95, silence_seconds=2.5, now=100))
    assert first.reason == "proactive"
    cooled = policy.decide(_ctx(transcript="別の補足", usefulness_score=0.99, silence_seconds=3, now=130))
    assert cooled.reason == "cooldown"
    later = policy.decide(_ctx(transcript="さらに補足", usefulness_score=0.99, silence_seconds=3, now=200))
    assert later.reason == "rate_limited"


def test_empty_transcript_stays_quiet() -> None:
    policy = ConversationPolicy(PolicyConfig(proactive_enabled=True))
    decision = policy.decide(_ctx(transcript="   ", usefulness_score=1, silence_seconds=5))
    assert decision.reason == "low_confidence"


def test_alias_chonmage_kun_counts_as_a_call() -> None:
    policy = ConversationPolicy()
    decision = policy.decide(_ctx(transcript="ちょんまげ君、お願い"))
    assert decision.reason == "addressed"
