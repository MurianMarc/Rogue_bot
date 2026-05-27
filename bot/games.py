from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field
from typing import Any

from .app import CommandContext, string_to_jid

LOG = logging.getLogger(__name__)

MIN_PLAYERS = 9
DEFAULT_PLAYER_TARGET = 9
MAX_PLAYERS = 50
NOMINEE_LIMIT = 3
DISCUSSION_SECONDS = 180
VOTE_SECONDS = 90
STORY_TIMEOUT_SECONDS = 25

ROLE_MAFIA = "Mafia"
ROLE_MEDIC = "Medic"
ROLE_DETECTIVE = "Detective"
ROLE_JESTER = "Jester"
ROLE_TOWN = "Town"
TEAM_CHAT_ROLES = {ROLE_MAFIA, ROLE_MEDIC}
ACTION_ROLES = {
    "kill": ROLE_MAFIA,
    "protect": ROLE_MEDIC,
    "investigate": ROLE_DETECTIVE,
}
ACTION_ORDER = ["kill", "protect", "investigate"]


@dataclass(slots=True)
class Player:
    user_id: str
    jid: Any
    nickname: str
    aliases: set[str] = field(default_factory=set)
    role: str = ROLE_TOWN
    alive: bool = True


@dataclass(slots=True)
class MafiaSession:
    group_id: str
    group_jid: Any
    host_id: str
    target_size: int = DEFAULT_PLAYER_TARGET
    stage: str = "lobby"
    players: dict[str, Player] = field(default_factory=dict)
    nickname_index: dict[str, str] = field(default_factory=dict)
    pending_actions: dict[str, str] = field(default_factory=dict)
    actions: dict[str, str] = field(default_factory=dict)
    action_queue: list[str] = field(default_factory=list)
    current_action: str | None = None
    skips: set[str] = field(default_factory=set)
    nominations: dict[str, str] = field(default_factory=dict)
    vote_options: list[str] = field(default_factory=list)
    votes: dict[str, str] = field(default_factory=dict)
    poll_id: str | None = None
    timer_task: asyncio.Task[None] | None = None
    night_number: int = 1
    day_number: int = 1


