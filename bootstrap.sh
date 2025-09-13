#!/usr/bin/env bash
set -euo pipefail

# Bootstrap installer: clone repo and run installer.
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/USER/REPO/branch/bootstrap.sh | bash

REPO_URL=${REPO_URL:-"https://github.com/REPLACE_ME/psoas-watcher.git"}
CLONE_DIR=${CLONE_DIR:-"/opt/psoas-watcher-src"}

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root (sudo)" >&2
  exit 1
fi

rm -rf "$CLONE_DIR"
mkdir -p "$CLONE_DIR"

command -v git >/dev/null 2>&1 || apt-get update && apt-get install -y git

git clone "$REPO_URL" "$CLONE_DIR"
cd "$CLONE_DIR"

# If a .env is present in this directory, the installer will import it automatically.
bash install_psoas_watcher.sh
