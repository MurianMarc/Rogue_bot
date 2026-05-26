# Rogue Bot

A Python WhatsApp bot that can answer questions with a local Ollama model and turn images, GIFs, or short videos into stickers.

The bot is intentionally small and command-based. Its structure is inspired by `neon_bot`'s `neonize` setup: phone pairing, a command registry, and native sticker sending.

## Important Reality Check

This project uses an unofficial WhatsApp companion-device library. That means it can break if WhatsApp changes things, and automation can put your number at risk if you spam or run it like a public bot. Test with a spare number if you can.

For a 100% free AI setup, this bot uses Ollama on your own computer. Grok/xAI and most hosted AI APIs are paid by usage.

## What Happens If You Link Your Number?

If you set `PH_NUMBER`, the bot links to that WhatsApp account as a companion device. When people send messages to that number, Rogue Bot receives the messages and can reply from that same number.

In plain terms: the replies look like they came from your WhatsApp account. If you also type from your phone, the bot ignores your own outgoing messages to avoid loops. If you want to chat with the bot yourself, use a separate WhatsApp number for the bot.

## Features

- `!ask <question>`: ask local Ollama
- `!sticker`: make a sticker from attached media or replied media
- `!reset`: clear short AI memory for the chat
- `!id`: show the chat ID for allow-listing
- `!help`: show commands

## Setup

1. Install Python 3.11 or newer.
2. Install Ollama from <https://ollama.com/download>.
3. Pull a local model:

```powershell
ollama pull llama3.2:3b
```

4. Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, use:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

5. Install dependencies:

```powershell
pip install -r requirements.txt
```

6. Create your config:

```powershell
Copy-Item .env.example .env
```

7. Edit `.env`.

For phone pairing:

```env
PH_NUMBER=2348012345678
```

Use country code, no `+`, no spaces.

For QR login, leave `PH_NUMBER` blank.

8. Start Ollama:

```powershell
ollama serve
```

9. In another terminal, run the bot:

```powershell
python -m bot
```

If `PH_NUMBER` is set, WhatsApp should send a pairing request/code to that number. If it is blank, scan the QR code from WhatsApp mobile app -> Linked devices -> Link a device.

## Commands

```text
!help
!ask why is the sky blue?
!reset
!id
!sticker
```

For stickers, send an image/video/GIF with caption `!sticker`, or reply to existing media with `!sticker`.

## Config

- `PH_NUMBER`: phone number to pair, with country code and no plus sign.
- `WA_DB`: local WhatsApp session database path.
- `CMD_PREFIX`: command prefix, default `!`.
- `ALLOWED_CHATS`: comma-separated chat IDs. Leave empty to allow all chats.
- `OLLAMA_URL`: default `http://127.0.0.1:11434`.
- `OLLAMA_MODEL`: default `llama3.2:3b`.
- `ENABLE_AUTO_QUESTION_MARK`: set `true` to answer messages that start with `?`.
- `STICKER_PACK_NAME`: sticker pack name.
- `STICKER_AUTHOR`: sticker author/name fallback.

## Notes

Video/GIF stickers need FFmpeg. The project includes `imageio-ffmpeg`, and the bot adds its bundled FFmpeg to `PATH` on startup so you usually do not need a separate FFmpeg install.
