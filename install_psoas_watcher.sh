#!/usr/bin/env bash
set -euo pipefail

# All-in-one installer for PSOAS page watcher on Ubuntu
# - Creates /opt/psoas-watcher with a Python venv
# - Installs dependencies
# - Creates an .env with SMTP creds and configuration
# - Installs systemd service and timer to run every minute

APP_DIR="/opt/psoas-watcher"
STATE_DIR="$APP_DIR/state"
VENV_DIR="$APP_DIR/venv"
PY_BIN="$VENV_DIR/bin/python3"
PIP_BIN="$VENV_DIR/bin/pip"
SERVICE_NAME="psoas-watcher"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
TIMER_FILE="/etc/systemd/system/${SERVICE_NAME}.timer"
REPO_SCRIPT_SRC="watch_psoas.py"
APP_SCRIPT="$APP_DIR/watch_psoas.py"
ENV_FILE="$APP_DIR/.env"

require_root() {
  if [[ "$EUID" -ne 0 ]]; then
    echo "Please run as root (use sudo)" >&2
    exit 1
  fi
}

install_prereqs() {
  apt-get update
  apt-get install -y python3-venv python3-pip
}

setup_app_dir() {
  mkdir -p "$APP_DIR" "$STATE_DIR"
  # Copy script from current workspace if present, else fetch via curl placeholder
  if [[ -f "$REPO_SCRIPT_SRC" ]]; then
    cp "$REPO_SCRIPT_SRC" "$APP_SCRIPT"
  else
    echo "watcher script not found in current dir" >&2
    exit 1
  fi
  chown -R root:root "$APP_DIR"
}

setup_venv() {
  if [[ ! -d "$VENV_DIR" ]]; then
    python3 -m venv "$VENV_DIR"
  fi
  "$PIP_BIN" install --upgrade pip
  "$PIP_BIN" install requests beautifulsoup4 python-dotenv
}

prompt_env() {
  # If a local .env exists, import it directly to avoid prompting
  if [[ -f .env ]]; then
    echo "Found local .env in $(pwd). Importing into $ENV_FILE"
    cp .env "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    return
  fi

  echo "Configure SMTP to send emails (values saved to $ENV_FILE)"
  read -rp "Recipient email [default: litecointele@gmail.com]: " RECIPIENT_EMAIL
  RECIPIENT_EMAIL=${RECIPIENT_EMAIL:-litecointele@gmail.com}
  read -rp "SMTP server [default: smtp.gmail.com]: " SMTP_SERVER
  SMTP_SERVER=${SMTP_SERVER:-smtp.gmail.com}
  read -rp "SMTP port [default: 587]: " SMTP_PORT
  SMTP_PORT=${SMTP_PORT:-587}
  read -rp "SMTP username (email address): " SMTP_USERNAME
  read -rsp "SMTP password (app password recommended): " SMTP_PASSWORD
  echo
  read -rp "From email address [default: ${SMTP_USERNAME}]: " EMAIL_FROM
  EMAIL_FROM=${EMAIL_FROM:-$SMTP_USERNAME}

  echo
  echo "Optionally configure Telegram alerts (recommended if email isn't working)."
  read -rp "Telegram bot token (leave empty to skip): " TELEGRAM_BOT_TOKEN
  read -rp "Telegram chat ID (leave empty to skip): " TELEGRAM_CHAT_ID

  cat > "$ENV_FILE" <<EOF
URL="https://www.psoas.fi/en/apartments/?_sfm_htyyppi=k-%2C-p-%2C-y&_sfm_huoneistojen_tilanne=vapaa_ja_vapautumassa&_sfm_koko=7+84&_sfm_vuokra=161+791&_sfm_huonelkm=1+7"
STATE_DIR="$STATE_DIR"
RECIPIENT_EMAIL="$RECIPIENT_EMAIL"
SMTP_SERVER="$SMTP_SERVER"
SMTP_PORT="$SMTP_PORT"
SMTP_USERNAME="$SMTP_USERNAME"
SMTP_PASSWORD="$SMTP_PASSWORD"
EMAIL_FROM="$EMAIL_FROM"
# Telegram (optional)
TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID="$TELEGRAM_CHAT_ID"
# Set to true to get a notification on the first baseline run
NOTIFY_ON_FIRST_RUN=false
# Set to true to get emails when the script errors
EMAIL_ON_ERROR=true
# Set to true to get Telegram messages when the script errors
TELEGRAM_ON_ERROR=true
EOF
  chmod 600 "$ENV_FILE"
}

install_systemd() {
  cat > "$SERVICE_FILE" <<SERVICE
[Unit]
Description=PSOAS watcher - check page and email on change
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$PY_BIN $APP_SCRIPT --once
# Log to journal
StandardOutput=journal
StandardError=journal
RuntimeDirectoryMode=0755

[Install]
WantedBy=multi-user.target
SERVICE

  cat > "$TIMER_FILE" <<TIMER
[Unit]
Description=Run PSOAS watcher every minute

[Timer]
OnBootSec=30sec
OnUnitActiveSec=60sec
AccuracySec=5sec
Unit=${SERVICE_NAME}.service

[Install]
WantedBy=timers.target
TIMER

  systemctl daemon-reload
  systemctl enable --now ${SERVICE_NAME}.timer
}

smoke_test() {
  echo "Running a one-time check to establish baseline..."
  "$PY_BIN" "$APP_SCRIPT" --once --debug || true
}

main() {
  require_root
  install_prereqs
  setup_app_dir
  setup_venv
  prompt_env
  install_systemd
  smoke_test
  echo "\nInstallation complete. The watcher is scheduled every minute via systemd timer: ${SERVICE_NAME}.timer"
  echo "Use: journalctl -u ${SERVICE_NAME}.service -f   to watch logs"
  echo "Check timer: systemctl status ${SERVICE_NAME}.timer"
}

main "$@"
