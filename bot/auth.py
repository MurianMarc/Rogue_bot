from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AuthorizedChat:
    chat_id: str
    name: str


class AllowlistStore:
    def __init__(self, path: Path, static_chats: tuple[str, ...] = ()):
        self.path = path
        self.static_chats = set(static_chats)
        self._chats = self._load()

    def authorize(self, chat_id: str, name: str = "") -> None:
        self._chats[chat_id] = AuthorizedChat(chat_id, name.strip() or chat_id)
        self._save()

    def remove(self, chat_id: str) -> bool:
        if chat_id not in self._chats:
            return False
        del self._chats[chat_id]
        self._save()
        return True

    def is_allowed(self, chat_id: str) -> bool:
        return chat_id in self.static_chats or chat_id in self._chats

    def all_chat_ids(self) -> list[str]:
        return sorted(self.static_chats | set(self._chats))

    def list(self) -> list[AuthorizedChat]:
        dynamic = list(self._chats.values())
        static = [
            AuthorizedChat(chat_id, f"{chat_id} (env)")
            for chat_id in self.static_chats
            if chat_id not in self._chats
        ]
        return sorted([*dynamic, *static], key=lambda chat: chat.name.casefold())

    def _load(self) -> dict[str, AuthorizedChat]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

        if isinstance(data, list):
            return {
                str(chat_id): AuthorizedChat(str(chat_id), str(chat_id))
                for chat_id in data
                if str(chat_id).strip()
            }

        if not isinstance(data, dict):
            return {}

        chats = data.get("chats", data)
        if not isinstance(chats, dict):
            return {}

        clean: dict[str, AuthorizedChat] = {}
        for chat_id, raw in chats.items():
            if not isinstance(chat_id, str) or not chat_id.strip():
                continue
            if isinstance(raw, dict):
                name = str(raw.get("name", chat_id))
            else:
                name = str(raw or chat_id)
            clean[chat_id] = AuthorizedChat(chat_id, name)
        return clean

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "chats": {
                chat.chat_id: {"name": chat.name}
                for chat in self._chats.values()
            }
        }
        self.path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
