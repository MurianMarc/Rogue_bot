from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field
from typing import Any

from .app import CommandContext

LOG = logging.getLogger(__name__)

PLAYER_LIMIT = 9
NOMINEE_LIMIT = 3
DISCUSSION_SECONDS = 180
VOTE_SECONDS = 90

ROLE_MAFIA = "Mafia"
ROLE_MEDIC = "Medic"
ROLE_DETECTIVE = "Detective"
ROLE_JESTER = "Jester"
ROLE_TOWN = "Town"


@dataclass(slots=True)
class Player:
    user_id: str
    jid: Any
    nickname: str
    role: str = ROLE_TOWN
    alive: bool = True


@dataclass(slots=True)
class MafiaSession:
    group_id: str
    group_jid: Any
    host_id: str
    stage: str = "lobby"
    players: dict[str, Player] = field(default_factory=dict)
    nickname_index: dict[str, str] = field(default_factory=dict)
    pending_actions: dict[str, str] = field(default_factory=dict)
    actions: dict[str, str] = field(default_factory=dict)
    skips: set[str] = field(default_factory=set)
    nominations: dict[str, str] = field(default_factory=dict)
    vote_options: list[str] = field(default_factory=list)
    votes: dict[str, str] = field(default_factory=dict)
    poll_id: str | None = None
    timer_task: asyncio.Task[None] | None = None
    night_number: int = 1
    day_number: int = 1


