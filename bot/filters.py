from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class FilterReply:
    kind: str
    value: str


class FilterStore:
    def __init__(self, path: Path):
        self.path = path
        self._filters = self._load()

    def add(self, chat_id: str, trigger: str, reply: str) -> None:
        self.add_text(chat_id, trigger, reply)

    def add_text(self, chat_id: str, trigger: str, reply: str) -> None:
        trigger = self._clean_trigger(trigger)
        if not trigger:
            raise ValueError("Filter trigger cannot be empty.")
        if not reply.strip():
            raise ValueError("Filter reply cannot be empty.")

        self._set(chat_id, trigger, FilterReply("text", reply.strip()))

    def add_sticker(self, chat_id: str, trigger: str, sticker_path: Path) -> None:
        trigger = self._clean_trigger(trigger)
        if not trigger:
            raise ValueError("Filter trigger cannot be empty.")
        if not sticker_path.exists():
            raise ValueError("Sticker file does not exist.")

        self._set(chat_id, trigger, FilterReply("sticker", sticker_path.name))

    def delete(self, chat_id: str, trigger: str) -> bool:
        trigger = self._clean_trigger(trigger)
        chat_filters = self._filters.get(chat_id, {})
        if trigger not in chat_filters:
            return False
        del chat_filters[trigger]
        if not chat_filters:
            self._filters.pop(chat_id, None)
        self._save()
        return True

    def clear(self, chat_id: str) -> int:
        count = len(self._filters.get(chat_id, {}))
        self._filters.pop(chat_id, None)
        self._save()
        return count

    def list(self, chat_id: str) -> list[str]:
        chat_filters = self._filters.get(chat_id, {})
        return [
            f"{trigger} ({reply.kind})"
            for trigger, reply in sorted(chat_filters.items())
        ]

    def match(self, chat_id: str, text: str) -> FilterReply | None:
        folded = text.casefold()
        filters = self._filters.get(chat_id, {})
        matches = [trigger for trigger in filters if trigger in folded]
        if not matches:
            return None
        trigger = sorted(matches, key=len, reverse=True)[0]
        return filters[trigger]

    def sticker_path(self, sticker_dir: Path, reply: FilterReply) -> Path:
        return sticker_dir / reply.value

    def _set(self, chat_id: str, trigger: str, reply: FilterReply) -> None:
        chat_filters = self._filters.setdefault(chat_id, {})
        chat_filters[trigger] = reply
        self._save()

    def _load(self) -> dict[str, dict[str, FilterReply]]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(data, dict):
            return {}

        clean: dict[str, dict[str, FilterReply]] = {}
        for chat_id, filters in data.items():
            if not isinstance(chat_id, str) or not isinstance(filters, dict):
                continue
            clean_filters: dict[str, FilterReply] = {}
            for trigger, raw_reply in filters.items():
                if not isinstance(trigger, str):
                    continue
                parsed = self._parse_reply(raw_reply)
                if parsed:
                    clean_filters[self._clean_trigger(trigger)] = parsed
            if clean_filters:
                clean[chat_id] = clean_filters
        return clean

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            chat_id: {
                trigger: {"type": reply.kind, "value": reply.value}
                for trigger, reply in filters.items()
            }
            for chat_id, filters in self._filters.items()
        }
        self.path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    @staticmethod
    def _parse_reply(raw_reply: object) -> FilterReply | None:
        if isinstance(raw_reply, str):
            value = raw_reply.strip()
            return FilterReply("text", value) if value else None

        if not isinstance(raw_reply, dict):
            return None

        kind = str(raw_reply.get("type", "text")).strip().casefold()
        value = str(raw_reply.get("value", "")).strip()
        if kind not in {"text", "sticker"} or not value:
            return None
        return FilterReply(kind, value)

    @staticmethod
    def _clean_trigger(trigger: str) -> str:
        return " ".join(trigger.casefold().strip().split())
