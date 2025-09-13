# PSOAS Watcher

Monitors the PSOAS apartment listing page and sends Telegram (and optional email) alerts when new listings appear or when the page changes.

## Features
- Runs every minute via systemd timer on Ubuntu
- Telegram alerts for new listings (recommended)
- Email notifications (optional)
- Unified diff in change notifications
- Robust fetch with headers and timeouts
- Persistent state to avoid duplicate alerts

## Quick install (one line)
Replace YOUR_GH_USER in the command:

```bash
sudo bash -lc 'apt-get update -y && apt-get install -y curl git && curl -fsSL https://raw.githubusercontent.com/YOUR_GH_USER/psoas-watcher/main/bootstrap.sh | bash'
```

This will:
- Clone the repo into /opt/psoas-watcher-src
- Run the installer
- Install the app to /opt/psoas-watcher and enable the timer

## Manual install
```bash
git clone https://github.com/YOUR_GH_USER/psoas-watcher.git
cd psoas-watcher
sudo bash install_psoas_watcher.sh
```

If you have a ready `.env`, place it next to the installer before running; it will be imported.

## .env settings
See `.env.example`. Key variables:
- TELEGRAM_BOT_TOKEN: from BotFather
- TELEGRAM_CHAT_ID: your chat id
- NOTIFY_ON_FIRST_RUN=true|false
- EMAIL_ON_ERROR=true|false, TELEGRAM_ON_ERROR=true|false

## Service management
```bash
# Check timer status
systemctl status psoas-watcher.timer

# View logs
journalctl -u psoas-watcher.service -f

# Manual check
sudo /opt/psoas-watcher/venv/bin/python3 /opt/psoas-watcher/watch_psoas.py --once --debug
```

## Uninstall
```bash
sudo systemctl disable --now psoas-watcher.timer || true
sudo rm -f /etc/systemd/system/psoas-watcher.service /etc/systemd/system/psoas-watcher.timer
sudo systemctl daemon-reload || true
sudo rm -rf /opt/psoas-watcher /opt/psoas-watcher-src
```
