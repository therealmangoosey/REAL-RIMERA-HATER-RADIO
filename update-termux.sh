#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

if ! git rev-parse --show-toplevel >/dev/null 2>&1; then
  echo "ERROR: Run this from the REAL-RIMERA-HATER-RADIO repository directory."
  exit 1
fi

cd "$(git rev-parse --show-toplevel)"
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

if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git ls-files --others --exclude-standard)" ]; then
  echo "Stashing local changes so the update cannot be blocked..."
  git stash push -u -m "automatic pre-rimera-termux-update $(date +%Y%m%d-%H%M%S)" || true
fi

rm -f .git/index.lock

echo "Fetching latest main from GitHub..."
git fetch --prune origin main
git reset --hard origin/main
# Keep runtime configuration, cookies, the virtualenv, and local backup data.
git clean -fd \
  -e .env \
  -e config.json \
  -e cache.json \
  -e instagram-cookies.txt \
  -e .venv/ \
  -e .pytest_cache/

echo "Restoring local configuration..."
restore_file .env
restore_file config.json
restore_file cache.json
restore_file instagram-cookies.txt

pkg update -y
pkg install -y python git ffmpeg curl

if [ ! -d .venv ]; then
  echo "Creating Python virtual environment..."
  python -m venv .venv
fi

. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-termux.txt --upgrade

python -m compileall -q bot.py media_downloader.py instagram_fallback.py discord_formatter.py state_manager.py scrapers
python -m unittest discover -v

echo ""
echo "Update and checks complete. Starting bot..."
exec bash termux-start.sh
