# Rogue Bot

Rogue Bot is a WhatsApp bot focused on quick AI replies and sticker creation.

## Features

- Smart AI question answering with `!ask <question>`.
- Fast CPU AI answers with `!fast <question>`.
- Separate smart and fast model personalities.
- Local AI support through Ollama, so questions can be answered without paid API calls.
- Smart GPU model and fast CPU model deployment script.
- Short per-chat memory for follow-up questions.
- `!reset` command to clear a chat's AI memory.
- Random rude-but-playful replies for unknown commands.
- `!ping` latency and uptime check.
- `!scores` live football score lookup.
- Group-only Mafia game with `!game start`, `!join`, `!skip`, `!nominate`, and `!vote`.
- Mafia roles for Mafia, Medic, Detective, Jester, and Town players.
- Mafia night actions through DMs and group voting through WhatsApp polls.
- Text and sticker filters with `!filter`, `!filters`, and `!del_filter`.
- Sticker maker with `!sticker`.
- Sticker creation from attached images, GIFs, short videos, or replied media.
- Local sticker archive under `storage/stickers`.
- Custom sticker pack name and sticker author metadata.
- `!stickers` command to show stored sticker files.
- WhatsApp companion-device login using QR code or phone-number pairing.
- Command-only behavior by default, so it responds only when called.
- Optional `?` auto-question mode for quick prompts.
- Optional chat allow-listing with `ALLOWED_CHATS`.
- Low-memory VPS mode for 1 GB servers when AI runs on another machine.
- `!id` command to show the current chat ID.
- Built-in help with `!help`.
- Bundled FFmpeg support for video and GIF sticker conversion.
- Python-based structure using `neonize`.
