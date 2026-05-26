from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "y", "on"}


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
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    ollama_fast_model: str = os.getenv("OLLAMA_FAST_MODEL", "qwen3:1.7b")
    ollama_timeout_seconds: int = _int("OLLAMA_TIMEOUT_SECONDS", 90)
    ollama_keep_alive: str = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
    ollama_num_predict: int = _int("OLLAMA_NUM_PREDICT", 220)
    ollama_fast_num_predict: int = _int("OLLAMA_FAST_NUM_PREDICT", 160)
    ollama_think: bool = _bool("OLLAMA_THINK", False)
    ollama_fast_think: bool = _bool("OLLAMA_FAST_THINK", False)
    ollama_num_thread: int | None = _optional_int("OLLAMA_NUM_THREAD")
    ollama_num_gpu: int | None = _optional_int("OLLAMA_NUM_GPU", allow_zero=True)
    ollama_fast_num_gpu: int | None = _optional_int("OLLAMA_FAST_NUM_GPU", allow_zero=True)
    system_prompt: str = os.getenv(
        "SYSTEM_PROMPT",
        "You are a helpful WhatsApp assistant. Keep answers clear, friendly, and concise.",
    )
    enable_auto_question_mark: bool = _bool("ENABLE_AUTO_QUESTION_MARK", False)
    max_input_chars: int = _int("MAX_INPUT_CHARS", 1800)

    sticker_pack_name: str = os.getenv("STICKER_PACK_NAME", "Rogue Stickers")
    sticker_author: str = os.getenv("STICKER_AUTHOR", "Rogue Bot")
    sticker_crop: bool = _bool("STICKER_CROP", False)


settings = Settings()
