"""環境変数と YAML から設定を読む。API キーはログに出さない。"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

from hagakure.conversation.policy import PolicyConfig


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8775
    preview_port: int = 8776
    device_token: str = ""
    sample_rate: int = 16000
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-live"
    voice: str = "echo"
    save_transcripts: bool = False
    transcript_dir: Path | None = None


def project_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "config" / "config.example.yaml").is_file():
            return parent
    raise FileNotFoundError("config/config.example.yaml が見つかりません")


def load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _env_int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key, "").strip()
    if not raw:
        return default
    return int(raw)


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    source = os.environ if env is None else env
    return Settings(
        host=source.get("HAGAKURE_HOST", "127.0.0.1").strip() or "127.0.0.1",
        port=_env_int(source, "HAGAKURE_PORT", 8775),
        preview_port=_env_int(source, "HAGAKURE_PREVIEW_PORT", 8776),
        device_token=source.get("HAGAKURE_DEVICE_TOKEN", "").strip(),
        sample_rate=16000,
        gemini_api_key=source.get("GEMINI_API_KEY", "").strip(),
        gemini_model=source.get("GEMINI_MODEL", "").strip() or "gemini-3.8-live",
        voice=source.get("HAGAKURE_VOICE", "").strip() or "echo",
        save_transcripts=source.get("HAGAKURE_SAVE_TRANSCRIPTS", "").strip() == "1",
        transcript_dir=project_root() / "data" / "conversations",
    )


def load_policy(path: Path) -> PolicyConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    conversation = data.get("conversation") or {}
    names = conversation.get("call_names") or ["はがくれ君"]
    return PolicyConfig(
        character_name=str(conversation.get("character_name") or "はがくれ君"),
        call_names=tuple(str(name) for name in names),
        language=str(conversation.get("language") or "ja"),
        mode=str(conversation.get("mode") or "stage_a"),
        proactive_enabled=bool(conversation.get("proactive_enabled", False)),
        proactive_threshold=float(conversation.get("proactive_threshold", 0.85)),
        minimum_silence_seconds=float(conversation.get("minimum_silence_seconds", 2.0)),
        proactive_cooldown_seconds=float(conversation.get("proactive_cooldown_seconds", 60)),
        max_proactive_utterances_per_5min=int(conversation.get("max_proactive_utterances_per_5min", 1)),
        max_proactive_utterance_seconds=float(conversation.get("max_proactive_utterance_seconds", 15)),
        barge_in_enabled=bool(conversation.get("barge_in_enabled", False)),
        store_raw_audio=bool(conversation.get("store_raw_audio", False)),
    )


def config_path(root: Path) -> Path:
    chosen = root / "config" / "config.yaml"
    if chosen.is_file():
        return chosen
    return root / "config" / "config.example.yaml"
