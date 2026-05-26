from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from neonize.aioze.client import NewAClient
from neonize.aioze.events import MessageEv
from neonize.utils.enum import ChatPresence, ChatPresenceMedia
from neonize.utils.jid import Jid2String
from neonize.utils.message import extract_text

from .ai import OllamaClient
from .config import Settings

LOG = logging.getLogger(__name__)
Handler = Callable[["CommandContext", str], Awaitable[None]]


@dataclass(slots=True)
class CommandContext:
    app: "RogueBot"
    client: NewAClient
    message: MessageEv
    text: str
    chat_id: str

    @property
    def chat_jid(self):
        return self.message.Info.MessageSource.Chat

    async def reply(self, text: str) -> None:
        chunks = split_text(text, 3500)
        for index, chunk in enumerate(chunks):
            if index == 0:
                await self.client.reply_message(chunk, self.message, link_preview=False)
            else:
                await self.client.send_message(self.chat_jid, chunk, link_preview=False)

    async def typing(self, active: bool = True) -> None:
        state = (
            ChatPresence.CHAT_PRESENCE_COMPOSING
            if active
            else ChatPresence.CHAT_PRESENCE_PAUSED
        )
        await self.client.send_chat_presence(
            self.chat_jid, state, ChatPresenceMedia.CHAT_PRESENCE_MEDIA_TEXT
        )


class RogueBot:
    def __init__(self, settings: Settings, ai: OllamaClient):
        self.settings = settings
        self.ai = ai
        self.commands: dict[str, Handler] = {}

    def command(self, name: str) -> Callable[[Handler], Handler]:
        def decorator(handler: Handler) -> Handler:
            self.commands[name.casefold()] = handler
            return handler

        return decorator

    async def handle_message(self, client: NewAClient, message: MessageEv) -> None:
        if message.Info.MessageSource.IsFromMe:
            return

        chat_id = Jid2String(message.Info.MessageSource.Chat)
        if not self._chat_is_allowed(chat_id):
            return

        text = (extract_text(message.Message) or "").strip()
        sender = Jid2String(message.Info.MessageSource.Sender)
        LOG.info("chat=%s sender=%s text=%s", chat_id, sender, text or "[media]")

        if not text:
            return

        ctx = CommandContext(self, client, message, text, chat_id)
        parsed = self._parse_command(text)
        if parsed:
            name, args = parsed
            handler = self.commands.get(name)
            if handler:
                await handler(ctx, args)
            return

        if self.settings.enable_auto_question_mark and text.startswith("?"):
            handler = self.commands.get("ask")
            if handler:
                await handler(ctx, text[1:].strip())

    def _parse_command(self, text: str) -> tuple[str, str] | None:
        prefix = self.settings.cmd_prefix
        if not text.startswith(prefix):
            return None
        raw = text[len(prefix) :].strip()
        if not raw:
            return None
        name, _, args = raw.partition(" ")
        return name.casefold(), args.strip()

    def _chat_is_allowed(self, chat_id: str) -> bool:
        return not self.settings.allowed_chats or chat_id in self.settings.allowed_chats


def split_text(text: str, max_length: int) -> list[str]:
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    remaining = text.strip()
    while len(remaining) > max_length:
        split_at = remaining.rfind("\n", 0, max_length)
        if split_at < 500:
            split_at = max_length
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks
