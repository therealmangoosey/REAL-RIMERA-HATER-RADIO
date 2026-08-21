import asyncio
import json
import logging
import os

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

from discord_formatter import DiscordFormatter
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
SHOP_PUBLIC_DELAY_SECONDS = 120


def is_admin_or_super_user():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id == SUPER_ADMIN_ID:
            return True
        return interaction.user.guild_permissions.administrator
    return app_commands.check(predicate)


def load_config():
    with open(CONFIG_FILE, 'r') as f:
        loaded_config = json.load(f)
    loaded_config.setdefault('channels', {})
    if loaded_config.get('channel_id') and not loaded_config['channels'].get('default'):
        loaded_config['channels']['default'] = loaded_config['channel_id']
    loaded_config.setdefault('media_download_channel_id', None)
    loaded_config.setdefault('website_url', 'https://rimerarimera.com')
    loaded_config.setdefault('linktree_url', 'https://linktr.ee/rimerarimera')
    loaded_config.setdefault('instagram_url', 'https://instagram.com/rimeraera')
    loaded_config.setdefault('spotify_url', '')
    loaded_config.setdefault('apple_music_url', '')
    loaded_config.setdefault('soundcloud_url', '')
    loaded_config.setdefault('youtube_url', '')
    loaded_config.setdefault('youtube_channel_id', '')
    loaded_config.setdefault('initial_password', 'CHANGE_ME')
    loaded_config.setdefault('initial_subscribers', [])
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
        channel_id = config.get('media_download_channel_id')
        if not channel_id or message.channel.id != int(channel_id):
            return
        urls = list(dict.fromkeys(self.media_downloader.extract_urls(message.content)))[:3]
        if not urls:
            return
        async with self.media_download_semaphore:
            await self.download_media_reply(message, urls)

    @staticmethod
    def _make_discord_files(paths):
        return [discord.File(path, filename=os.path.basename(path)) for path in paths]

    async def _send_private_media(self, user, path, message_text, fallback_limit=10_000_000):
        """Send one file per DM, adapting to Discord's effective upload limit."""
        candidates = [path]
        compressed = await asyncio.to_thread(
            self.media_downloader.fit_for_discord,
            path,
            DISCORD_FREE_LIMIT,
        )
        if compressed and compressed != path:
            candidates.insert(0, compressed)

        last_error = None
        for candidate in candidates:
            try:
                await user.send(
                    content=message_text,
                    file=discord.File(candidate, filename=os.path.basename(candidate)),
                )
                return True
            except discord.HTTPException as exc:
                last_error = exc
                if exc.status != 413:
                    break

        # Some accounts/contexts can still enforce the older 10 MB ceiling.
        compressed_10mb = await asyncio.to_thread(
            self.media_downloader.fit_for_discord,
            path,
            fallback_limit,
        )
        if compressed_10mb:
            try:
                await user.send(
                    content=f"{message_text} I used the stricter 10 MB limit after Discord rejected the first upload.",
                    file=discord.File(compressed_10mb, filename=os.path.basename(compressed_10mb)),
                )
                return True
            except discord.HTTPException as exc:
                last_error = exc

        logger.warning("Could not privately send %s: %s", path, last_error)
        return False

    async def download_media_reply(self, message, urls):
        prepared_paths = []
        workdirs = []
        failed = []
        oversized = []
        try:
            for url in urls:
                try:
                    workdir, downloaded, _ = await asyncio.to_thread(self.media_downloader.download, url)
                    workdirs.append(workdir)
                    for path in downloaded:
                        if os.path.getsize(path) > self.media_downloader.max_bytes:
                            oversized.append((path, url))
                            continue
                        prepared_paths.append(path)
                except MediaDownloadError as exc:
                    logger.warning(f"Could not download {url}: {exc}")
                    failed.append(url)
                except Exception as exc:
                    logger.exception(f"Unexpected media download error for {url}: {exc}")
                    failed.append(url)

            compressed_paths = []
            for path, url in oversized:
                fitted = await asyncio.to_thread(self.media_downloader.fit_for_discord, path)
                if fitted:
                    compressed_paths.append((fitted, url, path))
                else:
                    failed.append(url)

            all_ready = prepared_paths + [item[0] for item in compressed_paths]
            if not all_ready:
                if failed:
                    await message.reply(
                        "I couldn't download that link. It may be private, unsupported, unavailable, or too large for Discord.",
                        mention_author=False,
                    )
                return

            # Keep the normal media result together up to Discord's attachment count.
            # Oversized files are deliberately sent separately so a single 413 cannot
            # invalidate the rest of the batch.
            normal_paths = [path for path in prepared_paths]
            public_paths = normal_paths[:DISCORD_MAX_ATTACHMENTS]
            remaining_paths = normal_paths[DISCORD_MAX_ATTACHMENTS:]

            text_parts = []
            if failed:
                text_parts.append("Some links/media items could not be downloaded, but I got the rest.")
            if public_paths:
                await message.reply(
                    content=" ".join(text_parts) or None,
                    files=self._make_discord_files(public_paths),
                    mention_author=False,
                )
            elif text_parts:
                await message.reply(content=" ".join(text_parts), mention_author=False)

            # Any normal overflow is sent one message at a time too.
            for path in remaining_paths:
                try:
                    await message.author.send(
                        content="Extra media from your download request:",
                        file=discord.File(path, filename=os.path.basename(path)),
                    )
                except discord.HTTPException as exc:
                    logger.warning("Could not privately send overflow file %s: %s", path, exc)

            # Every file that originally exceeded Discord's configured limit gets its
            # own message and a precise explanation of why it was recompressed.
            for fitted, url, original in compressed_paths:
                original_size = os.path.getsize(original)
                compressed_size = os.path.getsize(fitted)
                limit_mb = self.media_downloader.max_bytes / 1_000_000
                note = (
                    f"Compressed this file to {compressed_size / 1_000_000:.2f} MB "
                    f"to fit Discord's {limit_mb:.0f} MB upload limit while preserving as much quality as possible."
                )
                sent = await self._send_private_media(message.author, fitted, note)
                if not sent:
                    logger.warning("Oversized media could not be privately delivered: %s (original %.2f MB)", url, original_size / 1_000_000)

        finally:
            for workdir in workdirs:
                self.media_downloader.cleanup(workdir)

    def channel_id_for(self, source_key):
        channels = config.setdefault('channels', {})
        return channels.get(source_key) or channels.get('default') or config.get('channel_id')

    def configured_channel_mentions(self):
        rows = []
        for key, label in SOURCE_LABELS.items():
            channel_id = self.channel_id_for(key)
            channel = None
            if channel_id:
                try:
                    channel = self.get_channel(int(channel_id))
                except (ValueError, TypeError):
                    pass
            value = channel.mention if channel else (f"`{channel_id}`" if channel_id else "Not set")
            rows.append(f"{label}: {value}")
        return "\n".join(rows)

    async def send_item_update(self, source_key, item):
        channel_id = self.channel_id_for(source_key)
        if not channel_id:
            logger.warning(f"No channel configured for {source_key}; skipping notification.")
            return False
        try:
            channel = self.get_channel(int(channel_id)) or await self.fetch_channel(int(channel_id))
        except (ValueError, TypeError, discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
            logger.error(f"Error retrieving channel {channel_id} for {source_key}: {e}")
            return False
        if not channel:
            return False
        try:
            await channel.send(embed=self.formatter.format_item(item))
            return True
        except discord.DiscordException as e:
            logger.error(f"Could not send {source_key} update to channel {channel_id}: {e}")
            return False

    async def send_early_shop_update(self, item):
        subscriber_ids = config.get('initial_subscribers', [])
        if not subscriber_ids:
            logger.info("No /initial subscribers configured for early shop update.")
            return 0
        sent_count = 0
        embed = self.formatter.format_item(item)
        for user_id in subscriber_ids:
            try:
                user = self.get_user(int(user_id)) or await self.fetch_user(int(user_id))
                await user.send(content=f"<@{user_id}> early shop update:", embed=embed)
                sent_count += 1
            except discord.DiscordException as e:
                logger.error(f"Could not send early shop update to user {user_id}: {e}")
        return sent_count

    async def send_delayed_shop_channel_update(self, item):
        await asyncio.sleep(SHOP_PUBLIC_DELAY_SECONDS)
        await self.send_item_update('website', item)

    async def handle_shop_update(self, item):
        early_count = await self.send_early_shop_update(item)
        logger.info(f"Sent early shop update to {early_count} subscriber(s).")
        asyncio.create_task(self.send_delayed_shop_channel_update(item))

    @tasks.loop(minutes=config.get('polling_interval_minutes', 5))
    async def polling_loop(self):
        logger.info("Starting polling cycle...")
        await self.poll_twitter()
        await self.poll_tiktok()
        await self.poll_website()
        await self.poll_social_sources()

    async def poll_twitter(self):
        try:
            first_run = self.state_manager.is_first_run('Twitter')
            tweets = await asyncio.to_thread(self.twitter_scraper.get_latest_tweets)
            new_tweets = self.state_manager.get_new_items('Twitter', tweets)
            if not first_run:
                for tweet in new_tweets:
                    await self.send_item_update('twitter', tweet)
        except Exception as e:
            logger.error(f"Error in Twitter polling: {e}")

    async def poll_tiktok(self):
        try:
            first_run = self.state_manager.is_first_run('TikTok')
            videos = await asyncio.to_thread(self.tiktok_scraper.get_latest_videos)
            new_videos = self.state_manager.get_new_items('TikTok', videos)
            if not first_run:
                for video in new_videos:
                    await self.send_item_update('tiktok', video)
        except Exception as e:
            logger.error(f"Error in TikTok polling: {e}")

    async def poll_website(self):
        try:
            products = await asyncio.to_thread(self.website_scraper.get_latest_products)
            updates = self.state_manager.get_product_updates(products)
            for product in updates:
                await self.handle_shop_update(product)
        except Exception as e:
            logger.error(f"Error in Website polling: {e}")

    async def poll_social_sources(self):
        source_checks = [
            ('instagram', 'Instagram', self.social_scraper.get_instagram_updates),
            ('spotify', 'Spotify', self.social_scraper.get_spotify_updates),
            ('apple_music', 'Apple Music', self.social_scraper.get_apple_music_updates),
            ('soundcloud', 'SoundCloud', self.social_scraper.get_soundcloud_updates),
            ('youtube', 'YouTube', self.social_scraper.get_youtube_updates),
            ('tumblr', 'Tumblr', self.social_scraper.get_tumblr_updates),
        ]
        for source_key, source_name, fetcher in source_checks:
            try:
                first_run = self.state_manager.is_first_run(source_name)
                items = await asyncio.to_thread(fetcher)
                new_items = self.state_manager.get_new_items(source_name, items)
                if not first_run:
                    for item in new_items:
                        await self.send_item_update(source_key, item)
            except Exception as e:
                logger.error(f"Error in {source_name} polling: {e}")

    @polling_loop.before_loop
    async def before_polling_loop(self):
        await self.wait_until_ready()


bot = RimeraBot()


async def set_source_channel(interaction, source_key, channel):
    config.setdefault('channels', {})[source_key] = channel.id
    if source_key == 'default':
        config['channel_id'] = channel.id
    save_config()
    await interaction.response.send_message(f"{SOURCE_LABELS[source_key]} updates will post in {channel.mention}.")


@bot.tree.command(name="status", description="Check the bot status and configured channels")
async def status(interaction: discord.Interaction):
    embed = discord.Embed(title="Rimera Bot status", description="Running and watching rimerarimera.com plus configured social sources.", color=0xE85D9E)
    embed.add_field(name="Website", value=bot.website_scraper.url, inline=False)
    embed.add_field(name="Twitter", value=f"@{bot.twitter_scraper.handle}", inline=True)
    embed.add_field(name="TikTok", value=f"@{bot.tiktok_scraper.handle}", inline=True)
    embed.add_field(name="Linktree", value=config.get('linktree_url') or "Not set", inline=False)
    embed.add_field(name="Instagram", value=config.get('instagram_url') or "Not set", inline=False)
    embed.add_field(name="Spotify", value=config.get('spotify_url') or "Not set", inline=False)
    embed.add_field(name="Apple Music", value=config.get('apple_music_url') or "Not set", inline=False)
    embed.add_field(name="SoundCloud", value=config.get('soundcloud_url') or "Not set", inline=False)
    embed.add_field(name="YouTube", value=config.get('youtube_url') or config.get('youtube_channel_id') or "Not set", inline=False)
    media_channel = config.get('media_download_channel_id')
    embed.add_field(name="Media downloader", value=f"<#{media_channel}>" if media_channel else "Not set", inline=False)
    embed.add_field(name="Polling", value=f"{config.get('polling_interval_minutes', 5)} minutes", inline=True)
    embed.add_field(name="Early shop alerts", value=f"{len(config.get('initial_subscribers', []))} subscriber(s)", inline=True)
    embed.add_field(name="Channels", value=bot.configured_channel_mentions(), inline=False)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="invite", description="Get an invite link for the bot")
