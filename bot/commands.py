from __future__ import annotations

from .app import CommandContext, RogueBot
from .media import download_media, find_sticker_source


def register_commands(app: RogueBot) -> None:
    prefix = app.settings.cmd_prefix

    @app.command("help")
    async def help_command(ctx: CommandContext, args: str) -> None:
        await ctx.reply(
            "\n".join(
                [
                    f"{app.settings.bot_name} commands:",
                    f"{prefix}ask <question> - use the smart GPU model",
                    f"{prefix}fast <question> - use the lighter CPU model",
                    f"{prefix}models - show active AI models",
                    f"{prefix}sticker [name] - make a sticker from media or replied media",
                    f"{prefix}reset - clear this chat's short AI memory",
                    f"{prefix}id - show this chat ID for ALLOWED_CHATS",
                    f"{prefix}ping - check if the bot is alive",
                    f"{prefix}help - show this menu",
                ]
            )
        )

    @app.command("ping")
    async def ping_command(ctx: CommandContext, args: str) -> None:
        await ctx.reply("pong")

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
            await ctx.client.send_sticker(
                ctx.chat_jid,
                media,
                quoted=ctx.message,
                name=args.strip() or app.settings.sticker_author,
                packname=app.settings.sticker_pack_name,
                crop=app.settings.sticker_crop,
                enforce_not_broken=True,
                animated_gif=True,
            )
        except Exception as exc:
            await ctx.reply(f"I could not make that sticker: {exc}")
        finally:
            await ctx.typing(False)

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