class GameHub:
    def __init__(self) -> None:
        self._sessions: dict[str, MafiaSession] = {}
        self._private_routes: dict[str, str] = {}

    async def handle(self, ctx: CommandContext, args: str) -> None:
        parts = args.strip().split(maxsplit=1)
        action = parts[0].casefold() if parts else "help"
        rest = parts[1] if len(parts) > 1 else ""

        if action in {"start", "new"}:
            await self.start(ctx, rest)
            return
        if action in {"begin", "deal"}:
            await self.begin(ctx)
            return
        if action in {"stop", "quit", "end"}:
            await self.stop(ctx)
            return
        if action in {"status", "players"}:
            await self.status(ctx)
            return

        await ctx.reply(
            "\n".join(
                [
                    "Mafia commands:",
                    "!game start - open a group lobby",
                    "!join <nickname> - join the lobby",
                    "!game begin - start once 9 people joined",
                    "!skip - skip discussion once half the living players agree",
                    "!nominate <nickname> - nominate during voting setup",
                    "!vote <nickname> - text fallback if the poll misbehaves",
                    "!game status - show the current game",
                    "!game stop - stop the game if you hosted it",
                ]
            )
        )

    async def start(self, ctx: CommandContext, nickname: str = "") -> None:
        if not await self._require_group(ctx):
            return
        if ctx.chat_id in self._sessions:
            await ctx.reply("A Mafia game is already running here. Use !game status.")
            return

        session = MafiaSession(
            group_id=ctx.chat_id,
            group_jid=_clone_proto(ctx.chat_jid),
            host_id=ctx.sender_id,
        )
        self._sessions[ctx.chat_id] = session
        await ctx.reply(
            "\n".join(
                [
                    "Mafia lobby opened.",
                    "Need exactly 9 players: 1 Mafia, 1 Medic, 1 Detective, 1 Jester, 5 Town.",
                    "Join with !join <nickname>.",
                    "At 9 players I will deal roles in DMs. Keep your mouth shut unless your role says otherwise.",
                ]
            )
        )
        if nickname.strip():
            await self.join(ctx, nickname)

    async def begin(self, ctx: CommandContext) -> None:
        if not await self._require_group(ctx):
            return
        session = self._sessions.get(ctx.chat_id)
        if not session or session.stage != "lobby":
            await ctx.reply("There is no Mafia lobby waiting here.")
            return
        if len(session.players) != PLAYER_LIMIT:
            await ctx.reply(f"Need exactly {PLAYER_LIMIT} players. Current: {len(session.players)}.")
            return
        await self._start_game(session, ctx.client)

    async def stop(self, ctx: CommandContext) -> None:
        if not await self._require_group(ctx):
            return
        session = self._sessions.get(ctx.chat_id)
        if not session:
            await ctx.reply("No Mafia game is running here.")
            return
        if ctx.sender_id != session.host_id:
            await ctx.reply("Only the host can stop this Mafia game.")
            return
        await self._end_game(ctx.client, session, "The host ended the game.")

    async def status(self, ctx: CommandContext) -> None:
        if not await self._require_group(ctx):
            return
        session = self._sessions.get(ctx.chat_id)
        if not session:
            await ctx.reply("No Mafia game is running here. Use !game start.")
            return

        if session.stage == "lobby":
            players = ", ".join(player.nickname for player in session.players.values()) or "none"
            await ctx.reply(
                f"Mafia lobby: {len(session.players)}/{PLAYER_LIMIT}\nPlayers: {players}"
            )
            return

        alive = ", ".join(player.nickname for player in self._alive_players(session))
        dead = ", ".join(player.nickname for player in session.players.values() if not player.alive)
        lines = [f"Mafia stage: {session.stage}", f"Alive: {alive or 'none'}"]
        if dead:
            lines.append(f"Removed: {dead}")
        if session.stage == "voting" and session.vote_options:
            lines.append("Nominees: " + ", ".join(session.players[player_id].nickname for player_id in session.vote_options))
        await ctx.reply("\n".join(lines))

    async def join(self, ctx: CommandContext, nickname: str) -> None:
        if not await self._require_group(ctx):
            return
        session = self._sessions.get(ctx.chat_id)
        if not session or session.stage != "lobby":
            await ctx.reply("No open Mafia lobby here. Start one with !game start.")
            return

        nick = self._clean_nickname(nickname)
        if not nick:
            await ctx.reply("Use !join <nickname>. Pick one name. Make it recognizable.")
            return

        key = _nickname_key(nick)
        existing_owner = session.nickname_index.get(key)
        if existing_owner and existing_owner != ctx.sender_id:
            await ctx.reply("That nickname is already taken. Try originality for once.")
            return

        player = session.players.get(ctx.sender_id)
        if player:
            old_key = _nickname_key(player.nickname)
            session.nickname_index.pop(old_key, None)
            player.nickname = nick
            session.nickname_index[key] = ctx.sender_id
            await ctx.reply(f"Updated nickname to {nick}.")
            return

        if len(session.players) >= PLAYER_LIMIT:
            await ctx.reply("The lobby is full. 9 means 9.")
            return

        session.players[ctx.sender_id] = Player(
            user_id=ctx.sender_id,
            jid=_clone_proto(ctx.sender_jid),
            nickname=nick,
        )
        session.nickname_index[key] = ctx.sender_id
        count = len(session.players)
        await ctx.reply(f"{nick} joined. {count}/{PLAYER_LIMIT}.")

        if count == PLAYER_LIMIT:
            await self._start_game(session, ctx.client)

    async def skip(self, ctx: CommandContext) -> None:
        if not await self._require_group(ctx):
            return
        session = self._sessions.get(ctx.chat_id)
        if not session or session.stage != "discussion":
            await ctx.reply("There is no discussion timer to skip right now.")
            return
        player = await self._require_alive_player(ctx, session)
        if not player:
            return

        session.skips.add(player.user_id)
        needed = max(1, (len(self._alive_players(session)) + 1) // 2)
        if len(session.skips) >= needed:
            self._cancel_timer(session)
            await ctx.reply("Half the table skipped. Good. Nomination time.")
            await self._start_nominations(session, ctx.client)
            return
        await ctx.reply(f"Skip counted: {len(session.skips)}/{needed}.")

    async def nominate(self, ctx: CommandContext, nickname: str) -> None:
        if not await self._require_group(ctx):
            return
        session = self._sessions.get(ctx.chat_id)
        if not session or session.stage != "nominating":
            await ctx.reply("Nominations are not open right now.")
            return
        player = await self._require_alive_player(ctx, session)
        if not player:
            return
        target = self._find_living_player(session, nickname)
        if not target:
            await ctx.reply("Nominee not found. Use a living player's nickname.")
            return

        session.nominations[player.user_id] = target.user_id
        nominee_ids = self._unique_nominees(session)
        if len(nominee_ids) >= NOMINEE_LIMIT:
            await self._start_vote(session, ctx.client, nominee_ids[:NOMINEE_LIMIT])
            return
        await ctx.reply(
            f"Nominee added: {target.nickname}. "
            f"{len(nominee_ids)}/{NOMINEE_LIMIT} nominees ready."
        )

    async def vote(self, ctx: CommandContext, nickname: str) -> None:
        if not await self._require_group(ctx):
            return
        session = self._sessions.get(ctx.chat_id)
        if not session or session.stage != "voting":
            await ctx.reply("Voting is not open right now.")
            return
        player = await self._require_alive_player(ctx, session)
        if not player:
            return
        target = self._find_vote_option(session, nickname)
        if not target:
            await ctx.reply("That is not one of the three nominees.")
            return

        session.votes[player.user_id] = target.user_id
        await ctx.reply(f"Vote locked for {target.nickname}.")
        if self._all_living_voted(session):
            await self._finish_vote(session, ctx.client)

    async def handle_private_text(self, ctx: CommandContext, text: str) -> bool:
        if ctx.is_group:
            return False

        player_id = ctx.chat_id
        if player_id not in self._private_routes:
            player_id = ctx.sender_id
        group_id = self._private_routes.get(player_id)
        if not group_id:
            return False

        session = self._sessions.get(group_id)
        if not session or session.stage != "night" or player_id not in session.pending_actions:
            self._private_routes.pop(player_id, None)
            return False

        player = session.players[player_id]
        action = session.pending_actions[player_id]
        target = self._find_living_player(session, text)
        if not target:
            await ctx.client.send_message(
                player.jid,
                "That nickname is not alive in this game.\n" + self._target_list(session),
                link_preview=False,
            )
            return True

        if action in {"kill", "investigate"} and target.user_id == player.user_id:
            await ctx.client.send_message(player.jid, "Pick someone else. Not yourself.", link_preview=False)
            return True

        session.actions[action] = target.user_id
        session.pending_actions.pop(player_id, None)
        self._private_routes.pop(player_id, None)
        await ctx.client.send_message(player.jid, f"Locked in: {target.nickname}.", link_preview=False)

        if not session.pending_actions:
            await self._resolve_night(session, ctx.client)
        return True

    async def handle_raw(self, ctx: CommandContext) -> bool:
        if not ctx.is_group:
            return False

        poll_update = ctx.message.Message.pollUpdateMessage
        if not poll_update.ByteSize():
            return False

        session = self._sessions.get(ctx.chat_id)
        if not session or session.stage != "voting" or not session.poll_id:
            return False
        if poll_update.pollCreationMessageKey.ID != session.poll_id:
            return False

        player = session.players.get(ctx.sender_id)
        if not player or not player.alive:
            return True

        try:
            vote_message = await ctx.client.decrypt_poll_vote(ctx.message.Message)
        except Exception as exc:
            LOG.warning("Could not decrypt Mafia poll vote: %s", exc)
            return True

        selected = self._selected_poll_option(vote_message.selectedOptions)
        if not selected:
            session.votes.pop(player.user_id, None)
            return True

        target = self._find_vote_option(session, selected)
        if target:
            session.votes[player.user_id] = target.user_id
            if self._all_living_voted(session):
                await self._finish_vote(session, ctx.client)
        return True

    async def _start_game(self, session: MafiaSession, client: Any) -> None:
        self._cancel_timer(session)
        session.stage = "night"
        session.night_number = 1
        session.day_number = 1
        session.actions.clear()
        session.pending_actions.clear()
        session.skips.clear()
        session.nominations.clear()
        session.votes.clear()
        session.vote_options.clear()
        session.poll_id = None

        player_ids = list(session.players)
        random.shuffle(player_ids)
        role_plan = [ROLE_MAFIA, ROLE_MEDIC, ROLE_DETECTIVE, ROLE_JESTER]
        for player_id, role in zip(player_ids, role_plan, strict=False):
            session.players[player_id].role = role
        for player_id in player_ids[len(role_plan):]:
            session.players[player_id].role = ROLE_TOWN

        for player in session.players.values():
            await self._send_role_dm(client, session, player)

        await client.send_message(
            session.group_jid,
            "Roles are out in DMs. Night 1 has started. Mafia, Medic, and Detective must answer their DMs with nicknames.",
            link_preview=False,
        )
        await self._start_night(session, client, announce=False)

    async def _start_night(self, session: MafiaSession, client: Any, announce: bool = True) -> None:
        session.stage = "night"
        session.actions.clear()
        session.pending_actions.clear()
        session.skips.clear()
        session.nominations.clear()
        session.votes.clear()
        session.vote_options.clear()
        session.poll_id = None
        self._cancel_timer(session)

        if announce:
            await client.send_message(
                session.group_jid,
                f"Night {session.night_number} begins. Special roles, check your DMs.",
                link_preview=False,
            )

        for action, role in (("kill", ROLE_MAFIA), ("protect", ROLE_MEDIC), ("investigate", ROLE_DETECTIVE)):
            player = self._living_role(session, role)
            if player:
                session.pending_actions[player.user_id] = action
                self._private_routes[player.user_id] = session.group_id
                await self._send_action_prompt(client, session, player, action)

        if not session.pending_actions:
            await self._resolve_night(session, client)

    async def _resolve_night(self, session: MafiaSession, client: Any) -> None:
        for player_id in list(session.pending_actions):
            self._private_routes.pop(player_id, None)
        session.pending_actions.clear()

        detective = self._living_role(session, ROLE_DETECTIVE)
        investigated_id = session.actions.get("investigate")
        if detective and investigated_id in session.players:
            target = session.players[investigated_id]
            result = "Mafia" if target.role == ROLE_MAFIA else "not Mafia"
            await client.send_message(
                detective.jid,
                f"Investigation result: {target.nickname} is {result}. Use your brain with this.",
                link_preview=False,
            )

        killed: Player | None = None
        kill_id = session.actions.get("kill")
        protect_id = session.actions.get("protect")
        if kill_id and kill_id != protect_id and kill_id in session.players:
            target = session.players[kill_id]
            if target.alive:
                target.alive = False
                killed = target

        story = self._night_story(session, killed, bool(kill_id and kill_id == protect_id))
        winner = self._winner(session)
        if winner:
            await client.send_message(session.group_jid, story, link_preview=False)
            await self._announce_winner(client, session, winner)
            return

        session.stage = "discussion"
        session.skips.clear()
        await client.send_message(
            session.group_jid,
            "\n".join(
                [
                    story,
                    "",
                    f"Discussion is open for {DISCUSSION_SECONDS}s.",
                    "Use !skip if you are done talking. Half of the living players can force nominations.",
                ]
            ),
            link_preview=False,
        )
        session.timer_task = asyncio.create_task(self._discussion_timeout(session, client))

    async def _start_nominations(self, session: MafiaSession, client: Any) -> None:
        if session.group_id not in self._sessions or session.stage not in {"discussion", "nominating"}:
            return
        self._cancel_timer(session)
        session.stage = "nominating"
        session.skips.clear()
        session.nominations.clear()
        await client.send_message(
            session.group_jid,
            "\n".join(
                [
                    "Nomination time.",
                    "Pick exactly 3 suspects with !nominate <nickname>.",
                    "Living players: " + ", ".join(player.nickname for player in self._alive_players(session)),
                ]
            ),
            link_preview=False,
        )

    async def _start_vote(self, session: MafiaSession, client: Any, nominee_ids: list[str]) -> None:
        self._cancel_timer(session)
        session.stage = "voting"
        session.vote_options = nominee_ids
        session.votes.clear()
        options = [session.players[player_id].nickname for player_id in nominee_ids]
        poll_created = False

        try:
            poll = await client.build_poll_vote_creation(
                "Mafia vote: who leaves?",
                options,
                1,
            )
            response = await client.send_message(session.group_jid, poll)
            session.poll_id = response.ID
            poll_created = True
        except Exception as exc:
            LOG.warning("Could not create Mafia poll: %s", exc)

        await client.send_message(
            session.group_jid,
            "\n".join(
                [
                    "Vote now.",
                    "Nominees: " + ", ".join(options),
                    "Use the poll if it appears. If WhatsApp acts possessed, use !vote <nickname>.",
                    f"Voting closes in {VOTE_SECONDS}s.",
                ]
            ),
            link_preview=False,
        )
        if not poll_created:
            await client.send_message(session.group_jid, "Poll failed, so text votes only.", link_preview=False)
        session.timer_task = asyncio.create_task(self._vote_timeout(session, client))

    async def _finish_vote(self, session: MafiaSession, client: Any) -> None:
        if session.group_id not in self._sessions or session.stage != "voting":
            return
        self._cancel_timer(session)

        counts = {player_id: 0 for player_id in session.vote_options}
        for voter_id, target_id in session.votes.items():
            voter = session.players.get(voter_id)
            if voter and voter.alive and target_id in counts:
                counts[target_id] += 1

        if not counts or max(counts.values()) == 0:
            await client.send_message(
                session.group_jid,
                "Vote ended with zero valid votes. Embarrassing. Nobody leaves.",
                link_preview=False,
            )
            session.night_number += 1
            await self._start_night(session, client)
            return

        top_votes = max(counts.values())
        top = [player_id for player_id, count in counts.items() if count == top_votes]
        if len(top) > 1:
            names = ", ".join(session.players[player_id].nickname for player_id in top)
            await client.send_message(
                session.group_jid,
                f"Vote tied between {names}. Nobody leaves. You had one job.",
                link_preview=False,
            )
            session.night_number += 1
            await self._start_night(session, client)
            return

        eliminated = session.players[top[0]]
        eliminated.alive = False
        await client.send_message(
            session.group_jid,
            f"{eliminated.nickname} was voted out with {top_votes} vote(s). Role: {eliminated.role}.",
            link_preview=False,
        )

        if eliminated.role == ROLE_JESTER:
            await self._end_game(
                client,
                session,
                f"{eliminated.nickname} was the Jester and got voted out. Jester wins. Annoying, but legal.",
            )
            return

        winner = self._winner(session)
        if winner:
            await self._announce_winner(client, session, winner)
            return

        session.night_number += 1
        await self._start_night(session, client)

    async def _discussion_timeout(self, session: MafiaSession, client: Any) -> None:
        await asyncio.sleep(DISCUSSION_SECONDS)
        if self._sessions.get(session.group_id) is session and session.stage == "discussion":
            await self._start_nominations(session, client)

    async def _vote_timeout(self, session: MafiaSession, client: Any) -> None:
        await asyncio.sleep(VOTE_SECONDS)
        if self._sessions.get(session.group_id) is session and session.stage == "voting":
            await self._finish_vote(session, client)

    async def _send_role_dm(self, client: Any, session: MafiaSession, player: Player) -> None:
        descriptions = {
            ROLE_MAFIA: "You choose who gets removed at night. Reply when I ask.",
            ROLE_MEDIC: "You protect one living player each night.",
            ROLE_DETECTIVE: "You investigate one player each night.",
            ROLE_JESTER: "You win if the group votes you out. Be suspicious, but do not be obvious.",
            ROLE_TOWN: "Find the Mafia by discussion and voting.",
        }
        await client.send_message(
            player.jid,
            "\n".join(
                [
                    f"Your Mafia role: {player.role}.",
                    descriptions[player.role],
                    f"Group roster: {self._target_list(session)}",
                ]
            ),
            link_preview=False,
        )

    async def _send_action_prompt(self, client: Any, session: MafiaSession, player: Player, action: str) -> None:
        verb = {
            "kill": "kill",
            "protect": "protect",
            "investigate": "investigate",
        }[action]
        await client.send_message(
            player.jid,
            "\n".join(
                [
                    f"Night {session.night_number}: who do you want to {verb}?",
                    "Reply in this DM with only the nickname.",
                    self._target_list(session),
                ]
            ),
            link_preview=False,
        )

    async def _announce_winner(self, client: Any, session: MafiaSession, winner: str) -> None:
        if winner == "town":
            message = "The Mafia is gone. Town wins."
        else:
            message = "Only one non-Mafia player remains with the Mafia. Mafia wins."
        await self._end_game(client, session, message)

    async def _end_game(self, client: Any, session: MafiaSession, message: str) -> None:
        self._cancel_timer(session)
        for player_id in list(session.pending_actions):
            self._private_routes.pop(player_id, None)
        self._sessions.pop(session.group_id, None)
        reveal = "\n".join(
            f"- {player.nickname}: {player.role}" for player in session.players.values()
        )
        await client.send_message(
            session.group_jid,
            f"{message}\n\nRole reveal:\n{reveal}",
            link_preview=False,
        )

    async def _require_group(self, ctx: CommandContext) -> bool:
        if ctx.is_group:
            return True
        await ctx.reply("Mafia commands only work in groups.")
        return False

    async def _require_alive_player(self, ctx: CommandContext, session: MafiaSession) -> Player | None:
        player = session.players.get(ctx.sender_id)
        if not player:
            await ctx.reply("You are not in this Mafia game.")
            return None
        if not player.alive:
            await ctx.reply("You are already out. Haunt silently.")
            return None
        return player

    def _night_story(self, session: MafiaSession, killed: Player | None, blocked: bool) -> str:
        opening = random.choice(
            [
                "Night report: the group chat went quiet, which was already suspicious.",
                "Night report: everyone claimed innocence. Naturally, someone was lying.",
                "Night report: the lights went out and the confidence left the room.",
            ]
        )
        if killed:
            result = f"By morning, {killed.nickname} was gone. Role: {killed.role}."
        elif blocked:
            result = "Someone was targeted, but the Medic handled it. No death tonight."
        else:
            result = "No one died. Either the Mafia blinked or the night was weirdly disciplined."
        return f"{opening}\n{result}"

    def _winner(self, session: MafiaSession) -> str | None:
        alive = self._alive_players(session)
        mafia_alive = [player for player in alive if player.role == ROLE_MAFIA]
        non_mafia_alive = [player for player in alive if player.role != ROLE_MAFIA]
        if not mafia_alive:
            return "town"
        if len(non_mafia_alive) <= 1:
            return "mafia"
        return None

    def _alive_players(self, session: MafiaSession) -> list[Player]:
        return [player for player in session.players.values() if player.alive]

    def _living_role(self, session: MafiaSession, role: str) -> Player | None:
        for player in session.players.values():
            if player.alive and player.role == role:
                return player
        return None

    def _find_living_player(self, session: MafiaSession, nickname: str) -> Player | None:
        player_id = session.nickname_index.get(_nickname_key(nickname))
        if not player_id:
            return None
        player = session.players[player_id]
        return player if player.alive else None

    def _find_vote_option(self, session: MafiaSession, nickname: str) -> Player | None:
        player = self._find_living_player(session, nickname)
        if player and player.user_id in session.vote_options:
            return player
        return None

    def _unique_nominees(self, session: MafiaSession) -> list[str]:
        seen: set[str] = set()
        nominees: list[str] = []
        for player_id in session.nominations.values():
            if player_id not in seen:
                nominees.append(player_id)
                seen.add(player_id)
        return nominees

    def _all_living_voted(self, session: MafiaSession) -> bool:
        alive_ids = {player.user_id for player in self._alive_players(session)}
        return bool(alive_ids) and alive_ids.issubset(session.votes)

    def _target_list(self, session: MafiaSession) -> str:
        return "Living players: " + ", ".join(player.nickname for player in self._alive_players(session))

    def _clean_nickname(self, nickname: str) -> str:
        nick = " ".join(nickname.strip().split())
        if not nick or nick.startswith("!") or len(nick) > 24 or "\n" in nick:
            return ""
        return nick

    def _selected_poll_option(self, selected_options: Any) -> str:
        if not selected_options:
            return ""
        option = selected_options[0]
        if isinstance(option, bytes):
            return option.decode("utf-8", "ignore").strip()
        return str(option).strip()

    def _cancel_timer(self, session: MafiaSession) -> None:
        if session.timer_task and not session.timer_task.done():
            session.timer_task.cancel()
        session.timer_task = None


def _nickname_key(nickname: str) -> str:
    return " ".join(nickname.casefold().strip().split())


def _clone_proto(value: Any) -> Any:
    clone = value.__class__()
    clone.MergeFrom(value)
    return clone
