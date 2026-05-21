import asyncio
import json
import logging
import os

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

from discord_formatter import DiscordFormatter
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
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('rimera-bot')

CONFIG_FILE = 'config.json'
SOURCE_LABELS = {
    'default': 'Default',
    'website': 'Website',
    'twitter': 'Twitter',
    'tiktok': 'TikTok',
    'tumblr': 'Tumblr',
    'instagram': 'Instagram',
    'spotify': 'Spotify',
    'youtube': 'YouTube',
}

SHOP_PUBLIC_DELAY_SECONDS = 120


def load_config():
    with open(CONFIG_FILE, 'r') as f:
        loaded_config = json.load(f)

    loaded_config.setdefault('channels', {})
    if loaded_config.get('channel_id') and not loaded_config['channels'].get('default'):
        loaded_config['channels']['default'] = loaded_config['channel_id']
    loaded_config.setdefault('website_url', 'https://rimerarimera.com')
    loaded_config.setdefault('tumblr_url', 'https://rimeraera.tumblr.com')
    loaded_config.setdefault('instagram_url', 'https://www.instagram.com/rimeraera/')
    loaded_config.setdefault('spotify_url', 'https://open.spotify.com/artist/3HgzwrhMXuElbeBBWJ1d38')
    loaded_config.setdefault('youtube_url', 'https://www.youtube.com/channel/UCeliKm-RLwRJNWJLOhv3lNw')
    loaded_config.setdefault('youtube_channel_id', 'UCeliKm-RLwRJNWJLOhv3lNw')
    loaded_config.setdefault('initial_password', 'Phone118')
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
            config.get('twitter_handle', 'rimera_official'),
            config.get('nitter_instances', ["https://nitter.net"])
        )
        self.tiktok_scraper = TikTokScraper(config.get('tiktok_handle', 'rimera_official'))
        self.website_scraper = WebsiteScraper(config.get('website_url', 'https://rimerarimera.com'))
        self.social_scraper = SocialScraper(config)
        self.formatter = DiscordFormatter()

    async def setup_hook(self):
        logger.info("Setting up bot...")
        self.polling_loop.start()

        if start_web_server and config.get('enable_web_server', False):
            start_web_server(self, config.get('flask_port', 5000))

    async def on_ready(self):
        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} command(s)")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")

    def channel_id_for(self, source_key):
        channels = config.setdefault('channels', {})
        return channels.get(source_key) or channels.get('default') or config.get('channel_id')

    def configured_channel_mentions(self):
        rows = []
        for key, label in SOURCE_LABELS.items():
            channel_id = self.channel_id_for(key) if key != 'default' else config.get('channels', {}).get('default')
            channel = self.get_channel(int(channel_id)) if channel_id else None
            value = channel.mention if channel else (f"`{channel_id}`" if channel_id else "Not set")
            rows.append(f"{label}: {value}")
        return "\n".join(rows)

    async def send_item_update(self, source_key, item):
        channel_id = self.channel_id_for(source_key)
        if not channel_id:
            logger.warning(f"No channel configured for {source_key}; skipping notification.")
            return False

        channel = self.get_channel(int(channel_id))
        if not channel:
            logger.error(f"Could not find channel with ID {channel_id} for {source_key}")
            return False

        try:
            embed = self.formatter.format_item(item)
            await channel.send(embed=embed)
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
            ('tumblr', 'Tumblr', self.social_scraper.get_tumblr_updates),
            ('instagram', 'Instagram', self.social_scraper.get_instagram_updates),
            ('spotify', 'Spotify', self.social_scraper.get_spotify_updates),
            ('youtube', 'YouTube', self.social_scraper.get_youtube_updates),
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
    await interaction.response.send_message(
        f"{SOURCE_LABELS[source_key]} updates will post in {channel.mention}.",
        ephemeral=True
    )


@bot.tree.command(name="status", description="Check the bot status and configured channels")
async def status(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Rimera Bot status",
        description="Running and watching rimerarimera.com plus configured social sources.",
        color=0xE85D9E
    )
    embed.add_field(name="Website", value=bot.website_scraper.url, inline=False)
    embed.add_field(name="Twitter", value=f"@{bot.twitter_scraper.handle}", inline=True)
    embed.add_field(name="TikTok", value=f"@{bot.tiktok_scraper.handle}", inline=True)
    embed.add_field(name="Tumblr", value=config.get('tumblr_url') or "Not set", inline=False)
    embed.add_field(name="Instagram", value=config.get('instagram_url') or "Not set", inline=False)
    embed.add_field(name="Spotify", value=config.get('spotify_url') or "Not set", inline=False)
    embed.add_field(name="YouTube", value=config.get('youtube_url') or config.get('youtube_channel_id') or "Not set", inline=False)
    embed.add_field(name="Polling", value=f"{config.get('polling_interval_minutes', 5)} minutes", inline=True)
    embed.add_field(name="Early shop alerts", value=f"{len(config.get('initial_subscribers', []))} subscriber(s)", inline=True)
    embed.add_field(name="Channels", value=bot.configured_channel_mentions(), inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="channels", description="Show where each update type is posted")
async def channels(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Configured update channels",
        description=bot.configured_channel_mentions(),
        color=0xE85D9E
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="set-channel", description="Set the default update channel")
@app_commands.checks.has_permissions(administrator=True)
async def set_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    await set_source_channel(interaction, 'default', channel)


@bot.tree.command(name="set-website-channel", description="Set the product and restock update channel")
@app_commands.checks.has_permissions(administrator=True)
async def set_website_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    await set_source_channel(interaction, 'website', channel)


@bot.tree.command(name="set-shop-channel", description="Set the shop product and restock update channel")
@app_commands.checks.has_permissions(administrator=True)
async def set_shop_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    await set_source_channel(interaction, 'website', channel)


@bot.tree.command(name="set-twitter-channel", description="Set the Twitter update channel")
@app_commands.checks.has_permissions(administrator=True)
async def set_twitter_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    await set_source_channel(interaction, 'twitter', channel)


@bot.tree.command(name="set-tiktok-channel", description="Set the TikTok update channel")
@app_commands.checks.has_permissions(administrator=True)
async def set_tiktok_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    await set_source_channel(interaction, 'tiktok', channel)


@bot.tree.command(name="set-tumblr-channel", description="Set the Tumblr update channel")
@app_commands.checks.has_permissions(administrator=True)
async def set_tumblr_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    await set_source_channel(interaction, 'tumblr', channel)


@bot.tree.command(name="set-instagram-channel", description="Set the Instagram update channel")
@app_commands.checks.has_permissions(administrator=True)
async def set_instagram_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    await set_source_channel(interaction, 'instagram', channel)


@bot.tree.command(name="set-spotify-channel", description="Set the Spotify update channel")
@app_commands.checks.has_permissions(administrator=True)
async def set_spotify_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    await set_source_channel(interaction, 'spotify', channel)


@bot.tree.command(name="set-youtube-channel", description="Set the YouTube update channel")
@app_commands.checks.has_permissions(administrator=True)
async def set_youtube_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    await set_source_channel(interaction, 'youtube', channel)


@bot.tree.command(name="set-social-url", description="Set a social profile URL to monitor")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.choices(source=[
    app_commands.Choice(name="Tumblr", value="tumblr_url"),
    app_commands.Choice(name="Instagram", value="instagram_url"),
    app_commands.Choice(name="Spotify", value="spotify_url"),
    app_commands.Choice(name="YouTube", value="youtube_url"),
])
async def set_social_url(
    interaction: discord.Interaction,
    source: app_commands.Choice[str],
    url: str
):
    config[source.value] = url.strip()
    if source.value == 'youtube_url':
        config['youtube_channel_id'] = ''
    save_config()
    await interaction.response.send_message(
        f"{source.name} monitoring URL set to {url}.",
        ephemeral=True
    )


@bot.tree.command(name="initial", description="Register for private early shop alerts")
async def initial(interaction: discord.Interaction, password: str):
    if password != config.get('initial_password', 'Phone118'):
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


@bot.tree.command(name="check-products", description="Check rimerarimera.com now for new or restocked products")
@app_commands.checks.has_permissions(administrator=True)
async def check_products(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    products = await asyncio.to_thread(bot.website_scraper.get_latest_products)
    updates = bot.state_manager.get_product_updates(products)

    sent_count = 0
    for product in updates:
        sent_count += await bot.send_early_shop_update(product)
        asyncio.create_task(bot.send_delayed_shop_channel_update(product))

    await interaction.followup.send(
        f"Checked {len(products)} products. Sent {sent_count} early alert(s). Shop channel updates will post 2 minutes later.",
        ephemeral=True
    )


@bot.tree.command(name="check-socials", description="Check Tumblr, Instagram, Spotify, and YouTube now")
@app_commands.checks.has_permissions(administrator=True)
async def check_socials(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)

    source_checks = [
        ('tumblr', 'Tumblr', bot.social_scraper.get_tumblr_updates),
        ('instagram', 'Instagram', bot.social_scraper.get_instagram_updates),
        ('spotify', 'Spotify', bot.social_scraper.get_spotify_updates),
        ('youtube', 'YouTube', bot.social_scraper.get_youtube_updates),
    ]
    checked_count = 0
    sent_count = 0

    for source_key, source_name, fetcher in source_checks:
        items = await asyncio.to_thread(fetcher)
        checked_count += len(items)
        new_items = bot.state_manager.get_new_items(source_name, items)
        for item in new_items:
            if await bot.send_item_update(source_key, item):
                sent_count += 1

    await interaction.followup.send(
        f"Checked {checked_count} social item(s). Sent {sent_count} update(s).",
        ephemeral=True
    )


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        message = "You need administrator permission to use that command."
    else:
        logger.error(f"Slash command error: {error}")
        message = "Something went wrong while running that command."

    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


if __name__ == "__main__":
    if not TOKEN:
        logger.error("Please set DISCORD_TOKEN in a .env file.")
    else:
        bot.run(TOKEN)
