# Real Rimera Hater Radio Bot

A Discord bot that watches Rimera-related shops and socials, then posts clean Discord embeds when it finds new updates.

## What It Does

- Checks `rimerarimera.com` for new products and restocks.
- Posts product embeds with the product name, description, photo, price, stock status, and variant availability.
- Tracks Rimera social/music links from `https://linktr.ee/rimerarimera` for visible changes or new feed items:
  - Instagram
  - Spotify
  - Apple Music
  - SoundCloud
  - YouTube
  - Twitter/X through Nitter instances
  - TikTok through Selenium
- Lets server admins choose separate Discord channels for each update type.
- Lets approved users register for private early shop alerts before the public shop channel post.
- Keeps a local `cache.json` so old posts/products are not repeatedly announced.
- Requires the Discord token to be stored in `.env`, not `config.json`.

## Python Version

Use Python 3.10 or newer.

This bot was checked locally with Python 3.14.3, but Python 3.10+ is the intended supported range for the current dependencies.

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

## Discord Bot Permissions

In the Discord Developer Portal, make sure the bot has:

- `bot`
- `applications.commands`

Recommended bot permissions:

- Send Messages
- Embed Links
- Read Message History
- Use Slash Commands

If you use channel-specific permissions, make sure the bot can send messages and embeds in every configured update channel.

## Running The Bot

From the repo folder, with the virtual environment active:

```powershell
python bot.py
```

On startup, the bot syncs slash commands and starts the polling loop.

## Configuration

Most settings live in `config.json`.

Important fields:

- `polling_interval_minutes`: how often the bot checks for updates.
- `linktree_url`: the Linktree used as the source of truth for Rimera social/music links.
- `website_url`: the Rimera shop URL.
- `channels`: Discord channel IDs for each source.
- `twitter_handle`: Twitter/X handle to check through Nitter.
- `tiktok_handle`: TikTok handle to check.
- `instagram_url`: Instagram profile to check.
- `spotify_url`: Spotify artist/profile/release URL to check.
- `apple_music_url`: Apple Music artist URL to check.
- `soundcloud_url`: SoundCloud URL to check.
- `youtube_url` or `youtube_channel_id`: YouTube channel to check.
- `initial_password`: password required for `/initial`.
- `initial_subscribers`: user IDs that receive private early shop alerts.

You can set channel IDs through slash commands, so you usually do not need to edit them by hand. Social/music URLs come from the Linktree defaults in `config.json`.

## Slash Commands

General:

- `/status` shows bot status, monitored URLs, polling interval, and configured channels.
- `/channels` shows where each update type is posted.
- `/check-products` immediately checks `rimerarimera.com`.
- `/check-socials` immediately checks the Linktree-listed social/music pages.
- `/initial` registers a user for private early shop alerts when they enter the correct password.

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

Admin permission is required for setup and manual check commands.

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

## Testing

Run the test suite:

```powershell
python -m unittest discover -v
```

Run a compile check:

```powershell
python -m compileall bot.py discord_formatter.py state_manager.py scrapers
```

## Notes

- TikTok checking uses Selenium and ChromeDriver. If those dependencies are missing or ChromeDriver cannot run, the bot logs the TikTok error and continues checking the other sources.
- Twitter/X checking uses public Nitter instances, which can be unreliable. Add or change instances in `config.json` if needed.
- `cache.json` and `bot.log` are local runtime files and are ignored by Git.
