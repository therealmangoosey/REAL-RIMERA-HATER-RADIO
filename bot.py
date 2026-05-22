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
    'instagram': 'Instagram',
    'spotify': 'Spotify',
    'apple_music': 'Apple Music',
    'soundcloud': 'SoundCloud',
    'youtube': 'YouTube',
}

SUPER_ADMIN_ID = 1300260018691637308

def is_admin_or_super_user():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id == SUPER_ADMIN_ID:
            return True
        return interaction.user.guild_permissions.administrator
    return app_commands.check(predicate)

SHOP_PUBLIC_DELAY_SECONDS = 120


def load_config():
    with open(CONFIG_FILE, 'r') as f:
        loaded_config = json.load(f)

    loaded_config.setdefault('channels', {})
    if loaded_config.get('channel_id') and not loaded_config['channels'].get('default'):
        loaded_config['channels']['default'] = loaded_config['channel_id']
    loaded_config.setdefault('website_url', 'https://rimerarimera.com')
    loaded_config.setdefault('linktree_url', 'https://linktr.ee/rimerarimera')
    loaded_config.setdefault('instagram_url', 'https://instagram.com/rimeraera?igshid=YTM0ZjI4ZDI=')
    loaded_config.setdefault('spotify_url', 'https://open.spotify.com/artist/3HgzwrhMXuElbeBBWJ1d38?si=90d_vXIFSiCDkBjAGG0FyA')
    loaded_config.setdefault('apple_music_url', 'https://music.apple.com/gb/artist/rimera/1478454603')
    loaded_config.setdefault('soundcloud_url', 'https://soundcloud.app.goo.gl/HuhB6bRZBe9Qutt68')
    loaded_config.setdefault('youtube_url', 'https://youtube.com/channel/UCeliKm-RLwRJNWJLOhv3lNw')
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
            config.get('twitter_handle', 'rimera'),
            config.get('nitter_instances', ["https://nitter.net"])
        )
        self.tiktok_scraper = TikTokScraper(config.get('tiktok_handle', 'rimera'))
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
        await self.change_presence(activity=discord.Game(name="rimera.vercel.app"))
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

        channel = None
        try:
            channel_id_int = int(channel_id)
            channel = self.get_channel(channel_id_int) or await self.fetch_channel(channel_id_int)
        except (ValueError, TypeError, discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
            logger.error(f"Error retrieving channel {channel_id} for {source_key}: {e}")
            return False

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
            ('instagram', 'Instagram', self.social_scraper.get_instagram_updates),
            ('spotify', 'Spotify', self.social_scraper.get_spotify_updates),
            ('apple_music', 'Apple Music', self.social_scraper.get_apple_music_updates),
            ('soundcloud', 'SoundCloud', self.social_scraper.get_soundcloud_updates),
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


class WebRecommendationModal(discord.ui.Modal, title='Website Recommendation'):
    rec_title = discord.ui.TextInput(label='Feature or Page Name', placeholder='e.g. Dark Mode, Gallery Page', required=True)
    description = discord.ui.TextInput(label='Details', style=discord.TextStyle.paragraph, placeholder='Describe your suggestion for rimera.vercel.app...', required=True)

    def __init__(self, attachment: discord.Attachment = None):
        super().__init__()
        self.attachment = attachment

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()  # Fixes the "Interaction failed" error
        target_channel_id = 1507095977251700796
        channel = interaction.client.get_channel(target_channel_id)
        if not channel:
            try:
                channel = await interaction.client.fetch_channel(target_channel_id)
            except Exception:
                await interaction.followup.send("Error: Could not find the target channel.")
                return

        embed = discord.Embed(
            title="✨ New Website Recommendation",
            color=0xE85D9E,
            timestamp=discord.utils.utcnow()
        )
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.add_field(name="🏷️ Suggestion", value=self.rec_title.value, inline=False)
        embed.add_field(name="📝 Details", value=self.description.value, inline=False)
        
        files = []
        if self.attachment:
            file_data = await self.attachment.to_file()
            files.append(file_data)
            if self.attachment.content_type and self.attachment.content_type.startswith('image/'):
                embed.set_image(url=f"attachment://{self.attachment.filename}")

        try:
            await channel.send(embed=embed, files=files)
            await interaction.followup.send("✅ Your recommendation has been submitted successfully!")
        except discord.Forbidden:
            logger.error(f"Permission denied (50001) for channel {target_channel_id}. Bot lacks 'View Channel' or 'Send Messages'.")
            await interaction.followup.send(f"❌ Error: I don't have access to the recommendation channel. Please ensure I have 'View Channel' and 'Send Messages' permissions in <#{target_channel_id}>.")
        except discord.HTTPException as e:
            logger.error(f"Failed to send recommendation: {e}")
            await interaction.followup.send("❌ Something went wrong while submitting your recommendation.")


bot = RimeraBot()


async def set_source_channel(interaction, source_key, channel):
    config.setdefault('channels', {})[source_key] = channel.id
    if source_key == 'default':
        config['channel_id'] = channel.id
    save_config()
    await interaction.response.send_message(
        f"{SOURCE_LABELS[source_key]} updates will post in {channel.mention}."
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
    embed.add_field(name="Linktree", value=config.get('linktree_url') or "Not set", inline=False)
    embed.add_field(name="Instagram", value=config.get('instagram_url') or "Not set", inline=False)
    embed.add_field(name="Spotify", value=config.get('spotify_url') or "Not set", inline=False)
    embed.add_field(name="Apple Music", value=config.get('apple_music_url') or "Not set", inline=False)
    embed.add_field(name="SoundCloud", value=config.get('soundcloud_url') or "Not set", inline=False)
    embed.add_field(name="YouTube", value=config.get('youtube_url') or config.get('youtube_channel_id') or "Not set", inline=False)
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
    await interaction.response.send_message(
        "Donations are only used to help run and maintain the bot via PayPal: https://bit.ly/49figis",
    )


@bot.tree.command(name="channels", description="Show where each update type is posted")
async def channels(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Configured update channels",
        description=bot.configured_channel_mentions(),
        color=0xE85D9E
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="web-reccomendations", description="Submit a recommendation for the website")
async def web_reccomendations(interaction: discord.Interaction, file: discord.Attachment = None):
    await interaction.response.send_modal(WebRecommendationModal(file))


@bot.tree.command(name="test", description="Test shop or social pings with the most recent post info")
@app_commands.choices(ping_type=[
    app_commands.Choice(name="Shop Ping", value="shop"),
    app_commands.Choice(name="Social Ping", value="social"),
])
@is_admin_or_super_user()
async def test_ping(interaction: discord.Interaction, ping_type: app_commands.Choice[str]):
    await interaction.response.defer(thinking=True)
    
    if ping_type.value == "shop":
        items = await asyncio.to_thread(bot.website_scraper.get_latest_products)
        if items:
            item = items[0]
            embed = bot.formatter.format_item(item)
            stock_status = "❌ Sold Out" if item.get('sold_out') else "✅ In Stock"
            embed.add_field(name="📊 Item Stats", value=f"**Price:** {item.get('price', 'N/A')}\n**Status:** {stock_status}", inline=False)
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("No shop products found.")
    else:
        fetchers = [
            bot.social_scraper.get_instagram_updates,
            bot.social_scraper.get_youtube_updates,
            bot.social_scraper.get_spotify_updates,
            bot.social_scraper.get_apple_music_updates,
            bot.social_scraper.get_soundcloud_updates
        ]
        found_item = None
        for fetcher in fetchers:
            items = await asyncio.to_thread(fetcher)
            if items:
                found_item = items[0]
                break
        
        if found_item:
            embed = bot.formatter.format_item(found_item)
            embed.add_field(name="📊 Post Info", value=f"**Platform:** {found_item.get('source', 'Unknown')}\n**Post ID:** `{found_item.get('id', 'N/A')}`", inline=False)
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("No social items found.")


@bot.tree.command(name="set-channel", description="Set the default update channel")
@is_admin_or_super_user()
async def set_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    await set_source_channel(interaction, 'default', channel)


@bot.tree.command(name="set-website-channel", description="Set the product and restock update channel")
@is_admin_or_super_user()
async def set_website_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    await set_source_channel(interaction, 'website', channel)


@bot.tree.command(name="set-shop-channel", description="Set the shop product and restock update channel")
@is_admin_or_super_user()
async def set_shop_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    await set_source_channel(interaction, 'website', channel)


@bot.tree.command(name="set-twitter-channel", description="Set the Twitter update channel")
@is_admin_or_super_user()
async def set_twitter_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    await set_source_channel(interaction, 'twitter', channel)


@bot.tree.command(name="set-tiktok-channel", description="Set the TikTok update channel")
@is_admin_or_super_user()
async def set_tiktok_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    await set_source_channel(interaction, 'tiktok', channel)


@bot.tree.command(name="set-instagram-channel", description="Set the Instagram update channel")
@is_admin_or_super_user()
async def set_instagram_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    await set_source_channel(interaction, 'instagram', channel)


@bot.tree.command(name="set-spotify-channel", description="Set the Spotify update channel")
@is_admin_or_super_user()
async def set_spotify_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    await set_source_channel(interaction, 'spotify', channel)


@bot.tree.command(name="set-apple-music-channel", description="Set the Apple Music update channel")
@is_admin_or_super_user()
async def set_apple_music_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    await set_source_channel(interaction, 'apple_music', channel)


@bot.tree.command(name="set-soundcloud-channel", description="Set the SoundCloud update channel")
@is_admin_or_super_user()
async def set_soundcloud_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    await set_source_channel(interaction, 'soundcloud', channel)


@bot.tree.command(name="set-youtube-channel", description="Set the YouTube update channel")
@is_admin_or_super_user()
async def set_youtube_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    await set_source_channel(interaction, 'youtube', channel)


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
@is_admin_or_super_user()
async def check_products(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    products = await asyncio.to_thread(bot.website_scraper.get_latest_products)
    updates = bot.state_manager.get_product_updates(products)

    if not products:
        await interaction.followup.send("No products found on the website. The shop might be locked or down.")
        return

    sent_count = 0
    for product in updates:
        sent_count += await bot.send_early_shop_update(product)
        # Post immediately for manual checks to verify channel config
        await bot.send_item_update('website', product)

    await interaction.followup.send(
        f"Checked {len(products)} products. Sent {sent_count} early alert(s) and posted updates to the shop channel."
    )


@bot.tree.command(name="check-socials", description="Check Linktree-listed social and music pages now")
@is_admin_or_super_user()
async def check_socials(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)

    source_checks = [
        ('instagram', 'Instagram', bot.social_scraper.get_instagram_updates),
        ('spotify', 'Spotify', bot.social_scraper.get_spotify_updates),
        ('apple_music', 'Apple Music', bot.social_scraper.get_apple_music_updates),
        ('soundcloud', 'SoundCloud', bot.social_scraper.get_soundcloud_updates),
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
        f"Checked {checked_count} social item(s). Sent {sent_count} update(s)."
    )


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
