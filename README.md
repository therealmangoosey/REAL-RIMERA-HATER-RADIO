# Real Rimera Hater Radio Bot

A Discord bot that watches Rimera-related shops and socials, then posts clean Discord embeds when it finds new updates. It can also turn public social-media links dropped into a configured Discord channel into downloadable video/photo attachments.

## What It Does

- Checks `rimerarimera.com` for new products and restocks.
- Posts product embeds with the product name, description, photo, price, stock status, and variant availability.
- Tracks Rimera social/music links from the Linktree source of truth.
- Lets server admins choose separate Discord channels for each update type.
- Lets approved users register for private early shop alerts before the public shop channel post.
- Automatically downloads public media links with `yt-dlp` in a selected Discord channel.
- Supports Instagram multi-media posts/carousels and Instagram Story URLs when yt-dlp can access the media.
- Sends all successfully downloaded pieces from one post/story into the same Discord reply where Discord allows it. If there are more than Discord's attachment limit, the extra pieces are sent privately to the person who posted the link. **No ZIP files are created.**
- Keeps a local `cache.json` so old posts/products are not repeatedly announced.
- Requires the Discord token to be stored in `.env`, not `config.json`.

## Python Version

Use Python 3.10 or newer.

## Setup

1. Clone the repo:

```bash
git clone https://github.com/therealmangoosey/REAL-RIMERA-HATER-RADIO.git
cd REAL-RIMERA-HATER-RADIO
```

2. Create a virtual environment:

```bash
python -m venv .venv
```

3. Activate it and install the dependencies for your platform.

Linux/macOS:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

4. Create `.env` and add:

```env
DISCORD_TOKEN=your_actual_discord_bot_token_here
```

Do not commit `.env`. It is ignored by `.gitignore`.

## Termux / Android

The bot has a dedicated lightweight Termux dependency file and startup script. You do **not** need Selenium/Chrome just to run the bot on Termux.

Install Termux packages:

```bash
pkg update && pkg upgrade
pkg install python git ffmpeg
```

Clone the repo:

```bash
git clone https://github.com/therealmangoosey/REAL-RIMERA-HATER-RADIO.git
cd REAL-RIMERA-HATER-RADIO
```

Create `.env`:

```bash
nano .env
```

Put your token in it:

```env
DISCORD_TOKEN=your_actual_discord_bot_token_here
```

Start the bot:

```bash
bash termux-start.sh
```

The script creates `.venv`, installs `requirements-termux.txt`, checks FFmpeg, enables a wake lock when available, and starts `bot.py`.

### One-command Termux update

From the repo directory, use:

```bash
bash update-termux.sh
```

That updater backs up `.env`, `config.json`, `cache.json`, and `instagram-cookies.txt`, syncs the working tree to the latest `origin/main`, restores those local files, updates Termux Python dependencies, compiles the bot to catch syntax errors, and starts it again.

**Do not use `git reset --hard origin/main` manually** if you need to preserve your local `.env` or `config.json`; use `bash update-termux.sh` instead.

### Keep Termux running

Android may kill long-running background processes. For the most reliable setup:

- disable battery optimisation for Termux in Android settings;
- keep Termux awake while the bot is running;
- keep the device powered if this is being used as a 24/7 bot host.

The included `termux-start.sh` uses `termux-wake-lock` when it is available.

## Media Downloader Requirements

The automatic media downloader uses `yt-dlp`, which supports a large number of video and social-media sites. Instagram and TikTok are supported when the post/story is accessible to the downloader. Private, login-only, expired, DRM-protected, or currently unsupported media can still fail.

FFmpeg is strongly recommended and is installed on Termux with:

```bash
pkg install ffmpeg
```

It lets the bot merge separate high-quality video/audio streams and compress files that are too large for Discord's upload limit.

### Instagram Story access

Instagram Stories are often login-gated. To let the bot use an authorized Instagram session, set an optional yt-dlp cookies file in `.env`:

```env
YT_DLP_COOKIES_FILE=/absolute/path/to/instagram-cookies.txt
```

The cookies file must belong to an account that is authorized to view the requested Story. Do not commit or publicly share that file.

