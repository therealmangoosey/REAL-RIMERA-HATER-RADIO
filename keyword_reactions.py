"""Alias-based custom emoji reactions for the Rimera bot."""

import asyncio
import re
from typing import Dict, List

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


def matching_reactions(content: str) -> List[str]:
    """Return unique custom emojis for every matching configured alias.

    Aliases are checked independently so overlapping entries also count. For
    example, "real rimera hater radio" matches both that full alias and
    "rimera", as required by the manual alias table.
    """
    if not content:
        return []

    found: List[str] = []
    for alias, emoji in KEYWORD_REACTIONS.items():
        pattern = re.compile(r"(?<![\w])" + re.escape(alias) + r"(?![\w])", re.IGNORECASE)
        if pattern.search(content) and emoji not in found:
            found.append(emoji)
    return found


async def react_to_message(message) -> None:
    """React to a message when it contains one or more configured aliases."""
    if message.author.bot or not message.content:
        return

    emojis = matching_reactions(message.content)
    if not emojis:
        return

    results = await asyncio.gather(
        *(message.add_reaction(emoji) for emoji in emojis),
        return_exceptions=True,
    )
    _ = results
