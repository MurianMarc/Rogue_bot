from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DEFAULT_SYSTEM_PROMPT = (
    "You are Rogue Bot v3, a WhatsApp assistant with a blunt, serious, "
    "confident voice. Be useful first. Keep replies concise. You may roast "
    "bad prompts lightly, but do not use hate speech, threats, or cruelty. "
    "If the user is confused, answer directly and act like you have the room "
    "under control."
)

DEFAULT_SUPER_SYSTEM_PROMPT = (
    "You are Rogue Super, the strongest reasoning profile of Rogue Bot v3. "
    "Be serious, confident, direct, and more thorough than normal ask. "
    "Use the extra intelligence for planning, code, debugging, strategy, "
    "and hard questions. Keep the attitude controlled, not childish."
)


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "y", "on"}


def _optional_bool(name: str) -> bool | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    return value.strip().casefold() in {"1", "true", "yes", "y", "on"}


def _bool_with_default(name: str, default: bool) -> bool:
    value = _optional_bool(name)
    return default if value is None else value


def _int(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _optional_int(name: str, *, allow_zero: bool = False) -> int | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    if parsed > 0 or (allow_zero and parsed == 0):
        return parsed
    return None


def _list(name: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in os.getenv(name, "").split(",") if item.strip())


@dataclass(frozen=True, slots=True)
class Settings:
    bot_name: str = os.getenv("BOT_NAME", "Rogue Bot")
    cmd_prefix: str = os.getenv("CMD_PREFIX", "!")
    phone_number: str = os.getenv("PH_NUMBER", "").strip().lstrip("+")
    wa_db: Path = Path(os.getenv("WA_DB", "sessions/rogue.sqlite3"))
    show_pair_push: bool = _bool("SHOW_PAIR_PUSH", True)
    allowed_chats: tuple[str, ...] = _list("ALLOWED_CHATS")

    ollama_url: str = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen3:8b")
    ollama_super_model: str = os.getenv("OLLAMA_SUPER_MODEL", "qwen3:14b")
    ollama_timeout_seconds: int = _int("OLLAMA_TIMEOUT_SECONDS", 240)
    ollama_keep_alive: str = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
    ollama_num_predict: int = _int("OLLAMA_NUM_PREDICT", 220)
    ollama_super_num_predict: int = _int("OLLAMA_SUPER_NUM_PREDICT", 220)
    ollama_think: bool = _bool("OLLAMA_THINK", False)
    ollama_super_think: bool = _bool("OLLAMA_SUPER_THINK", False)
    ollama_num_thread: int | None = _optional_int("OLLAMA_NUM_THREAD")
    ollama_num_gpu: int | None = _optional_int("OLLAMA_NUM_GPU", allow_zero=True)
    ollama_super_num_gpu: int | None = _optional_int("OLLAMA_SUPER_NUM_GPU", allow_zero=True)
    system_prompt: str = os.getenv(
        "SYSTEM_PROMPT",
        DEFAULT_SYSTEM_PROMPT,
    )
    super_system_prompt: str = os.getenv(
        "SUPER_SYSTEM_PROMPT",
        DEFAULT_SUPER_SYSTEM_PROMPT,
    )
    require_init: bool = _bool("REQUIRE_INIT", True)
    init_secret: str = os.getenv("INIT_SECRET", "").strip()
    allowlist_db: Path = Path(os.getenv("ALLOWLIST_DB", "storage/allowed_chats.json"))
    announce_online: bool = _bool("ANNOUNCE_ONLINE", True)
    online_message: str = os.getenv("ONLINE_MESSAGE", "bot is now online")
    super_cooldown_seconds: int = _int("SUPER_COOLDOWN_SECONDS", 120)
    enable_auto_question_mark: bool = _bool("ENABLE_AUTO_QUESTION_MARK", False)
    max_input_chars: int = _int("MAX_INPUT_CHARS", 1800)
    low_memory_mode: bool = _bool("LOW_MEMORY_MODE", False)
    filter_db: Path = Path(os.getenv("FILTER_DB", "storage/filters.json"))

    sticker_pack_name: str = os.getenv("STICKER_PACK_NAME", "Rogue Stickers")
    sticker_author: str = os.getenv("STICKER_AUTHOR", "Rogue Bot")
    sticker_crop: bool = _bool("STICKER_CROP", False)
    sticker_store_dir: Path = Path(os.getenv("STICKER_STORE_DIR", "storage/stickers"))
    sticker_max_input_mb: int = _int(
        "STICKER_MAX_INPUT_MB",
        4 if _bool("LOW_MEMORY_MODE", False) else 12,
    )
    sticker_animated_enabled: bool = _bool_with_default(
        "STICKER_ANIMATED_ENABLED",
        not _bool("LOW_MEMORY_MODE", False),
    )
    sticker_animated_seconds: int = _int(
        "STICKER_ANIMATED_SECONDS",
        3 if _bool("LOW_MEMORY_MODE", False) else 6,
    )
    sticker_animated_fps: int = _int(
        "STICKER_ANIMATED_FPS",
        8 if _bool("LOW_MEMORY_MODE", False) else 15,
    )
    scores_timeout_seconds: int = _int("SCORES_TIMEOUT_SECONDS", 12)
    scores_max_leagues: int = _int(
        "SCORES_MAX_LEAGUES",
        4 if _bool("LOW_MEMORY_MODE", False) else 7,
    )


settings = Settings()
