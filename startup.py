"""Dependency-safe launcher for the Rimera Hater Radio bot."""

import importlib.util
import os
import sys


REQUIRED = (
    ("discord", "discord.py"),
    ("requests", "requests"),
    ("yt_dlp", "yt-dlp"),
)


def missing_packages():
    return [package for module, package in REQUIRED if importlib.util.find_spec(module) is None]


def main():
    missing = missing_packages()
    if missing:
        print("Missing Python dependencies: " + ", ".join(missing))
        print("Install them with:")
        print(f"  {sys.executable} -m pip install -r requirements.txt")
        return 1

    import discord
    from discord import app_commands
    from bot import bot, TOKEN
    from keyword_reactions import reactions_enabled, react_to_message, set_reactions_enabled

    # Register the reaction listener explicitly. Do not rely on Python's optional
    # sitecustomize hook: Termux/Python environments can skip it.
    bot.add_listener(react_to_message, "on_message")

    SUPER_ADMIN_ID = 1300260018691637308

    def is_admin(interaction):
        return interaction.user.id == SUPER_ADMIN_ID or (
            interaction.guild is not None and interaction.user.guild_permissions.administrator
        )

    reactions_group = app_commands.Group(
        name="reactions",
        description="Control automatic keyword emoji reactions",
    )

    @reactions_group.command(name="on", description="Turn automatic keyword reactions on")
    async def reactions_on(interaction: discord.Interaction):
        if not is_admin(interaction):
            await interaction.response.send_message("You need Administrator permission to change reactions.", ephemeral=True)
            return
        if not set_reactions_enabled(True):
            await interaction.response.send_message("I couldn't save the reaction setting.", ephemeral=True)
            return
        await interaction.response.send_message("Automatic keyword reactions are now **ON**.", ephemeral=True)

    @reactions_group.command(name="off", description="Turn automatic keyword reactions off")
    async def reactions_off(interaction: discord.Interaction):
        if not is_admin(interaction):
            await interaction.response.send_message("You need Administrator permission to change reactions.", ephemeral=True)
            return
        if not set_reactions_enabled(False):
            await interaction.response.send_message("I couldn't save the reaction setting.", ephemeral=True)
            return
        await interaction.response.send_message("Automatic keyword reactions are now **OFF**.", ephemeral=True)

    @reactions_group.command(name="status", description="Show automatic keyword reaction status")
    async def reactions_status(interaction: discord.Interaction):
        if not is_admin(interaction):
            await interaction.response.send_message("You need Administrator permission to view reaction settings.", ephemeral=True)
            return
        state = "ON" if reactions_enabled() else "OFF"
        await interaction.response.send_message(f"Automatic keyword reactions are **{state}**.", ephemeral=True)

    bot.tree.add_command(reactions_group)

    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN is not set")
    bot.run(TOKEN)


if __name__ == "__main__":
    raise SystemExit(main())
