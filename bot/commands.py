from __future__ import annotations

import time

from neonize.utils.message import extract_text

from .app import CommandContext, RogueBot
from .filters import FilterStore
from .games import GameHub
from .media import download_media, find_sticker_source, quoted_message
from .scores import live_scores
from .stickers import create_sticker, sticker_summary


def register_commands(app: RogueBot) -> None:
    prefix = app.settings.cmd_prefix
    filters = FilterStore(app.settings.filter_db)
    games = GameHub()

    @app.on_text
    async def filter_listener(ctx: CommandContext, text: str) -> bool:
        reply = filters.match(ctx.chat_id, text)
        if not reply:
            return False
        await ctx.reply(reply)
        return True

    @app.command("help")
    async def help_command(ctx: CommandContext, args: str) -> None:
        await ctx.reply(
            "\n".join(
                [
                    f"{app.settings.bot_name} commands:",
                    f"{prefix}ask <question> - use the smart GPU model",
                    f"{prefix}fast <question> - use the lighter CPU model",
                    f"{prefix}models - show active AI models",
                    f"{prefix}scores - show current football scores",
                    f"{prefix}onyx - show Onyx integration status",
                    f"{prefix}game start - play Rogue Trial",
                    f"{prefix}filter <word> | <reply> - save an auto-reply filter",
                    f"{prefix}filters - list this chat's filters",
                    f"{prefix}del_filter <word|all> - delete filters",
                    f"{prefix}sticker [name] - make a sticker from media or replied media",
                    f"{prefix}stickers - show stored sticker files",
                    f"{prefix}reset - clear this chat's short AI memory",
                    f"{prefix}id - show this chat ID for ALLOWED_CHATS",
                    f"{prefix}ping - check latency and uptime",
                    f"{prefix}help - show this menu",
                ]
            )
        )

    @app.command("ping")
    async def ping_command(ctx: CommandContext, args: str) -> None:
        latency_ms = int((time.perf_counter() - ctx.received_at) * 1000)
        uptime_seconds = int(time.perf_counter() - app.started_at)
        await ctx.reply(f"pong | latency {latency_ms}ms | uptime {format_duration(uptime_seconds)}")

    @app.command("id")
    async def id_command(ctx: CommandContext, args: str) -> None:
        await ctx.reply(f"Chat ID:\n{ctx.chat_id}")

    @app.command("reset")
    async def reset_command(ctx: CommandContext, args: str) -> None:
        app.ai.reset(ctx.chat_id)
        await ctx.reply("Memory reset for this chat.")

    @app.command("ask")
    async def ask_command(ctx: CommandContext, args: str) -> None:
        await answer_question(ctx, args, "smart")

    @app.command("fast")
    async def fast_command(ctx: CommandContext, args: str) -> None:
        await answer_question(ctx, args, "fast")

    @app.command("models")
    async def models_command(ctx: CommandContext, args: str) -> None:
        await ctx.reply(
            "\n".join(
                [
                    "Active AI profiles:",
                    f"Smart GPU: {app.settings.ollama_model}",
                    f"Fast CPU: {app.settings.ollama_fast_model}",
                ]
            )
        )

    @app.command("scores")
    async def scores_command(ctx: CommandContext, args: str) -> None:
        await ctx.typing(True)
        try:
            await ctx.reply(await live_scores(app.settings))
        except Exception as exc:
            await ctx.reply(f"Could not fetch scores: {exc}")
        finally:
            await ctx.typing(False)

    @app.command("onyx")
    async def onyx_command(ctx: CommandContext, args: str) -> None:
        await ctx.reply(
            "\n".join(
                [
                    "Onyx check:",
                    "Yes, Onyx can share this bot's local Ollama models.",
                    "The Ollama Onyx guide is for wiring Onyx to Ollama as a chat/RAG UI.",
                    "Direct WhatsApp-to-Onyx mode needs an Onyx API service URL, so this bot keeps using Ollama directly for now.",
                ]
            )
        )

    @app.command("game")
    async def game_command(ctx: CommandContext, args: str) -> None:
        await games.handle(ctx, args)

    @app.command("filter")
    async def filter_command(ctx: CommandContext, args: str) -> None:
        parsed = parse_filter_args(ctx, args)
        if not parsed:
            await ctx.reply(
                f"Use {prefix}filter <word> | <reply>, "
                f"or reply to text with {prefix}filter <word>."
            )
            return
        trigger, reply = parsed
        try:
            filters.add(ctx.chat_id, trigger, reply)
        except ValueError as exc:
            await ctx.reply(str(exc))
            return
        await ctx.reply(f"Saved filter: {trigger.casefold()}")

    @app.command("filters")
    async def filters_command(ctx: CommandContext, args: str) -> None:
        triggers = filters.list(ctx.chat_id)
        if not triggers:
            await ctx.reply("No filters saved in this chat.")
            return
        await ctx.reply("Filters:\n" + "\n".join(f"- {trigger}" for trigger in triggers))

    @app.command("del_filter")
    async def delete_filter_command(ctx: CommandContext, args: str) -> None:
        trigger = args.strip()
        if not trigger:
            await ctx.reply(f"Use {prefix}del_filter <word>, or {prefix}del_filter all.")
            return
        if trigger.casefold() == "all":
            count = filters.clear(ctx.chat_id)
            await ctx.reply(f"Deleted {count} filter(s).")
            return
        if filters.delete(ctx.chat_id, trigger):
            await ctx.reply(f"Deleted filter: {trigger.casefold()}")
        else:
            await ctx.reply(f"No filter named {trigger.casefold()} exists here.")

    @app.command("sticker")
    async def sticker_command(ctx: CommandContext, args: str) -> None:
        source = find_sticker_source(ctx.message.Message)
        if not source:
            await ctx.reply(
                f"Send an image/video/GIF with caption {prefix}sticker, "
                f"or reply to media with {prefix}sticker."
            )
            return

        await ctx.typing(True)
        try:
            media = await download_media(ctx.client, source)
            sticker_name = args.strip() or app.settings.sticker_author
            created = await create_sticker(media, source, app.settings, sticker_name)
            await ctx.client.send_sticker(
                ctx.chat_jid,
                created.webp,
                quoted=ctx.message,
                name=sticker_name,
                packname=app.settings.sticker_pack_name,
                passthrough=True,
            )
        except Exception as exc:
            await ctx.reply(f"I could not make that sticker: {exc}")
        finally:
            await ctx.typing(False)

    @app.command("stickers")
    async def stickers_command(ctx: CommandContext, args: str) -> None:
        await ctx.reply(sticker_summary(app.settings))

    async def answer_question(ctx: CommandContext, args: str, profile: str) -> None:
        question = args.strip()
        command = "fast" if profile == "fast" else "ask"
        model = (
            app.settings.ollama_fast_model
            if profile == "fast"
            else app.settings.ollama_model
        )

        if not question:
            await ctx.reply(f"Send {prefix}{command} followed by your question.")
            return

        if len(question) > app.settings.max_input_chars:
            await ctx.reply(
                f"That question is too long. Keep it under "
                f"{app.settings.max_input_chars} characters."
            )
            return

        await ctx.typing(True)
        try:
            answer = await app.ai.ask(ctx.chat_id, question, profile=profile)
            await ctx.reply(answer)
        except Exception as exc:
            await ctx.reply(
                "\n".join(
                    [
                        "I could not reach the local AI.",
                        "Make sure Ollama is running and the model is installed:",
                        f"ollama pull {model}",
                        "ollama serve",
                        f"Error: {exc}",
                    ]
                )
            )
        finally:
            await ctx.typing(False)


def parse_filter_args(ctx: CommandContext, args: str) -> tuple[str, str] | None:
    raw = args.strip()
    if not raw:
        return None

    if "|" in raw:
        trigger, _, reply = raw.partition("|")
        return trigger.strip(), reply.strip()

    quoted = quoted_message(ctx.message.Message)
    quoted_text = (extract_text(quoted) or "").strip() if quoted else ""
    if quoted_text:
        return raw, quoted_text

    trigger, _, reply = raw.partition(" ")
    if trigger and reply:
        return trigger.strip(), reply.strip()
    return None


def format_duration(seconds: int) -> str:
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"
