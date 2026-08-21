#!/data/data/com.termux/files/usr/bin/bash
set -e

cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "ERROR: .env is missing. Create it with:"
  echo 'DISCORD_TOKEN=your_bot_token'
  exit 1
fi

if ! command -v python >/dev/null 2>&1; then
  echo "ERROR: Python is not installed. Run: pkg install python"
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "WARNING: FFmpeg is not installed. Large videos may not be compressible for Discord."
  echo "Install it with: pkg install ffmpeg"
fi

if [ ! -d .venv ]; then
  echo "Creating Termux virtual environment..."
  python -m venv .venv
fi

. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-termux.txt

# Keep Android/Termux awake while the bot is running when termux-api is installed.
if command -v termux-wake-lock >/dev/null 2>&1; then
  termux-wake-lock || true
fi

cleanup() {
  if command -v termux-wake-unlock >/dev/null 2>&1; then
    termux-wake-unlock || true
  fi
}
trap cleanup EXIT INT TERM

echo "Starting Rimera Hater Radio in Termux..."
exec python bot.py
