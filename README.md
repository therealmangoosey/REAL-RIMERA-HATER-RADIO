# Real Rimera Hater Radio Bot

A Discord bot that watches Rimera-related shops and socials, then posts clean Discord embeds when it finds new updates. It can also turn public social-media links dropped into a configured Discord channel into downloadable video/photo attachments.

## What It Does

- Checks `rimerarimera.com` for new products and restocks.
- Posts product embeds with the product name, description, photo, price, stock status, and variant availability.
- Tracks Rimera social/music links from the Linktree source of truth:
  - Instagram
  - Spotify
  - Apple Music
  - SoundCloud
  - YouTube
  - Twitter/X through Nitter instances
  - TikTok through Selenium
- Lets server admins choose separate Discord channels for each update type.
- Lets approved users register for private early shop alerts before the public shop channel post.
- Automatically downloads public media links with `yt-dlp` in a selected Discord channel and replies to the original message with the downloaded video/photo.
- Keeps a local `cache.json` so old posts/products are not repeatedly announced.
- Requires the Discord token to be stored in `.env`, not `config.json`.

## Python Version

Use Python 3.10 or newer.

Python 3.10 through 3.14 are supported by the current dependency set.

## Setup

1. Clone the repo:

```powershell
git clone https://github.com/therealmangoosey/REAL-RIMERA-HATER-RADIO.git
cd REAL-RIMERA-HATER-RADIO
```

2. Create a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

3. Install dependencies:

```powershell
pip install -r requirements.txt
```

4. Create your `.env` file:

```powershell
Copy-Item .env.example .env
```

5. Open `.env` and put your bot token in it:

```env
DISCORD_TOKEN=your_actual_discord_bot_token_here
```

Do not commit `.env`. It is ignored by `.gitignore`.

## Media Downloader Requirements

The automatic media downloader uses `yt-dlp`, which supports a very large number of video and social-media sites. Instagram and TikTok are supported when the public post is accessible, but private/login-only posts can still fail. Supported sites can change as platforms change their websites.

`ffmpeg` is strongly recommended. It lets the bot merge separate high-quality video/audio streams and compress files that are too large for Discord's current free upload limit.

On Windows, install FFmpeg and make sure `ffmpeg` is available in PATH. On Debian/Ubuntu:

```bash
sudo apt update
sudo apt install ffmpeg
```

## Discord Bot Permissions

In the Discord Developer Portal, make sure the bot has:

- `bot`
- `applications.commands`

Recommended bot permissions:

- View Channel
- Send Messages
- Attach Files
- Embed Links
- Read Message History
- Use Slash Commands

The bot also needs the **Message Content Intent** enabled in the Developer Portal because the media downloader watches normal messages for links.

For the configured media-download channel, make sure the bot can view the channel, read message history, send messages, and attach files.

## Running The Bot

From the repo folder, with the virtual environment active:

```powershell
python bot.py
```

On startup, the bot syncs slash commands and starts the polling loop.

## Updating The Bot

This is the normal update process. **Do not delete `config.json` or `.env`.**

1. Stop the running bot.
2. Open the repo folder.
3. Pull the newest code:

```powershell
git pull origin main
```

