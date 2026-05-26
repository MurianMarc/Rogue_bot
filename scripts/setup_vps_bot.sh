#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="${SERVICE_NAME:-rogue-bot}"
INSTALL_SERVICE="${INSTALL_SERVICE:-1}"

log() {
  printf '[vps-bot] %s\n' "$1"
}

install_packages() {
  if command -v apt-get >/dev/null 2>&1; then
    log "Installing Linux packages."
    sudo apt-get update
    sudo apt-get install -y python3 python3-venv python3-pip git ffmpeg libmagic1
  else
    log "apt-get not found. Install python3, python3-venv, git, ffmpeg, and libmagic manually."
  fi
}

write_service() {
  local service_dir="$HOME/.config/systemd/user"
  local service_file="$service_dir/$SERVICE_NAME.service"

  if ! command -v systemctl >/dev/null 2>&1; then
    log "systemctl not found. Start manually with: $ROOT/.venv/bin/python -m bot"
    return
  fi

  mkdir -p "$service_dir"
  cat > "$service_file" <<SERVICE
[Unit]
Description=Rogue Bot WhatsApp service
After=network-online.target

[Service]
Type=simple
WorkingDirectory=$ROOT
ExecStart=$ROOT/.venv/bin/python -m bot
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
SERVICE

  systemctl --user daemon-reload
  systemctl --user enable --now "$SERVICE_NAME"

  if command -v loginctl >/dev/null 2>&1; then
    sudo loginctl enable-linger "$USER" || true
  fi

  log "Service started. Watch logs with: journalctl --user -u $SERVICE_NAME -f"
}

cd "$ROOT"
install_packages

log "Creating Python virtual environment."
python3 -m venv .venv

log "Installing Python dependencies."
"$ROOT/.venv/bin/python" -m pip install --upgrade pip
"$ROOT/.venv/bin/python" -m pip install -r requirements.txt

mkdir -p logs sessions storage/stickers

if [[ ! -f .env ]]; then
  if [[ -f .env.vps.example ]]; then
    cp .env.vps.example .env
    log "Created .env from .env.vps.example. Edit OLLAMA_URL and PH_NUMBER before pairing."
  else
    cp .env.example .env
    log "Created .env from .env.example. Edit OLLAMA_URL and PH_NUMBER before pairing."
  fi
fi

if grep -q "YOUR_LAPTOP_TAILSCALE_IP" .env; then
  log "Edit .env and replace YOUR_LAPTOP_TAILSCALE_IP with your laptop's Tailscale IP, then rerun this script."
  exit 0
fi

if [[ "$INSTALL_SERVICE" == "1" ]]; then
  write_service
else
  log "Skipping service install. Start manually with: $ROOT/.venv/bin/python -m bot"
fi
