#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

cd "$(dirname "$0")"
REPO_DIR="$(pwd)"
BACKUP_DIR="$HOME/.rimera-hater-radio-backup"
mkdir -p "$BACKUP_DIR"

backup_file() {
  local file="$1"
  if [ -f "$file" ]; then
    cp -f "$file" "$BACKUP_DIR/$(basename "$file")"
  fi
}

restore_file() {
  local file="$1"
  if [ -f "$BACKUP_DIR/$(basename "$file")" ]; then
    cp -f "$BACKUP_DIR/$(basename "$file")" "$file"
  fi
}

echo "Backing up local configuration..."
backup_file .env
backup_file config.json
backup_file cache.json
backup_file instagram-cookies.txt

if [ -f .git/index.lock ]; then
  rm -f .git/index.lock
fi

echo "Updating from origin/main..."
git fetch origin main
git reset --hard origin/main

echo "Restoring local configuration..."
restore_file .env
restore_file config.json
restore_file cache.json
restore_file instagram-cookies.txt

pkg install -y python git ffmpeg >/dev/null 2>&1 || true

if [ ! -d .venv ]; then
  python -m venv .venv
fi

. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-termux.txt --upgrade

python -m compileall -q bot.py media_downloader.py discord_formatter.py state_manager.py scrapers

echo ""
echo "Update complete. Starting bot..."
exec bash termux-start.sh