class GameHub:
    def __init__(self, app: Any | None = None) -> None:
        self.app = app
        self._sessions: dict[str, MafiaSession] = {}
        self._private_routes: dict[str, str] = {}

    async def handle(self, ctx: CommandContext, args: str) -> None:
        parts = args.strip().split(maxsplit=1)
        action = parts[0].casefold() if parts else "help"
        rest = parts[1] if len(parts) > 1 else ""

        if action in {"start", "new"}:
            await self.start(ctx, rest)
            return
        if action in {"size", "target"}:
            await self.set_size(ctx, rest)
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
                    "!game start [players] - open a group lobby, 9 minimum",
                    "!game size <players> - change the lobby target before starting",
                    "!join <nickname> - join the lobby",
                    "!game begin - host starts once the target is reached",
                    "!skip - skip discussion once half the living players agree",
                    "!nominate <nickname> - nominate during voting setup",
                    "!vote <nickname> - text fallback if the poll misbehaves",
                    "!team <message> - private Mafia or Medic team relay in bot DM",
                    "!game status - show the current game",
                    "!game stop - stop the game if you hosted it",
                ]
            )
        )

    async def start(self, ctx: CommandContext, args: str = "") -> None:
        if not await self._require_group(ctx):
            return
        if ctx.chat_id in self._sessions:
            await ctx.reply("A Mafia game is already running here. Use !game status.")
            return

        target_size, nickname = self._parse_lobby_args(args)
        if target_size < MIN_PLAYERS:
            await ctx.reply(f"Mafia needs at least {MIN_PLAYERS} players.")
            return
        if target_size > MAX_PLAYERS:
            await ctx.reply(f"Keep the lobby at {MAX_PLAYERS} players or less.")
            return

        session = MafiaSession(
            group_id=ctx.chat_id,
            group_jid=_clone_proto(ctx.chat_jid),
            host_id=ctx.sender_id,
            target_size=target_size,
        )
        self._sessions[ctx.chat_id] = session
        await ctx.reply(
            "\n".join(
                [
                    "Mafia lobby opened.",
                    f"Target: {target_size} players. Minimum: {MIN_PLAYERS}.",
                    "Roles scale with the lobby: Mafia and Medics can have teams, Detective stays alone.",
                    "Join with !join <nickname>.",
                    "Only the host can begin the game once the target is reached.",
                ]
            )
        )
        prelude = await self._story_text(
            session,
            "prelude",
            (
                f"A Mafia lobby has opened for {target_size} players. "
                "Write a tense opening prelude before roles are dealt."
            ),
            self._fallback_prelude(session),
        )
        await ctx.client.send_message(session.group_jid, prelude, link_preview=False)
        if nickname:
            await self.join(ctx, nickname)

    async def set_size(self, ctx: CommandContext, args: str) -> None:
        if not await self._require_group(ctx):
            return
        session = self._sessions.get(ctx.chat_id)
        if not session or session.stage != "lobby":
            await ctx.reply("There is no Mafia lobby waiting here.")
            return
        if ctx.sender_id != session.host_id:
            await ctx.reply("Only the host can change the lobby size.")
            return

        try:
            target_size = int(args.strip().split()[0])
        except (IndexError, ValueError):
            await ctx.reply(f"Use !game size <players>. Minimum {MIN_PLAYERS}.")
            return
        if target_size < MIN_PLAYERS:
            await ctx.reply(f"Mafia needs at least {MIN_PLAYERS} players.")
            return
        if target_size > MAX_PLAYERS:
            await ctx.reply(f"Keep the lobby at {MAX_PLAYERS} players or less.")
            return
        if target_size < len(session.players):
            await ctx.reply(f"{len(session.players)} players already joined. The target cannot go below that.")
            return
        session.target_size = target_size
        await ctx.reply(f"Lobby target set to {target_size} players.")

    async def begin(self, ctx: CommandContext) -> None:
        if not await self._require_group(ctx):
            return
        session = self._sessions.get(ctx.chat_id)
        if not session or session.stage != "lobby":
            await ctx.reply("There is no Mafia lobby waiting here.")
            return
        if ctx.sender_id != session.host_id:
            await ctx.reply("Only the host can begin this Mafia game.")
            return
        if len(session.players) < MIN_PLAYERS:
            await ctx.reply(f"Need at least {MIN_PLAYERS} players. Current: {len(session.players)}.")
            return
        if len(session.players) < session.target_size:
            await ctx.reply(f"Need {session.target_size} players. Current: {len(session.players)}.")
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
                f"Mafia lobby: {len(session.players)}/{session.target_size}\nPlayers: {players}"
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
            player.aliases.update(self._ctx_aliases(ctx))
            session.nickname_index[key] = ctx.sender_id
            await ctx.reply(f"Updated nickname to {nick}.")
            return

        if len(session.players) >= session.target_size:
            await ctx.reply("The lobby has reached its target. The host can use !game begin.")
            return

        aliases = self._ctx_aliases(ctx)
        session.players[ctx.sender_id] = Player(
            user_id=ctx.sender_id,
            jid=string_to_jid(ctx.sender_id),
            nickname=nick,
            aliases=aliases,
        )
        session.nickname_index[key] = ctx.sender_id
        count = len(session.players)
        if count >= session.target_size:
            await ctx.reply(f"{nick} joined. {count}/{session.target_size}. Target reached. Host, use !game begin.")
            return
        await ctx.reply(f"{nick} joined. {count}/{session.target_size}.")

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

        session, player = self._private_player(ctx)
        if not session or not player:
            return False

        team_message = self._parse_team_message(ctx, text)
        if team_message is not None:
            await self._relay_team_message(ctx.client, session, player, team_message)
            return True

        if session.stage != "night" or player.user_id not in session.pending_actions:
            if session.stage == "night" and player.alive and player.role in ACTION_ROLES.values():
                current_role = ACTION_ROLES.get(session.current_action or "", "")
                if current_role and current_role != player.role:
                    await ctx.client.send_message(
                        player.jid,
                        f"Wait. The current night phase is {current_role}. I will ask you when it is your turn.",
                        link_preview=False,
                    )
                    return True
            return False

        action = session.pending_actions[player.user_id]
        target_text = self._private_action_target(ctx, text, action)
        target = self._find_living_player(session, target_text)
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
        if action == "kill" and target.role == ROLE_MAFIA:
            await ctx.client.send_message(player.jid, "Mafia cannot target Mafia. Pick someone else.", link_preview=False)
            return True

        session.actions[action] = target.user_id
        self._clear_pending_routes(session)
        await ctx.client.send_message(player.jid, f"Locked in: {target.nickname}.", link_preview=False)
        await self._broadcast_role(
            ctx.client,
            session,
            player.role,
            f"{player.nickname} locked the {action} choice.",
            exclude={player.user_id},
        )

        await self._advance_night(session, ctx.client)
        return True

    async def private_action_command(self, ctx: CommandContext, action: str, args: str) -> None:
        if ctx.is_group:
            await ctx.reply("Night actions happen in the bot DM.")
            return
        text = f"{action} {args.strip()}".strip()
        if not await self.handle_private_text(ctx, text):
            await ctx.reply("No pending Mafia action for you right now.")

    async def team_chat(self, ctx: CommandContext, args: str) -> None:
        if ctx.is_group:
            await ctx.reply("Use !team in the bot DM, not the group.")
            return
        session, player = self._private_player(ctx)
        if not session or not player:
            await ctx.reply("You are not connected to an active Mafia team chat.")
            return
        await self._relay_team_message(ctx.client, session, player, args.strip())

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
        session.action_queue.clear()
        session.current_action = None
        session.skips.clear()
        session.nominations.clear()
        session.votes.clear()
        session.vote_options.clear()
        session.poll_id = None

        player_ids = list(session.players)
        random.shuffle(player_ids)
        role_plan = self._role_plan(len(player_ids))
        for player_id, role in zip(player_ids, role_plan, strict=False):
            session.players[player_id].role = role
        for player_id in player_ids[len(role_plan):]:
            session.players[player_id].role = ROLE_TOWN

        for player in session.players.values():
            await self._send_role_dm(client, session, player)

        await client.send_message(
            session.group_jid,
            "Roles are out in DMs. Night 1 is about to begin. Actions happen in order: Mafia, Medic, Detective.",
            link_preview=False,
        )
        await self._start_night(session, client)

    async def _start_night(self, session: MafiaSession, client: Any, announce: bool = True) -> None:
        session.stage = "night"
        session.actions.clear()
        session.pending_actions.clear()
        session.action_queue = ACTION_ORDER.copy()
        session.current_action = None
        session.skips.clear()
        session.nominations.clear()
        session.votes.clear()
        session.vote_options.clear()
        session.poll_id = None
        self._clear_pending_routes(session)
        self._cancel_timer(session)

        if announce:
            story = await self._story_text(
                session,
                "night-opening",
                (
                    f"Night {session.night_number} begins in a Mafia game with "
                    f"{len(self._alive_players(session))} living players. "
                    "Write a suspenseful night opening before any action happens."
                ),
                self._fallback_night_opening(session),
            )
            await client.send_message(
                session.group_jid,
                "\n\n".join([story, "Special roles will be called one at a time: Mafia, Medic, Detective."]),
                link_preview=False,
            )

        await self._advance_night(session, client)

    async def _advance_night(self, session: MafiaSession, client: Any) -> None:
        self._clear_pending_routes(session)
        session.pending_actions.clear()
        session.current_action = None

        while session.action_queue:
            action = session.action_queue.pop(0)
            role = ACTION_ROLES[action]
            actors = self._living_players_by_role(session, role)
            if not actors:
                continue

            session.current_action = action
            for player in actors:
                session.pending_actions[player.user_id] = action
                self._register_private_routes(session, player)
                await self._send_action_prompt(client, session, player, action)

            names = ", ".join(player.nickname for player in actors)
            LOG.info("Mafia night waiting for %s action from %s", action, names)
            return

        await self._resolve_night(session, client)

    async def _resolve_night(self, session: MafiaSession, client: Any) -> None:
        self._clear_pending_routes(session)
        session.pending_actions.clear()
        session.current_action = None

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

        story = await self._night_story(session, killed, bool(kill_id and kill_id == protect_id))
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
            ROLE_MAFIA: "Your team chooses who gets removed at night. Use !team <message> here to coordinate.",
            ROLE_MEDIC: "Your team protects one living player each night. Use !team <message> here to coordinate.",
            ROLE_DETECTIVE: "You investigate one player each night.",
            ROLE_JESTER: "You win if the group votes you out. Be suspicious, but do not be obvious.",
            ROLE_TOWN: "Find the Mafia by discussion and voting.",
        }
        teammates = self._living_players_by_role(session, player.role)
        teammate_names = ", ".join(member.nickname for member in teammates if member.user_id != player.user_id)
        team_line = ""
        if player.role in TEAM_CHAT_ROLES:
            team_line = f"Team channel: !team <message>. Teammates: {teammate_names or 'none yet'}"
        await client.send_message(
            player.jid,
            "\n".join(
                [line for line in [
                    f"Your Mafia role: {player.role}.",
                    descriptions[player.role],
                    team_line,
                    f"Group roster: {self._target_list(session)}",
                ] if line]
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
                [line for line in [
                    f"Night {session.night_number}: who do you want to {verb}?",
                    "Reply in this DM with the nickname, or use the command form.",
                    f"Command form: !{verb} <nickname>",
                    "First valid reply from this role locks the action.",
                    "Use !team <message> to coordinate privately." if player.role in TEAM_CHAT_ROLES else "",
                    self._target_list(session),
                ] if line]
            ),
            link_preview=False,
        )

    async def _announce_winner(self, client: Any, session: MafiaSession, winner: str) -> None:
        if winner == "town":
            message = "The Mafia is gone. Town wins."
        else:
            message = "The Mafia has reached parity with everyone else. Mafia wins."
        await self._end_game(client, session, message)

    async def _end_game(self, client: Any, session: MafiaSession, message: str) -> None:
        self._cancel_timer(session)
        self._clear_pending_routes(session)
        for player in session.players.values():
            for alias in player.aliases | {player.user_id}:
                self._private_routes.pop(alias, None)
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

    async def _relay_team_message(
        self,
        client: Any,
        session: MafiaSession,
        player: Player,
        message: str,
    ) -> None:
        if player.role not in TEAM_CHAT_ROLES or not player.alive:
            await client.send_message(player.jid, "You do not have a private team channel.", link_preview=False)
            return
        if not message:
            await client.send_message(player.jid, "Use !team <message>.", link_preview=False)
            return

        teammates = [
            member
            for member in self._living_players_by_role(session, player.role)
            if member.user_id != player.user_id
        ]
        if not teammates:
            await client.send_message(player.jid, "No living teammates to relay this to.", link_preview=False)
            return

        relay = f"[{player.role} channel] {player.nickname}: {message}"
        for teammate in teammates:
            await client.send_message(teammate.jid, relay, link_preview=False)
        await client.send_message(player.jid, f"Team message sent to {player.role}.", link_preview=False)

    async def _broadcast_role(
        self,
        client: Any,
        session: MafiaSession,
        role: str,
        message: str,
        exclude: set[str] | None = None,
    ) -> None:
        excluded = exclude or set()
        for player in self._living_players_by_role(session, role):
            if player.user_id not in excluded:
                await client.send_message(player.jid, message, link_preview=False)

    def _private_player(self, ctx: CommandContext) -> tuple[MafiaSession | None, Player | None]:
        aliases = self._ctx_aliases(ctx)
        group_id = next((self._private_routes[alias] for alias in aliases if alias in self._private_routes), "")
        if group_id:
            session = self._sessions.get(group_id)
            player = self._player_by_alias(session, aliases) if session else None
            return session, player

        for session in self._sessions.values():
            player = self._player_by_alias(session, aliases)
            if player:
                player.aliases.update(aliases)
                return session, player
        return None, None

    def _player_by_alias(self, session: MafiaSession | None, aliases: set[str]) -> Player | None:
        if not session:
            return None
        for alias in aliases:
            player = session.players.get(alias)
            if player:
                player.aliases.update(aliases)
                return player
        for player in session.players.values():
            if player.aliases.intersection(aliases):
                player.aliases.update(aliases)
                return player
        return None

    def _ctx_aliases(self, ctx: CommandContext) -> set[str]:
        aliases = {alias for alias in ctx.sender_aliases if alias}
        aliases.add(ctx.sender_id)
        if not ctx.is_group:
            aliases.add(_canonical_jid_id(ctx.chat_id))
        return {alias for alias in aliases if alias}

    def _register_private_routes(self, session: MafiaSession, player: Player) -> None:
        for alias in player.aliases | {player.user_id}:
            self._private_routes[alias] = session.group_id

    def _clear_pending_routes(self, session: MafiaSession) -> None:
        for player_id in list(session.pending_actions):
            player = session.players.get(player_id)
            aliases = (player.aliases | {player.user_id}) if player else {player_id}
            for alias in aliases:
                self._private_routes.pop(alias, None)

    def _parse_team_message(self, ctx: CommandContext, text: str) -> str | None:
        value = " ".join(text.strip().split())
        prefix = ctx.app.settings.cmd_prefix
        for marker in (f"{prefix}team", "team"):
            if value.casefold() == marker:
                return ""
            if value.casefold().startswith(marker + " "):
                return value[len(marker) :].strip()
        return None

    def _role_plan(self, player_count: int) -> list[str]:
        mafia_count = max(1, player_count // 6)
        medic_count = max(1, player_count // 8)
        jester_count = 3 if player_count > 16 and random.randint(1, 1000) == 1 else 1
        reserved = mafia_count + medic_count + 1 + jester_count
        if reserved >= player_count:
            overflow = reserved - player_count + 1
            medic_count = max(1, medic_count - overflow)
        return (
            [ROLE_MAFIA] * mafia_count
            + [ROLE_MEDIC] * medic_count
            + [ROLE_DETECTIVE]
            + [ROLE_JESTER] * jester_count
        )

    async def _night_story(self, session: MafiaSession, killed: Player | None, blocked: bool) -> str:
        fallback = self._fallback_night_result(session, killed, blocked)
        kill_id = session.actions.get("kill")
        protect_id = session.actions.get("protect")
        investigated_id = session.actions.get("investigate")
        facts = [
            f"Night {session.night_number} resolved.",
            f"Mafia target: {self._nickname_for(session, kill_id) or 'none'}.",
            f"Medic protected: {self._nickname_for(session, protect_id) or 'none'}.",
            f"Detective investigated: {self._nickname_for(session, investigated_id) or 'none'}.",
            f"Public death: {killed.nickname + ' (' + killed.role + ')' if killed else 'none'}.",
            "The Medic blocked the kill." if blocked else "The Medic did not block the kill.",
        ]
        return await self._story_text(
            session,
            "night-result",
            " ".join(facts) + " Write the public morning story. Reveal only public death and role if someone died.",
            fallback,
        )

    def _fallback_prelude(self, session: MafiaSession) -> str:
        return (
            "The lobby opened under a heavy silence. Names began to gather one by one, each arrival "
            "making the room feel smaller, colder, and harder to leave.\n\n"
            f"When {session.target_size} names are written down, the host may begin. After that, trust becomes evidence."
        )

    def _fallback_night_opening(self, session: MafiaSession) -> str:
        return (
            f"Night {session.night_number} settles over the game. The group grows quiet, but the silence does not feel empty. "
            "It feels occupied.\n\n"
            "Somewhere in the dark, a decision is waiting for a name."
        )

    def _fallback_night_result(self, session: MafiaSession, killed: Player | None, blocked: bool) -> str:
        opening = random.choice(
            [
                "Morning arrived slowly, as if it had been dragged back into the room.",
                "The dark withdrew, but it left proof that someone had been moving through it.",
                "When the first messages returned, nobody sounded as confident as they had the night before.",
            ]
        )
        if killed:
            result = f"By morning, {killed.nickname} was gone. Role: {killed.role}."
        elif blocked:
            result = "Someone was targeted, but the Medic handled it. No death tonight."
        else:
            result = "No one died. That should have felt comforting. It did not."
        return f"{opening}\n{result}"

    async def _story_text(self, session: MafiaSession, scene: str, prompt: str, fallback: str) -> str:
        if not self.app or not getattr(self.app, "ai", None):
            return fallback
        roster = ", ".join(player.nickname for player in session.players.values())
        full_prompt = (
            "Write narration for a WhatsApp Mafia game. "
            "Style: scary, suspenseful, serious, confident. No emojis. No markdown. "
            "Keep it under 120 words and do not reveal hidden roles unless explicitly included in the facts. "
            f"Scene: {scene}. Roster: {roster}. Facts: {prompt}"
        )
        try:
            text = await asyncio.wait_for(
                self.app.ai.ask(f"mafia-story:{session.group_id}", full_prompt, profile="smart"),
                timeout=STORY_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            LOG.warning("Could not generate Mafia story: %s", exc)
            return fallback
        return self._clean_story_text(text) or fallback

    def _clean_story_text(self, text: str) -> str:
        cleaned = text.encode("ascii", "ignore").decode("ascii")
        cleaned = "\n".join(line.strip() for line in cleaned.splitlines() if line.strip())
        return cleaned[:900].strip()

    def _winner(self, session: MafiaSession) -> str | None:
        alive = self._alive_players(session)
        mafia_alive = [player for player in alive if player.role == ROLE_MAFIA]
        non_mafia_alive = [player for player in alive if player.role != ROLE_MAFIA]
        if not mafia_alive:
            return "town"
        if len(mafia_alive) >= len(non_mafia_alive):
            return "mafia"
        return None

    def _alive_players(self, session: MafiaSession) -> list[Player]:
        return [player for player in session.players.values() if player.alive]

    def _living_players_by_role(self, session: MafiaSession, role: str) -> list[Player]:
        return [player for player in session.players.values() if player.alive and player.role == role]

    def _living_role(self, session: MafiaSession, role: str) -> Player | None:
        for player in session.players.values():
            if player.alive and player.role == role:
                return player
        return None

    def _nickname_for(self, session: MafiaSession, player_id: str | None) -> str:
        if not player_id:
            return ""
        player = session.players.get(player_id)
        return player.nickname if player else ""

    def _find_living_player(self, session: MafiaSession, nickname: str) -> Player | None:
        player_id = session.nickname_index.get(_nickname_key(nickname))
        if not player_id:
            return None
        player = session.players[player_id]
        return player if player.alive else None

    def _private_action_target(self, ctx: CommandContext, text: str, action: str) -> str:
        value = " ".join(text.strip().split())
        prefix = ctx.app.settings.cmd_prefix
        for marker in (f"{prefix}{action}", action):
            if value.casefold().startswith(marker + " "):
                return value[len(marker) :].strip()
        return value

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

    def _parse_lobby_args(self, args: str) -> tuple[int, str]:
        parts = args.strip().split(maxsplit=1)
        if not parts:
            return DEFAULT_PLAYER_TARGET, ""
        try:
            target_size = int(parts[0])
        except ValueError:
            return DEFAULT_PLAYER_TARGET, args.strip()
        nickname = parts[1].strip() if len(parts) > 1 else ""
        return target_size, nickname

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


def _canonical_jid_id(value: str | None) -> str:
    if not value:
        return ""
    user, separator, server = value.partition("@")
    if not separator:
        return value
    user = user.split(":", 1)[0]
    return f"{user}@{server}"


def _clone_proto(value: Any) -> Any:
    clone = value.__class__()
    clone.MergeFrom(value)
    return clone
