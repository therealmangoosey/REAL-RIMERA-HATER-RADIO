"""Lightweight keyword-to-emoji reactions for the Rimera bot.

This module is intentionally dependency-free apart from discord.py. The keyword
map is compiled once at import time so normal messages only do a cheap regex
match and, when matched, a small number of Discord reaction requests.
"""

import asyncio
import re
from typing import Dict, List

# The old keyword reaction table is not present in the repository history, so
# keep this small/default table easy to edit without touching bot.py.
# Add or change entries here as: "word": "emoji".
KEYWORD_REACTIONS: Dict[str, str] = {
    "rimera": "💗",
    "rimerahate": "😭",
    "rimerahater": "😭",
    "radio": "📻",
    "song": "🎵",
    "music": "🎶",
    "merch": "🛍️",
    "instagram": "📸",
    "tiktok": "🎬",
    "spotify": "🎧",
    "youtube": "▶️",
}

MAX_REACTIONS_PER_MESSAGE = 3

_PATTERN = re.compile(
    r"(?<![\w])(?:" + "|".join(
        re.escape(word) for word in sorted(KEYWORD_REACTIONS, key=len, reverse=True)
    ) + r")(?![\w])",
    re.IGNORECASE,
)


def matching_reactions(content: str) -> List[str]:
    """Return unique emojis for matched whole-word keywords, capped per message."""
    if not content:
        return []

    found: List[str] = []
    for match in _PATTERN.finditer(content):
        emoji = KEYWORD_REACTIONS[match.group(0).lower()]
        if emoji not in found:
            found.append(emoji)
            if len(found) >= MAX_REACTIONS_PER_MESSAGE:
                break
    return found


async def react_to_message(message) -> None:
    """React to a message when it contains configured keywords."""
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
