"""Alias-based custom emoji reactions for the Rimera bot."""

import asyncio
import json
import os
import re
from typing import Dict, List

CONFIG_FILE = "config.json"
REACTIONS_ENABLED_KEY = "reactions_enabled"

# Keep this table explicit and local. Do not populate it from Discord/API data.
# Each key is a manual alias/phrase and each value is the exact custom emoji
# string to add when that phrase appears in a message.
KEYWORD_REACTIONS: Dict[str, str] = {
    "jazz punk": "<:JazzPunk:1395637360682602587>",
    "bushwa": "<:BUSHWA:1395637306408566805>",
    "vol 1": "<:CatchMeIfYouCan:1480703883356536985>",
    "volume 1": "<:CatchMeIfYouCan:1480703883356536985>",
    "volume one": "<:CatchMeIfYouCan:1480703883356536985>",
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
}

_COMPILED_REACTIONS = [
    (re.compile(r"(?<![\w])" + re.escape(alias) + r"(?![\w])", re.IGNORECASE), emoji)
    for alias, emoji in KEYWORD_REACTIONS.items()
]


def _load_enabled() -> bool:
    """Read the persistent toggle, defaulting to enabled for existing installs."""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as handle:
            config = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return True
    return bool(config.get(REACTIONS_ENABLED_KEY, True))


_reactions_enabled = _load_enabled()


def reactions_enabled() -> bool:
    """Return whether automatic keyword reactions are currently enabled."""
    return _reactions_enabled


def set_reactions_enabled(enabled: bool) -> bool:
    """Persist and apply the automatic reaction toggle."""
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
        return False

    _reactions_enabled = bool(enabled)
    return True


def matching_reactions(content: str) -> List[str]:
    """Return unique custom emojis for every matching configured alias."""
    if not content:
        return []

    found: List[str] = []
    for pattern, emoji in _COMPILED_REACTIONS:
        if pattern.search(content) and emoji not in found:
            found.append(emoji)
    return found


async def react_to_message(message) -> None:
    """React to a message when the persistent reaction toggle is enabled."""
    if not reactions_enabled() or message.author.bot or not message.content:
        return

    emojis = matching_reactions(message.content)
    if not emojis:
        return

    await asyncio.gather(
        *(message.add_reaction(emoji) for emoji in emojis),
        return_exceptions=True,
    )
