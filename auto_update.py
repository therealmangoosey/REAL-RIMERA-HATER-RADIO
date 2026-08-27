"""Run the bot and periodically restart it when origin/main changes.

Designed for a local/Termux checkout. GitHub is contacted only once every
15 minutes, so this does not hammer the API or restart unnecessarily.
"""

import subprocess
import sys
import time
from pathlib import Path

CHECK_INTERVAL_SECONDS = 15 * 60
BRANCH = "main"
ROOT = Path(__file__).resolve().parent


def run_git(*args):
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
        check=False,
    )


def is_clean():
    result = run_git("status", "--porcelain")
    if result.returncode != 0:
        print(result.stdout, flush=True)
        return False
    if result.stdout.strip():
        print("[auto-update] Local changes detected; skipping update to avoid overwriting them.", flush=True)
        return False
    return True


def update_available():
    fetch = run_git("fetch", "origin", BRANCH, "--quiet")
    if fetch.returncode != 0:
        print(f"[auto-update] Git fetch failed: {fetch.stdout.strip()}", flush=True)
        return False

    result = run_git("rev-list", "HEAD..origin/" + BRANCH, "--count")
    if result.returncode != 0:
        print(f"[auto-update] Could not compare commits: {result.stdout.strip()}", flush=True)
        return False
    return result.stdout.strip() != "0"


def apply_update():
    pull = run_git("pull", "--ff-only", "origin", BRANCH)
    if pull.returncode != 0:
        print(f"[auto-update] Update failed; keeping current bot running:\n{pull.stdout}", flush=True)
        return False
    print("[auto-update] Update installed successfully. Restarting bot...", flush=True)
    return True


def start_bot():
    print("[auto-update] Starting run_bot.py", flush=True)
    return subprocess.Popen([sys.executable, "run_bot.py"], cwd=ROOT)


def stop_bot(process):
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main():
    bot = start_bot()
    try:
        while True:
            time.sleep(CHECK_INTERVAL_SECONDS)

            if not is_clean():
                continue

            print("[auto-update] Checking GitHub for updates...", flush=True)
            if not update_available():
                print("[auto-update] No update. Bot continues normally.", flush=True)
                continue

            print("[auto-update] New update found. Stopping bot before pulling...", flush=True)
            stop_bot(bot)
            apply_update()
            bot = start_bot()

            if bot.poll() is not None:
                print("[auto-update] Bot exited; supervisor will keep monitoring.", flush=True)

    except KeyboardInterrupt:
        print("[auto-update] Shutting down...", flush=True)
    finally:
        stop_bot(bot)


if __name__ == "__main__":
    main()
