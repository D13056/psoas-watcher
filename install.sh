#!/usr/bin/env bash
set -euo pipefail

# Installer wrapper stored with project copy

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
cp "$SCRIPT_DIR/../watch_psoas.py" "$SCRIPT_DIR/watch_psoas.py"
cp "$SCRIPT_DIR/../install_psoas_watcher.sh" "$SCRIPT_DIR/install_psoas_watcher.sh"

bash "$SCRIPT_DIR/install_psoas_watcher.sh"