4. Update Python dependencies:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt --upgrade
```

5. Check the code compiles:

```powershell
python -m compileall bot.py media_downloader.py discord_formatter.py state_manager.py scrapers
```

6. Start the bot again:

```powershell
python bot.py
```

### If you are updating on Linux

```bash
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt --upgrade
python -m compileall bot.py media_downloader.py discord_formatter.py state_manager.py scrapers
python bot.py
```

### Updating only yt-dlp

`yt-dlp` is deliberately kept current because social platforms frequently change how their pages work. Run:

```powershell
pip install -U yt-dlp
```

Then restart the bot.

## Configuration

Most settings live in `config.json`.

Important fields:

- `polling_interval_minutes`: how often the bot checks for updates.
- `linktree_url`: the Linktree used as the source of truth for Rimera social/music links.
- `website_url`: the Rimera shop URL.
- `channels`: Discord channel IDs for each source.
- `media_download_channel_id`: the Discord channel where the bot watches normal messages for media links. Use `/set-media-channel` instead of editing this by hand.
- `twitter_handle`: Twitter/X handle to check through Nitter.
- `tiktok_handle`: TikTok handle to check.
- `instagram_url`: Instagram profile to check.
- `spotify_url`: Spotify artist/profile/release URL to check.
- `apple_music_url`: Apple Music artist URL to check.
- `soundcloud_url`: SoundCloud URL to check.
- `youtube_url` or `youtube_channel_id`: YouTube channel to check.
- `initial_password`: password required for `/initial`.
- `initial_subscribers`: user IDs that receive private early shop alerts.

You can set normal update channel IDs through slash commands, so you usually do not need to edit them by hand.

## Automatic Media Downloader

The media downloader is intentionally channel-based so it does not try to download every link across the server.

### Turn it on

An administrator runs:

```text
/set-media-channel channel:#media-downloads
```

After that, any normal message in that channel containing a public video/photo URL is checked automatically.

Example:

```text
https://www.tiktok.com/@example/video/123456789
```

The bot downloads the best available media it can access and replies directly to that message with the attachment.

It can process up to 3 links from one message and up to 10 attachments from a download result.

Use `/media-channel` to see the current channel.

### Quality and speed

- Video uses the best available video + audio formats and merges them when FFmpeg is available.
- The downloader uses a small retry count and concurrent fragment downloads for quicker downloads without blocking the Discord event loop.
- Downloads run in worker threads and are limited to two concurrent download jobs so a burst of links does not overwhelm the bot host.
- If a file is larger than Discord's upload limit, the bot attempts an FFmpeg compression pass before giving up.
- Private, login-only, expired, DRM-protected, or currently unsupported posts may still fail.
- The bot does not store downloaded media permanently. Temporary files are removed after the reply is sent.

## Slash Commands

General:

- `/status` shows bot status, monitored URLs, polling interval, configured channels, and the media downloader channel.
- `/channels` shows where each update type is posted.
- `/media-channel` shows the automatic media-download channel.
- `/invite` gives the bot invite link.
- `/donate` gives the bot support link.
- `/check-products` immediately checks `rimerarimera.com`.
- `/check-socials` immediately checks the Linktree-listed social/music pages.
- `/initial` registers a user for private early shop alerts.

Media downloader setup:

- `/set-media-channel` selects the channel where normal social-media links are automatically downloaded.

Channel setup:

- `/set-channel` sets the default update channel.
- `/set-website-channel` sets the product/restock channel.
- `/set-shop-channel` also sets the product/restock channel.
- `/set-twitter-channel` sets the Twitter/X channel.
- `/set-tiktok-channel` sets the TikTok channel.
- `/set-instagram-channel` sets the Instagram channel.
- `/set-spotify-channel` sets the Spotify channel.
- `/set-apple-music-channel` sets the Apple Music channel.
- `/set-soundcloud-channel` sets the SoundCloud channel.
- `/set-youtube-channel` sets the YouTube channel.

Administrator permission is required for setup and manual check commands.

The `/initial` command does not require admin permission. The current password is:

```text
Phone118
```

## How Updates Work

The first time the bot sees a source, it saves the current items to `cache.json` without posting them. After that:

- New products are announced.
- Products that change from sold out to in stock are announced as restocks.
- Users who registered with `/initial` get a private early shop alert immediately.
- The configured website/shop update channel gets the same shop update 2 minutes later (manual `/check-products` posts immediately).
- New feed items from YouTube are announced.
- Instagram, Spotify, Apple Music, and SoundCloud are checked for visible public metadata/page changes.
- Twitter/X and TikTok are checked for newly discovered posts/videos.
- The media downloader only watches the channel configured with `/set-media-channel`.

## Testing

Run the test suite:

```powershell
python -m unittest discover -v
```

Run a compile check:

```powershell
python -m compileall bot.py media_downloader.py discord_formatter.py state_manager.py scrapers
```

## Notes

- TikTok checking uses Selenium and ChromeDriver. If those dependencies are missing or ChromeDriver cannot run, the bot logs the TikTok error and continues checking the other sources.
- Twitter/X checking uses public Nitter instances, which can be unreliable. Add or change instances in `config.json` if needed.
- `cache.json`, `bot.log`, and temporary downloader files are local runtime data and should not be committed.
- The downloader uses public URLs only. A platform can still require authentication or change its anti-bot system, in which case that particular link may fail.
