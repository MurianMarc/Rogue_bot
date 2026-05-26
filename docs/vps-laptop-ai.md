# VPS Bot With Laptop AI

This setup keeps the WhatsApp bot online on a VPS while your laptop runs the heavy Ollama models.

## What Stays Online

- The VPS runs the Python WhatsApp bot, filters, stickers, scores, and Mafia game.
- The laptop runs Ollama and the smart/fast AI models.
- The VPS calls the laptop through a private Tailscale IP.
- If the laptop is off, the bot stays online, but `!ask` and `!fast` cannot answer until Ollama is back.

Do not expose Ollama port `11434` directly to the public internet. Use Tailscale or another private tunnel.

## Laptop

Install and sign in to Tailscale on the laptop, then run:

```powershell
.\deploy_models.ps1 -NoRestart
```

Start Ollama so the VPS can reach it through Tailscale:

```powershell
.\start_laptop_ai.ps1 -AllowTailscaleFirewall -Persist
```

If PowerShell says the firewall rule needs Administrator, reopen PowerShell as Administrator and run the same command again.
When Tailscale is available, the script binds Ollama to the laptop's Tailscale IP.

The script prints the value to use on the VPS:

```text
OLLAMA_URL=http://100.x.y.z:11434
```

## VPS

Install and sign in to Tailscale on the VPS, then confirm it can reach the laptop:

```bash
curl http://100.x.y.z:11434/api/tags
```

Clone the repo on the VPS, then run:

```bash
cp .env.vps.example .env
nano .env
```

Set:

```env
OLLAMA_URL=http://100.x.y.z:11434
PH_NUMBER=234xxxxxxxxxx
```

Make sure `OLLAMA_MODEL` and `OLLAMA_FAST_MODEL` match models installed on the laptop.

Then install and start the bot:

```bash
bash scripts/setup_vps_bot.sh
```

Watch the pairing/login logs:

```bash
journalctl --user -u rogue-bot -f
```

## Updating

On the VPS:

```bash
git pull
bash scripts/setup_vps_bot.sh
systemctl --user restart rogue-bot
```

On the laptop, keep Ollama running:

```powershell
.\start_laptop_ai.ps1
```
