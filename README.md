# Rogue Bot

Rogue Bot is a WhatsApp bot focused on quick AI replies and sticker creation.

## Features

- AI question answering with `!ask <question>`.
- Local AI support through Ollama, so questions can be answered without paid API calls.
- Short per-chat memory for follow-up questions.
- `!reset` command to clear a chat's AI memory.
- Sticker maker with `!sticker`.
- Sticker creation from attached images, GIFs, short videos, or replied media.
- Custom sticker pack name and sticker author metadata.
- WhatsApp companion-device login using QR code or phone-number pairing.
- Command-only behavior by default, so it responds only when called.
- Optional `?` auto-question mode for quick prompts.
- Optional chat allow-listing with `ALLOWED_CHATS`.
- `!id` command to show the current chat ID.
- Built-in help with `!help`.
- Bundled FFmpeg support for video and GIF sticker conversion.
- Python-based structure using `neonize`.
