# Real Rimera Hater Radio Bot

A Discord bot that watches Rimera-related shops and socials, then posts Discord embeds when it finds new updates. It can also turn public social-media links dropped into a configured Discord channel into downloadable video/photo attachments.

## What It Does

- Checks `rimerarimera.com` for new products and restocks.
- Posts product embeds with the product name, description, photo, price, stock status, and variant availability.
- Tracks configured social/music sources.
- Automatically downloads public media links with `yt-dlp` in a selected Discord channel and replies to the original message with the downloaded media.
- Handles Instagram posts, reels, Stories, photos, videos, and multi-media posts with dedicated fallbacks.
- Sends a multi-media result in one Discord reply when Discord allows it; excess items use a private fallback and are never zipped.
- Keeps a local `cache.json` so old posts/products are not repeatedly announced.
- Keeps secrets in `.env` and local cookie files rather than committing them.

## Python Version

Use Python 3.10 or newer.

## Setup

1. Clone the repo:

```bash
git clone https://github.com/therealmangoosey/REAL-RIMERA-HATER-RADIO.git
cd REAL-RIMERA-HATER-RADIO
```

2. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. Create `.env`:

```env
DISCORD_TOKEN=your_actual_discord_bot_token_here
WEBSHARE_PROXY_USERNAME=
WEBSHARE_PROXY_PASSWORD=
WEBSHARE_PROXY_HOSTS=
YT_DLP_COOKIES_FILE=/absolute/path/to/instagram-cookies.txt
```

The proxy variables and cookies path are optional. Never commit `.env` or an Instagram cookies file.

## Termux

Install the packages:

```bash
pkg update && pkg upgrade
pkg install python git ffmpeg curl
```

For a new Termux checkout, use `termux-start.sh` after creating `.env`.

```bash
bash termux-start.sh
```

## Updating The Bot

For an existing Termux installation, **do not run `git pull` first**. The updater is designed to recover from local changes safely.

```bash
cd ~/REAL-RIMERA-HATER-RADIO && curl -fsSL https://raw.githubusercontent.com/therealmangoosey/REAL-RIMERA-HATER-RADIO/main/update-termux.sh | bash
```

The updater backs up `.env`, `config.json`, `cache.json`, and `instagram-cookies.txt`, stashes other local changes, fetches the latest `main`, resets the code, restores runtime files, updates dependencies, compiles the Python files, runs the unit tests, and only starts the bot when those checks pass.

## Media Downloader

An administrator enables the downloader with:

```text
/set-media-channel channel:#downloads
```

After that, a message containing a public media URL can be dropped into the configured channel. The bot downloads it and replies directly to the original message.

The downloader uses the best available video/audio formats it can access and FFmpeg when available. It does not create ZIP files.

### Instagram

Instagram handling is split by media type because yt-dlp can fail on image-only posts and image-only carousels with `No video formats found` even when the public post itself is accessible.

For **public posts, photos, reels, and carousels**, the order is:

1. `yt-dlp` anonymous attempt.
2. `parth-dl` 1.2.1 as the dedicated no-login/no-API fallback for public posts, photos, mixed carousels, and reels.
3. Optional authenticated Instagram cookies as the final fallback.

For **public Stories**, the order is:

1. `yt-dlp` anonymous attempt.
2. SMDownloader's public structured resolver (`/api/extract`).
3. A small set of public Story page fallbacks that only accept explicit media/download links.
4. Optional authenticated Instagram cookies as the final fallback.

`parth-dl` is a separate lightweight Python package with no runtime dependencies. Its documented Python API returns a single file path or a list of paths for a carousel. citeturn623233view0

SMDownloader documents its `/api/extract` resolver for public Instagram posts, carousels and active Stories without requiring an Instagram login. citeturn701942search0turn775318search2

The fallback code validates actual media responses and file signatures. It rejects ordinary webpage images, logos, icons, store badges, screenshots, HTML pages, download buttons, and other site assets.

Public third-party services can change without notice. They only work for media the service can access publicly. Private/login-only/expired/DRM-protected content can still fail.

### Optional Instagram cookies

Cookies are never used on the first attempt. They are only a final fallback.

```bash
cd ~/REAL-RIMERA-HATER-RADIO
nano instagram-cookies.txt
```

Or configure:

```env
YT_DLP_COOKIES_FILE=/data/data/com.termux/files/home/REAL-RIMERA-HATER-RADIO/instagram-cookies.txt
```

Use Netscape/Mozilla cookies.txt format and never share the file.

## Slash Commands

- `/status` — bot status and configured channels.
- `/channels` — update channels.
- `/set-media-channel` — choose the automatic media-download channel.
- `/media-channel` — show the current media-download channel.
- `/check-products` — manually check the shop.
- `/check-socials` — manually check social/music sources.
- `/initial` — register for private early shop alerts.
- `/set-channel` plus the source-specific `/set-*-channel` commands configure update channels.

## Initial Alert Password

Fresh copies use:

```text
CHANGE_ME
```

Change `initial_password` in your local `config.json` before using `/initial`. The Termux updater preserves your local `config.json`, so it will not overwrite that value.

## Testing

Run:

```bash
python -m compileall -q bot.py media_downloader.py instagram_fallback.py discord_formatter.py state_manager.py scrapers
python -m unittest discover -v
```

GitHub Actions runs the same compile and unit-test checks on pushes and pull requests.

## Notes

- Enable Discord's **Message Content Intent** because the media downloader watches normal messages for URLs.
- TikTok profile monitoring uses an HTTP-first scraper; its Selenium fallback is optional and is not required by the media downloader.
- FFmpeg is strongly recommended for high-quality video merging and Discord-size handling.
- The bot limits concurrent media jobs so a burst of links does not overwhelm a small Termux device.
- Discord attachment limits still apply. The bot keeps the first batch together and sends overflow privately rather than creating a ZIP.
