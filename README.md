# Rogue Bot

Rogue Bot is a WhatsApp bot focused on quick AI replies and sticker creation.

## Features

- Smart AI question answering with `!ask <question>` using `qwen3:8b`.
- Rate-limited super AI answers with `!super <question>` using `qwen3:14b`.
- Persistent `!init` authorization for DMs and groups.
- Online announcement to authorized chats when the bot connects.
- Separate smart and super model personalities.
- Local AI support through Ollama, so questions can be answered without paid API calls.
- Model optimizer and warm-up script for `qwen3:8b` and `qwen3:14b`.
- Short per-chat memory for follow-up questions.
- `!reset` command to clear a chat's AI memory.
- Random rude-but-playful replies for unknown commands.
- `!ping` latency and uptime check.
- `!scores` live football score lookup.
- Group-only Mafia game with flexible lobby sizes, host-controlled start, `!join`, `!skip`, `!nominate`, and `!vote`.
- Scaled Mafia roles with Mafia teams, Medic teams, one Detective, Jester, Town players, and a rare triple-Jester setup.
- Sequential Mafia night actions through DMs in Mafia, Medic, Detective order, using nicknames or `!kill`, `!protect`, and `!investigate`.
- Private `!team` relay for Mafia and Medic coordination.
- Suspense-styled Mafia preludes and night stories with optional local AI narration.
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
