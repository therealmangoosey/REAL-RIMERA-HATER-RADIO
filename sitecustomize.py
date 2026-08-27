import logging

try:
    from media_downloader import MediaDownloader
    from public_story_resolver import resolve_public_story

    _logger = logging.getLogger("rimera-bot.sitecustomize")

    def _download_story_public_first_direct(self, url, workdir):
        _logger.info("Starting direct public Story resolver for %s", url)
        try:
            files = resolve_public_story(url, workdir, timeout=8)
            if files:
                return files, "direct public Story resolver"
        except Exception as exc:
            _logger.warning("Direct public Story resolver failed: %s", exc)
        return [], "direct public Story resolver returned no media"

    MediaDownloader._download_story_public_first = _download_story_public_first_direct
except Exception:
    logging.getLogger("rimera-bot.sitecustomize").debug("Story resolver bootstrap unavailable", exc_info=True)

# Register the existing reaction handler as a proper Discord listener and add
# a persistent admin toggle. This avoids replacing Bot.on_message, which can
# interfere with the bot's own message handling.
try:
    import discord
    from discord import app_commands
    from discord.ext import commands

    from keyword_reactions import reactions_enabled, react_to_message, set_reactions_enabled

    SUPER_ADMIN_ID = 1300260018691637308

    async def _reaction_admin_check(interaction: discord.Interaction) -> bool:
        return interaction.user.id == SUPER_ADMIN_ID or (
            interaction.guild is not None and interaction.user.guild_permissions.administrator
        )

    @app_commands.default_permissions(administrator=True)
    async def _reactions_on(interaction: discord.Interaction):
        if not await _reaction_admin_check(interaction):
            await interaction.response.send_message("You need Administrator permission to change reactions.", ephemeral=True)
            return
        if not set_reactions_enabled(True):
            await interaction.response.send_message("I couldn't save the reaction setting.", ephemeral=True)
            return
        await interaction.response.send_message("Automatic keyword reactions are now **ON**.", ephemeral=True)

    @app_commands.default_permissions(administrator=True)
    async def _reactions_off(interaction: discord.Interaction):
        if not await _reaction_admin_check(interaction):
            await interaction.response.send_message("You need Administrator permission to change reactions.", ephemeral=True)
            return
        if not set_reactions_enabled(False):
            await interaction.response.send_message("I couldn't save the reaction setting.", ephemeral=True)
            return
        await interaction.response.send_message("Automatic keyword reactions are now **OFF**.", ephemeral=True)

    @app_commands.default_permissions(administrator=True)
    async def _reactions_status(interaction: discord.Interaction):
        if not await _reaction_admin_check(interaction):
            await interaction.response.send_message("You need Administrator permission to view reaction settings.", ephemeral=True)
            return
        state = "ON" if reactions_enabled() else "OFF"
        await interaction.response.send_message(f"Automatic keyword reactions are **{state}**.", ephemeral=True)

    _reaction_group = app_commands.Group(name="reactions", description="Control automatic keyword emoji reactions")
    _reaction_group.add_command(app_commands.Command(name="on", description="Turn automatic keyword reactions on", callback=_reactions_on))
    _reaction_group.add_command(app_commands.Command(name="off", description="Turn automatic keyword reactions off", callback=_reactions_off))
    _reaction_group.add_command(app_commands.Command(name="status", description="Show the automatic reaction status", callback=_reactions_status))

    _original_bot_init = commands.Bot.__init__

    def _bot_init_with_reactions(self, *args, **kwargs):
        _original_bot_init(self, *args, **kwargs)
        try:
            self.add_listener(react_to_message, "on_message")
            if not any(getattr(command, "name", None) == "reactions" for command in self.tree.get_commands()):
                self.tree.add_command(_reaction_group)
        except Exception:
            logging.getLogger("rimera-bot.sitecustomize").exception("Failed to install reaction handler")

    commands.Bot.__init__ = _bot_init_with_reactions
except Exception:
    logging.getLogger("rimera-bot.sitecustomize").exception("Keyword reaction bootstrap unavailable")
