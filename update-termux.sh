#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

# Run this script from the repository directory. It is intentionally safe to
# run even when the local checkout contains uncommitted changes.
if ! git rev-parse --show-toplevel >/dev/null 2>&1; then
  echo "ERROR: Run this from the REAL-RIMERA-HATER-RADIO repository directory."
  exit 1
fi

cd "$(git rev-parse --show-toplevel)"
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

# Preserve local runtime/config files before replacing the checkout.
echo "Backing up local configuration..."
backup_file .env
backup_file config.json
backup_file cache.json
backup_file instagram-cookies.txt

# Preserve any other local work in Git's stash before the hard reset. This is
# recoverable with `git stash list`; config/runtime files are separately backed up.
if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git ls-files --others --exclude-standard)" ]; then
  echo "Stashing local changes so the update cannot be blocked..."
  git stash push -u -m "automatic pre-rimera-termux-update $(date +%Y%m%d-%H%M%S)" || true
fi

# Remove stale locks left by an interrupted Git operation.
rm -f .git/index.lock

echo "Fetching latest main from GitHub..."
git fetch --prune origin main

git reset --hard origin/main

git clean -fd -e .env -e config.json -e cache.json -e instagram-cookies.txt

echo "Restoring local configuration..."
restore_file .env
restore_file config.json
restore_file cache.json
restore_file instagram-cookies.txt

# Required Termux packages. Do not hide failures: a broken package install
# should stop the update rather than leaving a half-working bot.
pkg update -y
pkg install -y python git ffmpeg

if [ ! -d .venv ]; then
  echo "Creating Python virtual environment..."
  python -m venv .venv
fi

. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-termux.txt --upgrade

# Verify the Python files before starting the bot.
python -m compileall -q bot.py media_downloader.py discord_formatter.py state_manager.py scrapers

echo ""
echo "Update complete. Starting bot..."
exec bash termux-start.sh
