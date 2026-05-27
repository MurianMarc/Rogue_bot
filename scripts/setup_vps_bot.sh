#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="${SERVICE_NAME:-rogue-bot}"
INSTALL_SERVICE="${INSTALL_SERVICE:-1}"
SWAP_SIZE_MB="${SWAP_SIZE_MB:-1024}"

log() {
  printf '[vps-bot] %s\n' "$1"
}

install_packages() {
  if command -v apt-get >/dev/null 2>&1; then
    log "Installing Linux packages."
    sudo apt-get update
    sudo apt-get install -y python3 python3-venv python3-pip git ffmpeg libmagic1
  elif command -v dnf >/dev/null 2>&1; then
    log "Installing Linux packages with dnf."
    sudo dnf install -y python3 python3-pip git file-libs
    if ! command -v ffmpeg >/dev/null 2>&1; then
      sudo dnf install -y oracle-epel-release-el9 || true
      sudo dnf install -y ffmpeg || log "ffmpeg was not available. Static image stickers still work."
    fi
  else
    log "apt-get/dnf not found. Install python3, pip, git, ffmpeg, and libmagic manually."
  fi
}

ensure_swap() {
  if [[ "$SWAP_SIZE_MB" == "0" ]]; then
    log "Skipping swap setup."
    return
  fi

  if [[ -s /proc/swaps ]] && awk 'NR > 1 { found = 1 } END { exit !found }' /proc/swaps; then
    log "Swap is already enabled."
    return
  fi

  local swapfile="/swapfile"
  log "Creating ${SWAP_SIZE_MB}MB swap file for low-memory VPS stability."
  if command -v fallocate >/dev/null 2>&1; then
    sudo fallocate -l "${SWAP_SIZE_MB}M" "$swapfile"
  else
    sudo dd if=/dev/zero of="$swapfile" bs=1M count="$SWAP_SIZE_MB"
  fi
  sudo chmod 600 "$swapfile"
  sudo mkswap "$swapfile"
  sudo swapon "$swapfile"
  if ! grep -q "^$swapfile " /etc/fstab; then
    echo "$swapfile none swap sw 0 0" | sudo tee -a /etc/fstab >/dev/null
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
ensure_swap

log "Creating Python virtual environment."
if ! python3 -m venv .venv; then
  log "python3 venv failed; trying virtualenv fallback."
  python3 -m pip install --user virtualenv
  python3 -m virtualenv .venv
fi

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
