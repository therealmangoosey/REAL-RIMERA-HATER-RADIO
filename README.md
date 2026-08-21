# Real Rimera Hater Radio Bot

A Discord bot that watches Rimera-related shops and socials, then posts clean Discord embeds when it finds new updates. It can also turn public social-media links dropped into a configured Discord channel into downloadable video/photo attachments.

## What It Does

- Checks `rimerarimera.com` for new products and restocks.
- Posts product embeds with the product name, description, photo, price, stock status, and variant availability.
- Tracks Rimera social/music links from the Linktree source of truth.
- Automatically downloads public media links with `yt-dlp` in a selected Discord channel and replies to the original message with the downloaded media.
- Instagram carousel posts and other multi-media Instagram URLs are downloaded as multiple media items where yt-dlp can access them.
- Instagram Story URLs are supported when the bot has an authenticated Instagram cookies file for an account allowed to view the Story.
- Sends a multi-media result in one Discord reply when Discord's attachment limit allows it; excess items use the bot's private fallback rather than being zipped.
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

2. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. Create `.env` and add your Discord token:

```env
DISCORD_TOKEN=your_actual_discord_bot_token_here
```

Do not commit `.env`.

## Termux

Install the packages:

```bash
pkg update && pkg upgrade
pkg install python git ffmpeg curl
```

Then use the repo's Termux startup/update scripts as described below.

## Updating The Bot

For an existing Termux installation, **do not run `git pull` first**. The updater is designed to handle local changes without overwriting your local runtime configuration.

Use:

```bash
cd ~/REAL-RIMERA-HATER-RADIO && curl -fsSL https://raw.githubusercontent.com/therealmangoosey/REAL-RIMERA-HATER-RADIO/main/update-termux.sh | bash
```

The updater backs up `.env`, `config.json`, `cache.json`, and `instagram-cookies.txt`, stashes other local changes, fetches the latest `main`, resets the code to that version, restores local runtime files, updates dependencies, compile-checks the bot, and starts it again.

## Media Downloader

An administrator enables the downloader with:

```text
/set-media-channel channel:#downloads
```

After that, a message such as:

```text
https://www.instagram.com/p/example/
```

or an Instagram Story URL can be dropped into the configured channel. The bot downloads the media and replies to that message.

The downloader uses the best available video/audio formats it can access and FFmpeg when available. It does not create ZIP files. Multiple media items from a single Instagram post are sent together in one reply when possible. Discord's attachment limit is handled with the bot's private fallback.

### Instagram Stories require authentication

The error:

```text
You need to log in to access this content.
```

is an Instagram access restriction, not a Discord bug. yt-dlp supports passing an authenticated cookies file with `--cookies`/its Python equivalent. citeturn0search0

Export a cookies file from a browser where you are already logged into Instagram. The cookies must be in Mozilla/Netscape cookies.txt format. yt-dlp documents this format and warns that cookies files contain sensitive authentication data. citeturn0search0

Put the file here on Termux:

```bash
cd ~/REAL-RIMERA-HATER-RADIO
nano instagram-cookies.txt
```

Paste the exported cookies into that file. **Never commit it or send it to anyone.** The repository ignores `instagram-cookies.txt` automatically.

The bot automatically detects `instagram-cookies.txt` in the repo, so you normally do not need to change `.env`.

Alternatively, set an explicit path:

```env
YT_DLP_COOKIES_FILE=/data/data/com.termux/files/home/REAL-RIMERA-HATER-RADIO/instagram-cookies.txt
```

If the Story is private, your Instagram account must actually be allowed to view it. Cookies cannot bypass Instagram's privacy controls.

### Important Instagram limitation

Instagram can change its login/anti-bot behavior, and yt-dlp's Instagram extractor can therefore stop working temporarily even with valid cookies. Current yt-dlp guidance recommends using a fresh authenticated browser session/cookies when login or anti-bot protection blocks extraction. citeturn0search0

## Slash Commands

- `/status` — bot status and configured channels.
- `/channels` — update channels.
- `/set-media-channel` — choose the automatic media-download channel.
- `/media-channel` — show the current media-download channel.
- `/check-products` — manually check the shop.
- `/check-socials` — manually check social/music sources.
- `/initial` — register for private early shop alerts.
- `/set-channel` and the source-specific `/set-*-channel` commands configure update channels.

## Running

```bash
python bot.py
```

For Termux, use the included startup script so the environment and dependencies are prepared automatically.

## Notes

- Enable Discord's **Message Content Intent** because the media downloader watches normal messages for URLs.
- TikTok browser-dependent checking is optional on Termux; the main media downloader does not require Selenium.
- FFmpeg is strongly recommended for high-quality video merging and Discord-size handling.
- Private/login-only/expired/DRM-protected media can still fail.
