from __future__ import annotations

import random
from dataclasses import dataclass

from .app import CommandContext


@dataclass(slots=True)
class GuessGame:
    answer: int
    attempts: int = 0
    max_attempts: int = 6


class GameHub:
    def __init__(self) -> None:
        self._guess_games: dict[str, GuessGame] = {}

    async def handle(self, ctx: CommandContext, args: str) -> None:
        parts = args.strip().split()
        action = parts[0].casefold() if parts else "help"

        if action in {"start", "new"}:
            self._guess_games[ctx.chat_id] = GuessGame(answer=random.randint(1, 20))
            await ctx.reply(
                "Rogue Trial started. Guess a number from 1 to 20. "
                "You get 6 shots before I judge everyone."
            )
            return

        if action in {"stop", "quit", "end"}:
            game = self._guess_games.pop(ctx.chat_id, None)
            if not game:
                await ctx.reply("There is no game running. Dramatic, but false.")
                return
            await ctx.reply(f"Game ended. The answer was {game.answer}.")
            return

        if action in {"guess", "g"}:
            await self._guess(ctx, parts[1:] if len(parts) > 1 else [])
            return

        await ctx.reply(
            "\n".join(
                [
                    "Game commands:",
                    "!game start - start Rogue Trial",
                    "!game guess <1-20> - make a guess",
                    "!game stop - end the current game",
                ]
            )
        )

    async def _guess(self, ctx: CommandContext, args: list[str]) -> None:
        game = self._guess_games.get(ctx.chat_id)
        if not game:
            await ctx.reply("No game is running. Use !game start first. Simple.")
            return

        if not args or not args[0].isdigit():
            await ctx.reply("Give me a number. Not a prophecy.")
            return

        guess = int(args[0])
        if guess < 1 or guess > 20:
            await ctx.reply("Between 1 and 20. I even made the range tiny.")
            return

        game.attempts += 1
        if guess == game.answer:
            self._guess_games.pop(ctx.chat_id, None)
            await ctx.reply(f"Correct. {guess}. Took {game.attempts} attempt(s). Fine, impressive.")
            return

        if game.attempts >= game.max_attempts:
            self._guess_games.pop(ctx.chat_id, None)
            await ctx.reply(f"Nope. Out of attempts. The answer was {game.answer}.")
            return

        hint = "higher" if guess < game.answer else "lower"
        left = game.max_attempts - game.attempts
        await ctx.reply(f"No. Go {hint}. {left} attempt(s) left.")
