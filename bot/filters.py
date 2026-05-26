from __future__ import annotations

import json
from pathlib import Path


class FilterStore:
    def __init__(self, path: Path):
        self.path = path
        self._filters = self._load()

    def add(self, chat_id: str, trigger: str, reply: str) -> None:
        trigger = self._clean_trigger(trigger)
        if not trigger:
            raise ValueError("Filter trigger cannot be empty.")
        if not reply.strip():
            raise ValueError("Filter reply cannot be empty.")

        chat_filters = self._filters.setdefault(chat_id, {})
        chat_filters[trigger] = reply.strip()
        self._save()

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
        return sorted(self._filters.get(chat_id, {}))

    def match(self, chat_id: str, text: str) -> str | None:
        folded = text.casefold()
        filters = self._filters.get(chat_id, {})
        matches = [trigger for trigger in filters if trigger in folded]
        if not matches:
            return None
        trigger = sorted(matches, key=len, reverse=True)[0]
        return filters[trigger]

    def _load(self) -> dict[str, dict[str, str]]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(data, dict):
            return {}

        clean: dict[str, dict[str, str]] = {}
        for chat_id, filters in data.items():
            if not isinstance(chat_id, str) or not isinstance(filters, dict):
                continue
            clean[chat_id] = {
                self._clean_trigger(trigger): str(reply)
                for trigger, reply in filters.items()
                if isinstance(trigger, str) and str(reply).strip()
            }
        return clean

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._filters, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    @staticmethod
    def _clean_trigger(trigger: str) -> str:
        return " ".join(trigger.casefold().strip().split())