async def invite(interaction: discord.Interaction):
    app_id = "1507078816047300668"
    invite_url = f"https://discord.com/api/oauth2/authorize?client_id={app_id}&permissions=8&scope=bot%20applications.commands"
    await interaction.response.send_message(f"Invite me to your server: {invite_url}")


@bot.tree.command(name="donate", description="Support the bot's hosting and development")
async def donate(interaction: discord.Interaction):
    await interaction.response.send_message("Donations are only used to help run and maintain the bot via PayPal: https://bit.ly/49figis")


@bot.tree.command(name="channels", description="Show where each update type is posted")
async def channels(interaction: discord.Interaction):
    embed = discord.Embed(title="Configured update channels", description=bot.configured_channel_mentions(), color=0xE85D9E)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="set-media-channel", description="Set the channel where social links are automatically downloaded")
@is_admin_or_super_user()
async def set_media_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    config['media_download_channel_id'] = channel.id
    save_config()
    await interaction.response.send_message(f"Media auto-downloads are now enabled in {channel.mention}. Drop a public video/photo link there and I'll reply with the downloaded media.")


@bot.tree.command(name="media-channel", description="Show the channel used for automatic media downloads")
async def media_channel(interaction: discord.Interaction):
    channel_id = config.get('media_download_channel_id')
    if channel_id:
        await interaction.response.send_message(f"Automatic media downloads are enabled in <#{channel_id}>.")
    else:
        await interaction.response.send_message("Automatic media downloads are not configured yet. An administrator can use `/set-media-channel`.")


@bot.tree.command(name="initial", description="Register for private early shop alerts")
async def initial(interaction: discord.Interaction, password: str):
    if password != config.get('initial_password', 'CHANGE_ME'):
        await interaction.response.send_message("Incorrect password.", ephemeral=True)
        return
    subscriber_id = str(interaction.user.id)
    subscribers = config.setdefault('initial_subscribers', [])
    if subscriber_id not in subscribers:
        subscribers.append(subscriber_id)
        save_config()
        message = "You are registered for private early shop alerts."
    else:
        message = "You are already registered for private early shop alerts."
    await interaction.response.send_message(message, ephemeral=True)


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, (app_commands.MissingPermissions, app_commands.CheckFailure)):
        message = "You need administrator permission to use that command."
    else:
        logger.error(f"Slash command error: {error}")
        message = "Something went wrong while running that command."
    if interaction.response.is_done():
        await interaction.followup.send(message)
    else:
        await interaction.response.send_message(message)


if __name__ == "__main__":
    if not TOKEN:
        logger.error("Please set DISCORD_TOKEN in a .env file.")
    else:
        bot.run(TOKEN)
