from __future__ import annotations

import random
import time

from neonize.utils.message import extract_text

from .app import CommandContext, RogueBot
from .filters import FilterStore
from .games import GameHub
from .media import download_media, find_sticker_source, quoted_message
from .scores import live_scores
from .stickers import create_sticker, sticker_summary

DENIAL_REPLIES = ("no.", "lmao", "son😭")
COMMAND_DENIAL_CHANCE = 0.375
FILTER_TRIGGER_DENIAL_CHANCE = 0.10


def register_commands(app: RogueBot) -> None:
    prefix = app.settings.cmd_prefix
    filters = FilterStore(app.settings.filter_db)
    games = GameHub(app)
    super_last_used: dict[str, float] = {}

    @app.on_text(allow_unlisted=True)
    async def game_private_listener(ctx: CommandContext, text: str) -> bool:
        return await games.handle_private_text(ctx, text)

    @app.on_text
    async def filter_listener(ctx: CommandContext, text: str) -> bool:
        reply = filters.match(ctx.chat_id, text)
        if not reply:
            return False
        if random.random() < FILTER_TRIGGER_DENIAL_CHANCE:
            await ctx.reply("nah reply the filter yourself")
            return True
        if reply.kind == "text":
            await ctx.reply(reply.value)
            return True

        sticker_path = filters.sticker_path(app.settings.sticker_store_dir, reply)
        if not sticker_path.exists():
            await ctx.reply("That sticker filter points to a missing file.")
            return True

        await ctx.client.send_sticker(
            ctx.chat_jid,
            sticker_path.read_bytes(),
            quoted=ctx.message,
            name=app.settings.sticker_author,
            packname=app.settings.sticker_pack_name,
            passthrough=True,
        )
        return True

    @app.command("help")
    async def help_command(ctx: CommandContext, args: str) -> None:
        await ctx.reply(
            "\n".join(
                [
                    f"{app.settings.bot_name} commands:",
                    f"{prefix}init - authorize this DM/group",
                    f"{prefix}ask <question> - use qwen3:8b",
                    f"{prefix}super <question> - use qwen3:14b with cooldown",
                    f"{prefix}models - show active AI models",
                    f"{prefix}scores - show current football scores",
                    f"{prefix}game start [players] - open Mafia lobby, 9 minimum",
                    f"{prefix}game begin - host starts the Mafia game",
                    f"{prefix}join <nickname> - join a Mafia lobby",
                    f"{prefix}skip - skip Mafia discussion",
                    f"{prefix}nominate <nickname> - nominate a Mafia suspect",
                    f"{prefix}vote <nickname> - vote for a Mafia nominee",
                    f"{prefix}team <message> - Mafia/Medic private team chat in DM",
                    f"{prefix}kill/{prefix}protect/{prefix}investigate <nickname> - Mafia night DM actions",
                    f"{prefix}filter <word> | <reply> - save a text auto-reply",
                    f"{prefix}filter <word> - save a sticker filter from replied media",
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

    @app.command("init")
    async def init_command(ctx: CommandContext, args: str) -> None:
        provided = args.strip()
        if app.settings.init_secret and provided != app.settings.init_secret:
            await ctx.reply("Wrong init secret. Nice try.")
            return

        app.allowlist.authorize(ctx.chat_id)
        await ctx.reply("Authorized. This chat is now on my allowlist.")

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

    @app.command("super")
    async def super_command(ctx: CommandContext, args: str) -> None:
        now = time.monotonic()
        last_used = super_last_used.get(ctx.chat_id, 0)
        wait_seconds = int(app.settings.super_cooldown_seconds - (now - last_used))
        if wait_seconds > 0:
            await ctx.reply(f"Super ask is cooling down. Try again in {wait_seconds}s.")
            return
        if await answer_question(ctx, args, "super"):
            super_last_used[ctx.chat_id] = time.monotonic()

    @app.command("models")
    async def models_command(ctx: CommandContext, args: str) -> None:
        await ctx.reply(
            "\n".join(
                [
                    "Active AI profiles:",
                    f"Ask: {app.settings.ollama_model}",
                    f"Super ask: {app.settings.ollama_super_model}",
                    f"Super cooldown: {app.settings.super_cooldown_seconds}s",
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

    @app.command("game")
    async def game_command(ctx: CommandContext, args: str) -> None:
        await games.handle(ctx, args)

    @app.command("join")
    async def join_command(ctx: CommandContext, args: str) -> None:
        await games.join(ctx, args)

    @app.command("skip")
    async def skip_command(ctx: CommandContext, args: str) -> None:
        await games.skip(ctx)

    @app.command("nominate")
    async def nominate_command(ctx: CommandContext, args: str) -> None:
        await games.nominate(ctx, args)

    @app.command("vote")
    async def vote_command(ctx: CommandContext, args: str) -> None:
        await games.vote(ctx, args)

    @app.command("kill")
    async def kill_command(ctx: CommandContext, args: str) -> None:
        await games.private_action_command(ctx, "kill", args)

    @app.command("protect")
    async def protect_command(ctx: CommandContext, args: str) -> None:
        await games.private_action_command(ctx, "protect", args)

    @app.command("investigate")
    async def investigate_command(ctx: CommandContext, args: str) -> None:
        await games.private_action_command(ctx, "investigate", args)

    @app.command("team")
    async def team_command(ctx: CommandContext, args: str) -> None:
        await games.team_chat(ctx, args)

    @app.command("filter")
    async def filter_command(ctx: CommandContext, args: str) -> None:
        if random.random() < COMMAND_DENIAL_CHANCE:
            await ctx.reply(random.choice(DENIAL_REPLIES))
            return

        raw = args.strip()
        if not raw:
            await ctx.reply(
                f"Use {prefix}filter <word> | <reply>, "
                f"or reply to text/sticker media with {prefix}filter <word>."
            )
            return

        if "|" not in raw:
            source = find_sticker_source(ctx.message.Message)
            if source:
                await ctx.typing(True)
                try:
                    media = await download_media(ctx.client, source)
                    created = await create_sticker(media, source, app.settings, raw)
                    filters.add_sticker(ctx.chat_id, raw, created.sticker_path)
                    await ctx.reply(f"Saved sticker filter: {raw.casefold()}")
                except Exception as exc:
                    await ctx.reply(f"I could not save that sticker filter: {exc}")
                finally:
                    await ctx.typing(False)
                return

        parsed = parse_filter_args(ctx, raw)
        if not parsed:
            await ctx.reply(
                f"Use {prefix}filter <word> | <reply>, "
                f"or reply to text/sticker media with {prefix}filter <word>."
            )
            return
        trigger, reply = parsed
        try:
            filters.add_text(ctx.chat_id, trigger, reply)
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
        if random.random() < COMMAND_DENIAL_CHANCE:
            await ctx.reply(random.choice(DENIAL_REPLIES))
            return

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

    async def answer_question(ctx: CommandContext, args: str, profile: str) -> bool:
        question = args.strip()
        command = "super" if profile == "super" else "ask"
        model = (
            app.settings.ollama_super_model
            if profile == "super"
            else app.settings.ollama_model
        )

        if not question:
            await ctx.reply(f"Send {prefix}{command} followed by your question.")
            return False

        if len(question) > app.settings.max_input_chars:
            await ctx.reply(
                f"That question is too long. Keep it under "
                f"{app.settings.max_input_chars} characters."
            )
            return False

        await ctx.typing(True)
        try:
            answer = await app.ai.ask(ctx.chat_id, question, profile=profile)
            await ctx.reply(answer)
            return True
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
            return False
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