On Termux, a cookies file in the repo can be referenced with an absolute path such as:

```env
YT_DLP_COOKIES_FILE=/data/data/com.termux/files/home/REAL-RIMERA-HATER-RADIO/instagram-cookies.txt
```

## Discord Bot Permissions

In the Discord Developer Portal, make sure the bot has:

- `bot`
- `applications.commands`

Recommended permissions:

- View Channel
- Send Messages
- Attach Files
- Embed Links
- Read Message History
- Use Slash Commands

The bot also needs the **Message Content Intent** enabled because the media downloader watches normal messages for links.

## Running The Bot

Normal Linux/Windows:

```bash
python bot.py
```

Termux:

```bash
bash termux-start.sh
```

## Updating The Bot

Do not delete `config.json` or `.env`.

Termux safest update:

```bash
cd ~/REAL-RIMERA-HATER-RADIO
bash update-termux.sh
```

Linux/macOS:

```bash
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt --upgrade
python -m compileall bot.py media_downloader.py discord_formatter.py state_manager.py scrapers
python bot.py
```

Windows PowerShell uses `.\.venv\Scripts\Activate.ps1` instead of `source .venv/bin/activate`.

## Configuration

Most settings live in `config.json`.

Important fields include:

- `polling_interval_minutes`: how often the bot checks for updates.
- `linktree_url`: Linktree source of truth.
- `website_url`: Rimera shop URL.
- `channels`: Discord channel IDs.
- `media_download_channel_id`: channel watched for automatic media downloads. Use `/set-media-channel`.
- social/music URLs and handles.
- `initial_password` and `initial_subscribers` for early shop alerts.

## Automatic Media Downloader

The downloader is intentionally channel-based.

An administrator runs:

```text
/set-media-channel channel:#media-downloads
```

Then a message such as:

```text
https://www.instagram.com/p/example/
```

or:

```text
https://www.instagram.com/stories/example/123456789/
```

is automatically processed.

### Instagram posts, carousels and Stories

Instagram links are handled as multi-item downloads. For a carousel, the downloader attempts to retrieve every photo/video item rather than only the first one. Story URLs are passed through the same multi-item handling.

All successfully downloaded pieces from one source are sent in **one Discord reply** where possible. Discord's per-message attachment limit is respected. If the source produces more attachments than Discord permits in one message, the remaining files are sent **privately to the person who posted the link**. The bot does **not** create ZIP files.

### Quality and speed

- Uses the best available video + audio formats and merges them when FFmpeg is available.
- Instagram carousel/story extraction is enabled without expanding ordinary links into unrelated playlists.
- Uses retries and concurrent fragment downloads.
- Downloads run in worker threads and are limited to two concurrent download jobs.
- If an individual file is larger than Discord's upload limit, the bot attempts an FFmpeg compression pass.
- Temporary downloaded media is removed after sending.

## Slash Commands

- `/status` shows bot status and configured channels.
- `/channels` shows update channels.
- `/media-channel` shows the media-download channel.
- `/set-media-channel` selects it.
- `/check-products` manually checks the shop.
- `/check-socials` manually checks socials.
- `/initial` registers for private early shop alerts.
- `/invite` gives the bot invite link.
- `/donate` gives the support link.

Channel setup commands include `/set-channel`, `/set-website-channel`, `/set-shop-channel`, `/set-twitter-channel`, `/set-tiktok-channel`, `/set-instagram-channel`, `/set-spotify-channel`, `/set-apple-music-channel`, `/set-soundcloud-channel`, and `/set-youtube-channel`.

Administrator permission is required for setup and manual check commands.

## Testing

Run:

```bash
python -m unittest discover -v
python -m compileall bot.py media_downloader.py discord_formatter.py state_manager.py scrapers
```

The Termux updater runs the compile check automatically before starting the bot.

## Notes

- TikTok's optional Selenium fallback is not installed in the lightweight Termux dependency set. The HTTP scraper still runs, and the rest of the bot continues if browser scraping is unavailable.
- Twitter/X checking uses public Nitter instances and can be unreliable.
- `cache.json`, `bot.log`, temporary downloader files, and Instagram cookie files should not be committed.
- The downloader does not bypass platform privacy controls.
