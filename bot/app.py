from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

from neonize.aioze.client import NewAClient
from neonize.aioze.events import MessageEv
from neonize.utils.enum import ChatPresence, ChatPresenceMedia
from neonize.utils.jid import JID, Jid2String
from neonize.utils.message import extract_text

from .ai import OllamaClient
from .auth import AllowlistStore
from .config import Settings

LOG = logging.getLogger(__name__)
Handler = Callable[["CommandContext", str], Awaitable[None]]
TextHandler = Callable[["CommandContext", str], Awaitable[bool]]
RawHandler = Callable[["CommandContext"], Awaitable[bool]]
UNKNOWN_COMMAND_REPLIES = (
    "bro are you okay?",
    "please use your glasses",
    "nga what",
    "i will just assume you mean !help",
    "no.",
    "crayyy wayyyy",
    "wrong command buddy",
    "licky licky",
    "go back to primary one",
    "ummm",
    "wksowjwiwssosijs since we speaking jargon now",
    "?",
    "estoy loco",
    "son 😭",
    "come again?",
    "lol, you do you",
    "i'm not sure what you mean, but ok",
    "i'm just a bot, but that doesn't sound right",
    "kindly off your phone",
    "i'm not sure that's a real command",
    "error 404: command not found",
    "i'm not sure how to respond to that",
    "huh?",
    "i don't understand, but that's fine",
    "i'm not sure what you want, but ok",
    "that's not a command, but interesting",
)


@dataclass(slots=True)
class CommandContext:
    app: "RogueBot"
    client: NewAClient
    message: MessageEv
    text: str
    chat_id: str
    received_at: float

    @property
    def chat_jid(self):
        return self.message.Info.MessageSource.Chat

    @property
    def sender_jid(self):
        return self.message.Info.MessageSource.Sender

    @property
    def sender_id(self) -> str:
        sender = Jid2String(self.sender_jid)
        return sender or self.chat_id

    @property
    def is_group(self) -> bool:
        return bool(self.message.Info.MessageSource.IsGroup or self.chat_id.endswith("@g.us"))

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
        self.allowlist = AllowlistStore(settings.allowlist_db, settings.allowed_chats)
        self.commands: dict[str, Handler] = {}
        self.raw_handlers: list[RawHandler] = []
        self.text_handlers: list[TextHandler] = []
        self.started_at = time.perf_counter()

    def command(self, name: str) -> Callable[[Handler], Handler]:
        def decorator(handler: Handler) -> Handler:
            self.commands[name.casefold()] = handler
            return handler

        return decorator

    def on_raw(self, handler: RawHandler) -> RawHandler:
        self.raw_handlers.append(handler)
        return handler

    def on_text(self, handler: TextHandler) -> TextHandler:
        self.text_handlers.append(handler)
        return handler

    async def handle_message(self, client: NewAClient, message: MessageEv) -> None:
        received_at = time.perf_counter()
        if message.Info.MessageSource.IsFromMe:
            return

        chat_id = Jid2String(message.Info.MessageSource.Chat)
        text = (extract_text(message.Message) or "").strip()
        sender = Jid2String(message.Info.MessageSource.Sender)
        LOG.info("chat=%s sender=%s text=%s", chat_id, sender, text or "[media]")

        ctx = CommandContext(self, client, message, text, chat_id, received_at)
        parsed = self._parse_command(text) if text else None
        if not self._chat_is_allowed(chat_id):
            if parsed and parsed[0] == "init":
                handler = self.commands.get("init")
                if handler:
                    await handler(ctx, parsed[1])
            return

        for handler in self.raw_handlers:
            if await handler(ctx):
                return

        if not text:
            return

        if parsed:
            name, args = parsed
            handler = self.commands.get(name)
            if handler:
                await handler(ctx, args)
            else:
                await ctx.reply(random.choice(UNKNOWN_COMMAND_REPLIES))
            return

        for handler in self.text_handlers:
            if await handler(ctx, text):
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
        if self.allowlist.is_allowed(chat_id):
            return True
        return not self.settings.require_init and not self.settings.allowed_chats

    async def announce_online(self, client: NewAClient) -> None:
        if not self.settings.announce_online:
            return
        for chat_id in self.allowlist.all_chat_ids():
            try:
                await client.send_message(string_to_jid(chat_id), self.settings.online_message, link_preview=False)
            except Exception as exc:
                LOG.warning("Could not announce online to %s: %s", chat_id, exc)


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


def string_to_jid(value: str) -> JID:
    user, _, server = value.partition("@")
    return JID(User=user, Server=server)
