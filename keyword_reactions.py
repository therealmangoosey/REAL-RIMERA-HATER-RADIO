"""Alias-based custom emoji reactions for the Rimera bot."""

import json
import logging
import os
import re
from typing import Dict, List

CONFIG_FILE = "config.json"
REACTIONS_ENABLED_KEY = "reactions_enabled"
logger = logging.getLogger("rimera-bot.reactions")

KEYWORD_REACTIONS: Dict[str, str] = {
    "jazz punk": "<:JazzPunk:1395637360682602587>",
    "bushwa": "<:BUSHWA:1395637306408566805>",
    "vol 1": "<:CatchMeIfYouCan:1480703883356536985>",
    "volume 1": "<:CatchMeIfYouCan:1480703883356536985>",
    "volume one": "<:CatchMeIfYouCan:1480703883356536985>",
    "catch me if you can": "<:CatchMeIfYouCan:1480703883356536985>",
    "cmiyc": "<:CatchMeIfYouCan:1480703883356536985>",
    "vol 2": "<:RealRimeraHaterRadio:1504949135655305246>",
    "volume 2": "<:RealRimeraHaterRadio:1504949135655305246>",
    "volume two": "<:RealRimeraHaterRadio:1504949135655305246>",
    "real rimera hater": "<:RealRimeraHaterRadio:1504949135655305246>",
    "real rimera hater radio": "<:RealRimeraHaterRadio:1504949135655305246>",
    "rimera": "<:Pinkface:1430050553752190996>",
    "cd": "<:TheCDKeeper:1482891305171554304>",
    "dense": "<:dense:1512748563648479342>",
    "cw": "<:CAMPWANDER:1492324641556008970>",
    "campwander": "<:CAMPWANDER:1492324641556008970>",
    "camp wander": "<:CAMPWANDER:1492324641556008970>",
    "camp-wander": "<:CAMPWANDER:1492324641556008970>",
    "camp_wander": "<:CAMPWANDER:1492324641556008970>",
}

_COMPILED_REACTIONS = [
    (re.compile(r"(?<![\w])" + re.escape(alias) + r"(?![\w])", re.IGNORECASE), emoji)
    for alias, emoji in KEYWORD_REACTIONS.items()
]


def _load_enabled() -> bool:
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as handle:
            config = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return True
    return bool(config.get(REACTIONS_ENABLED_KEY, True))


_reactions_enabled = _load_enabled()


def reactions_enabled() -> bool:
    return _reactions_enabled


def set_reactions_enabled(enabled: bool) -> bool:
    global _reactions_enabled
    try:
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as handle:
                config = json.load(handle)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            config = {}
        config[REACTIONS_ENABLED_KEY] = bool(enabled)
        temp_path = f"{CONFIG_FILE}.tmp"
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(config, handle, indent=4)
            handle.write("\n")
        os.replace(temp_path, CONFIG_FILE)
    except OSError:
        logger.exception("Could not persist reaction setting")
        return False
    _reactions_enabled = bool(enabled)
    return True


def matching_reactions(content: str) -> List[str]:
    if not content:
        return []
    found: List[str] = []
    for pattern, emoji in _COMPILED_REACTIONS:
        if pattern.search(content) and emoji not in found:
            found.append(emoji)
    return found


async def react_to_message(message) -> None:
    if not reactions_enabled() or message.author.bot or not message.content:
        return

    emojis = matching_reactions(message.content)
    if not emojis:
        return

    import discord

    for emoji_text in emojis:
        emoji = discord.PartialEmoji.from_str(emoji_text)
        if emoji.id is None:
            logger.error("Invalid configured custom emoji: %s", emoji_text)
            continue
        try:
            await message.add_reaction(emoji)
            logger.info("Added reaction %s to message %s", emoji_text, message.id)
        except discord.Forbidden:
            logger.error(
                "Discord rejected reaction %s on message %s. Check Add Reactions and Use External Emojis permissions and that the emoji is available to this server.",
                emoji_text,
                message.id,
            )
        except discord.HTTPException as exc:
            logger.error("Failed to add reaction %s to message %s: %s", emoji_text, message.id, exc)
