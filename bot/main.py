from __future__ import annotations

import logging
import signal

from neonize.aioze.client import NewAClient
from neonize.aioze.events import ConnectedEv, DisconnectedEv, LoggedOutEv, MessageEv, PairStatusEv
from neonize.utils import log as neonize_log

from .ai import OllamaClient
from .app import RogueBot
from .commands import register_commands
from .config import settings
from .ffmpeg import add_bundled_ffmpeg_to_path


def build_bot() -> tuple[NewAClient, RogueBot]:
    settings.wa_db.parent.mkdir(parents=True, exist_ok=True)
    client = NewAClient(str(settings.wa_db))
    app = RogueBot(settings, OllamaClient(settings))
    register_commands(app)

    @client.event(ConnectedEv)
    async def on_connected(_: NewAClient, __: ConnectedEv) -> None:
        logging.info("%s connected.", settings.bot_name)

    @client.event(PairStatusEv)
    async def on_pair_status(_: NewAClient, event: PairStatusEv) -> None:
        logging.info("Pair status: %s", event)

    @client.event(DisconnectedEv)
    async def on_disconnected(_: NewAClient, event: DisconnectedEv) -> None:
        logging.warning("Disconnected: %s", event)

    @client.event(LoggedOutEv)
    async def on_logged_out(_: NewAClient, event: LoggedOutEv) -> None:
        logging.warning("Logged out: %s", event)

    @client.event(MessageEv)
    async def on_message(client_: NewAClient, message: MessageEv) -> None:
        await app.handle_message(client_, message)

    return client, app


async def start(client: NewAClient) -> None:
    if settings.phone_number:
        logging.info("Pairing by phone number ending in %s.", settings.phone_number[-4:])
        await client.PairPhone(settings.phone_number, show_push_notification=settings.show_pair_push)
    else:
        logging.info("No PH_NUMBER set; QR code login will be shown in the terminal.")
        await client.connect()

    await client.idle()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    neonize_log.setLevel(logging.INFO)
    add_bundled_ffmpeg_to_path()
    client, _ = build_bot()

    def stop_client(*_: object) -> None:
        client.loop.create_task(client.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, stop_client)
        except ValueError:
            pass

    client.loop.run_until_complete(start(client))
