import asyncio
import json
import logging
import os

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

from discord_formatter import DiscordFormatter
from keyword_reactions import reactions_enabled, react_to_message, set_reactions_enabled
from media_downloader import DISCORD_FREE_LIMIT, DISCORD_MAX_ATTACHMENTS, MediaDownloader, MediaDownloadError
from scrapers.social_scraper import SocialScraper
from scrapers.tiktok_scraper import TikTokScraper
from scrapers.twitter_scraper import TwitterScraper
from scrapers.website_scraper import WebsiteScraper
from state_manager import StateManager

try:
    from web_server import start_web_server
except ImportError:
    start_web_server = None

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s:%(levelname)s:%(name)s: %(message)s',
    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()]
)
logger = logging.getLogger('rimera-bot')

CONFIG_FILE = 'config.json'
SOURCE_LABELS = {
    'default': 'Default', 'website': 'Website', 'twitter': 'Twitter',
    'tiktok': 'TikTok', 'instagram': 'Instagram', 'spotify': 'Spotify',
    'apple_music': 'Apple Music', 'soundcloud': 'SoundCloud', 'youtube': 'YouTube',
    'tumblr': 'Tumblr',
}
SUPER_ADMIN_ID = 1300260018691637308


def is_admin_or_super_user():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id == SUPER_ADMIN_ID:
            return True
        return interaction.user.guild_permissions.administrator
    return app_commands.check(predicate)


SHOP_PUBLIC_DELAY_SECONDS = 120
DISCORD_REQUEST_LIMIT = 25 * 1024 * 1024


def load_config():
    with open(CONFIG_FILE, 'r') as f:
        loaded_config = json.load(f)
    loaded_config.setdefault('channels', {})
    if loaded_config.get('channel_id') and not loaded_config['channels'].get('default'):
        loaded_config['channels']['default'] = loaded_config['channel_id']
    loaded_config.setdefault('media_download_channel_id', None)
    loaded_config.setdefault('website_url', 'https://rimerarimera.com')
    loaded_config.setdefault('linktree_url', 'https://linktr.ee/rimerarimera')
    loaded_config.setdefault('instagram_url', 'https://instagram.com/rimeraera?igshid=YTM0ZjI4ZDI=')
    loaded_config.setdefault('spotify_url', 'https://open.spotify.com/artist/3HgzwrhMXuElbeBBWJ1d38?si=90d_vXIFSiCDkBjAGG0FyA')
    loaded_config.setdefault('apple_music_url', 'https://music.apple.com/gb/artist/rimera/1478454603')
    loaded_config.setdefault('soundcloud_url', 'https://soundcloud.app.goo.gl/HuhB6bRZBe9Qutt68')
    loaded_config.setdefault('youtube_url', 'https://youtube.com/channel/UCeliKm-RLwRJNWJLOhv3lNw')
    loaded_config.setdefault('youtube_channel_id', 'UCeliKm-RLwRJNWJLOhv3lNw')
    loaded_config.setdefault('tumblr_url', '')
    loaded_config.setdefault('initial_password', 'CHANGE_ME')
    loaded_config.setdefault('initial_subscribers', [])
    loaded_config.setdefault('reactions_enabled', True)
    return loaded_config


def save_config():
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)


config = load_config()
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')


class RimeraBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)
        self.state_manager = StateManager()
        self.twitter_scraper = TwitterScraper(
            config.get('twitter_handle', 'rimera'),
            config.get('nitter_instances', ["https://nitter.net"])
        )
        self.tiktok_scraper = TikTokScraper(config.get('tiktok_handle', 'rimera'))
        self.website_scraper = WebsiteScraper(config.get('website_url', 'https://rimerarimera.com'))
        self.social_scraper = SocialScraper(config)
        self.formatter = DiscordFormatter()
        self.media_downloader = MediaDownloader()
        self.media_download_semaphore = asyncio.Semaphore(2)

    async def setup_hook(self):
        logger.info("Setting up bot...")
        self.polling_loop.start()
        if start_web_server and config.get('enable_web_server', False):
            start_web_server(self, config.get('flask_port', 5000))

    async def on_ready(self):
        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        await self.change_presence(activity=discord.Game(name="rimera.vercel.app"))
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} command(s)")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")

    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        await react_to_message(message)
        channel_id = config.get('media_download_channel_id')
        if not channel_id or message.channel.id != int(channel_id):
            return
        urls = list(dict.fromkeys(self.media_downloader.extract_urls(message.content)))[:3]
        if not urls:
            return
        fetching_message = None
        try:
            fetching_message = await message.reply("Fetching…", mention_author=False)
        except discord.DiscordException as exc:
            logger.warning("Could not send fetching message: %s", exc)
        async with self.media_download_semaphore:
            await self.download_media_reply(message, urls, fetching_message)

    @app_commands.command(name="reactions", description="Turn automatic keyword emoji reactions on or off")
    @is_admin_or_super_user()
    @app_commands.describe(enabled="True to enable reactions, false to disable them")
    async def reactions(self, interaction: discord.Interaction, enabled: bool):
        if not set_reactions_enabled(enabled):
            await interaction.response.send_message("I couldn't save the reaction setting.", ephemeral=True)
            return
        state = "ON" if enabled else "OFF"
        await interaction.response.send_message(f"Automatic keyword reactions are now **{state}**.", ephemeral=True)

    @app_commands.command(name="reaction_status", description="Show whether automatic keyword emoji reactions are enabled")
    @is_admin_or_super_user()
    async def reaction_status(self, interaction: discord.Interaction):
        state = "ON" if reactions_enabled() else "OFF"
        await interaction.response.send_message(f"Automatic keyword reactions are **{state}**.", ephemeral=True)

    @staticmethod
    def _make_discord_files(paths):
        return [discord.File(path, filename=os.path.basename(path)) for path in paths]

    @staticmethod
    def _chunk_paths(paths):
        """Split attachments by Discord's attachment count and 25 MiB request limit."""
        chunks = []
        current = []
        current_bytes = 0
        for path in paths:
            size = os.path.getsize(path)
            if current and (len(current) >= DISCORD_MAX_ATTACHMENTS or current_bytes + size > DISCORD_REQUEST_LIMIT - 256 * 1024):
                chunks.append(current)
                current = []
                current_bytes = 0
            current.append(path)
            current_bytes += size
        if current:
            chunks.append(current)
        return chunks

    async def _send_public_batch(self, reply_to, paths, content=None):
        """Send one public batch as a reply to the previous message; return the sent message."""
        if not paths:
            return reply_to
        try:
            return await reply_to.reply(
                content=content,
                files=self._make_discord_files(paths),
                mention_author=False,
            )
        except discord.HTTPException as exc:
            if exc.status != 413 or len(paths) <= 1:
                raise

        midpoint = max(1, len(paths) // 2)
        first_message = await self._send_public_batch(reply_to, paths[:midpoint], content)
        return await self._send_public_batch(first_message, paths[midpoint:], None)

    async def download_media_reply(self, message, urls, fetching_message=None):
        prepared_paths = []
        workdirs = []
        failed = []
        compression_notes = {}
        try:
            for url in urls:
                try:
                    workdir, files = self.media_downloader.download_url(url)
                    workdirs.append(workdir)
                    prepared_paths.extend(files)
                except MediaDownloadError as exc:
                    failed.append((url, str(exc)))
                except Exception as exc:
                    logger.exception("Download failed for %s", url)
                    failed.append((url, f"Unexpected error: {exc}"))
            if prepared_paths:
                batches = self._chunk_paths(prepared_paths)
                first = True
                for batch in batches:
                    content = None
                    if first:
                        content = "\n".join(f"Failed: {url} ({reason})" for url, reason in failed) or None
                    await self._send_public_batch(message, batch, content)
                    first = False
            elif failed:
                await message.reply("\n".join(f"Failed: {url} ({reason})" for url, reason in failed), mention_author=False)
        finally:
            for path in prepared_paths:
                try:
                    os.remove(path)
                except OSError:
                    pass
            for workdir in workdirs:
                try:
                    os.rmdir(workdir)
                except OSError:
                    pass
            if fetching_message:
                try:
                    await fetching_message.delete()
                except discord.DiscordException:
                    pass

    @tasks.loop(minutes=5)
    async def polling_loop(self):
        try:
            await self.run_polling_cycle()
        except Exception:
            logger.exception("Polling cycle failed")

    @polling_loop.before_loop
    async def before_polling_loop(self):
        await self.wait_until_ready()

    async def run_polling_cycle(self):
        channels = config.get('channels', {})
        if not channels:
            return
        for name, channel_id in channels.items():
            try:
                channel = self.get_channel(int(channel_id))
                if channel is None:
                    continue
                items = []
                if name == 'website':
                    items = self.website_scraper.fetch_new()
                elif name == 'twitter':
                    items = self.twitter_scraper.fetch_new()
                elif name == 'tiktok':
                    items = self.tiktok_scraper.fetch_new()
                elif name == 'instagram':
                    items = self.social_scraper.fetch_instagram_new()
                elif name == 'spotify':
                    items = self.social_scraper.fetch_spotify_new()
                elif name == 'apple_music':
                    items = self.social_scraper.fetch_apple_music_new()
                elif name == 'soundcloud':
                    items = self.social_scraper.fetch_soundcloud_new()
                elif name == 'youtube':
                    items = self.social_scraper.fetch_youtube_new()
                elif name == 'tumblr':
                    items = self.social_scraper.fetch_tumblr_new()
                else:
                    items = self.website_scraper.fetch_new()
                for item in items:
                    await self.send_update(channel, item, name)
            except Exception:
                logger.exception(f"Error polling {name}")

    async def send_update(self, channel, item, source):
        title = item.get('title') or item.get('text') or 'New update'
        content = item.get('content') or item.get('description') or ''
        url = item.get('url') or ''
        embed = discord.Embed(title=title[:256], description=content[:4096], url=url or discord.Embed.Empty)
        embed.set_footer(text=f"Source: {SOURCE_LABELS.get(source, source)}")
        await channel.send(embed=embed)


bot = RimeraBot()

if __name__ == '__main__':
    if not TOKEN:
        raise RuntimeError('DISCORD_TOKEN is not set')
    bot.run(TOKEN)
