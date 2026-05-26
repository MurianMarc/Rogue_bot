from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

import aiohttp

from .config import Settings


@dataclass(frozen=True, slots=True)
class LeagueSource:
    name: str
    url: str


LEAGUES = (
    LeagueSource("Premier League", "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard"),
    LeagueSource("LaLiga", "https://site.api.espn.com/apis/site/v2/sports/soccer/esp.1/scoreboard"),
    LeagueSource("Serie A", "https://site.api.espn.com/apis/site/v2/sports/soccer/ita.1/scoreboard"),
    LeagueSource("Bundesliga", "https://site.api.espn.com/apis/site/v2/sports/soccer/ger.1/scoreboard"),
    LeagueSource("Ligue 1", "https://site.api.espn.com/apis/site/v2/sports/soccer/fra.1/scoreboard"),
    LeagueSource("Champions League", "https://site.api.espn.com/apis/site/v2/sports/soccer/uefa.champions/scoreboard"),
    LeagueSource("Europa League", "https://site.api.espn.com/apis/site/v2/sports/soccer/uefa.europa/scoreboard"),
)


async def live_scores(settings: Settings) -> str:
    timeout = aiohttp.ClientTimeout(total=settings.scores_timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        results = await asyncio.gather(
            *(_fetch_league(session, league) for league in LEAGUES),
            return_exceptions=True,
        )

    live: list[str] = []
    other: list[str] = []
    errors = 0
    for result in results:
        if isinstance(result, Exception):
            errors += 1
            continue
        for line, is_live in result:
            if is_live:
                live.append(line)
            else:
                other.append(line)

    stamp = datetime.now(timezone.utc).strftime("%H:%M UTC")
    if live:
        return "\n".join([f"Live football scores ({stamp})", *live[:12]])
    if other:
        return "\n".join(
            [
                f"No live football scores found ({stamp}). Closest fixtures/results:",
                *other[:10],
            ]
        )
    if errors:
        return "Could not fetch live scores right now. The score wires are being dramatic."
    return f"No live football scores found ({stamp})."


async def _fetch_league(
    session: aiohttp.ClientSession, league: LeagueSource
) -> list[tuple[str, bool]]:
    async with session.get(league.url) as response:
        response.raise_for_status()
        data = await response.json()

    lines: list[tuple[str, bool]] = []
    for event in data.get("events", []):
        competitions = event.get("competitions") or []
        if not competitions:
            continue
        competition = competitions[0]
        status = (competition.get("status") or event.get("status") or {}).get("type", {})
        state = (status.get("state") or "").casefold()
        detail = status.get("shortDetail") or status.get("detail") or "TBD"

        home = away = None
        for competitor in competition.get("competitors", []):
            side = competitor.get("homeAway")
            team = (competitor.get("team") or {}).get("shortDisplayName") or "Unknown"
            score = competitor.get("score", "0")
            if side == "home":
                home = (team, score)
            elif side == "away":
                away = (team, score)
        if not home or not away:
            continue

        is_live = state == "in"
        marker = "LIVE" if is_live else detail
        line = f"{marker} | {league.name} | {home[0]} {home[1]} - {away[1]} {away[0]}"
        lines.append((line, is_live))
    return lines
