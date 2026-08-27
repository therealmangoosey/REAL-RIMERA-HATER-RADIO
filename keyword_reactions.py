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
    "jazz punk": "<:JazzPunk:1395637360682602587>", "jazzpunk": "<:JazzPunk:1395637360682602587>", "jazz-punk": "<:JazzPunk:1395637360682602587>", "jazz_punk": "<:JazzPunk:1395637360682602587>", "jazz punk music": "<:JazzPunk:1395637360682602587>", "jazzpunk music": "<:JazzPunk:1395637360682602587>", "jazz punk song": "<:JazzPunk:1395637360682602587>", "jazz punk track": "<:JazzPunk:1395637360682602587>", "jazz punk album": "<:JazzPunk:1395637360682602587>", "jazzpunk album": "<:JazzPunk:1395637360682602587>", "jazz punk era": "<:JazzPunk:1395637360682602587>", "jazzpunk era": "<:JazzPunk:1395637360682602587>", "jazz punk rimera": "<:JazzPunk:1395637360682602587>", "rimera jazz punk": "<:JazzPunk:1395637360682602587>",
    "bushwa": "<:BUSHWA:1395637306408566805>", "bushwa music": "<:BUSHWA:1395637306408566805>", "bushwa song": "<:BUSHWA:1395637306408566805>", "bushwa track": "<:BUSHWA:1395637306408566805>", "bushwa album": "<:BUSHWA:1395637306408566805>", "bushwa era": "<:BUSHWA:1395637306408566805>", "bushwa rimera": "<:BUSHWA:1395637306408566805>", "rimera bushwa": "<:BUSHWA:1395637306408566805>", "the bushwa": "<:BUSHWA:1395637306408566805>", "that bushwa": "<:BUSHWA:1395637306408566805>", "bushwa project": "<:BUSHWA:1395637306408566805>", "bushwa record": "<:BUSHWA:1395637306408566805>", "bushwa music project": "<:BUSHWA:1395637306408566805>", "bushwa album era": "<:BUSHWA:1395637306408566805>",
    "vol 1": "<:CatchMeIfYouCan:1480703883356536985>", "vol. 1": "<:CatchMeIfYouCan:1480703883356536985>", "volume 1": "<:CatchMeIfYouCan:1480703883356536985>", "volume one": "<:CatchMeIfYouCan:1480703883356536985>", "vol one": "<:CatchMeIfYouCan:1480703883356536985>", "v1": "<:CatchMeIfYouCan:1480703883356536985>", "v.1": "<:CatchMeIfYouCan:1480703883356536985>", "v 1": "<:CatchMeIfYouCan:1480703883356536985>", "catch me if you can": "<:CatchMeIfYouCan:1480703883356536985>", "catchmeifyoucan": "<:CatchMeIfYouCan:1480703883356536985>", "catch-me-if-you-can": "<:CatchMeIfYouCan:1480703883356536985>", "catch_me_if_you_can": "<:CatchMeIfYouCan:1480703883356536985>", "cmiyc": "<:CatchMeIfYouCan:1480703883356536985>", "cmi yc": "<:CatchMeIfYouCan:1480703883356536985>", "catch me": "<:CatchMeIfYouCan:1480703883356536985>", "catch me if": "<:CatchMeIfYouCan:1480703883356536985>", "catch me if u can": "<:CatchMeIfYouCan:1480703883356536985>", "catch me if ya can": "<:CatchMeIfYouCan:1480703883356536985>", "catch me if you can rimera": "<:CatchMeIfYouCan:1480703883356536985>",
    "vol 2": "<:RealRimeraHaterRadio:1504949135655305246>", "vol. 2": "<:RealRimeraHaterRadio:1504949135655305246>", "volume 2": "<:RealRimeraHaterRadio:1504949135655305246>", "volume two": "<:RealRimeraHaterRadio:1504949135655305246>", "vol two": "<:RealRimeraHaterRadio:1504949135655305246>", "v2": "<:RealRimeraHaterRadio:1504949135655305246>", "v.2": "<:RealRimeraHaterRadio:1504949135655305246>", "v 2": "<:RealRimeraHaterRadio:1504949135655305246>", "real rimera hater": "<:RealRimeraHaterRadio:1504949135655305246>", "real rimera hater radio": "<:RealRimeraHaterRadio:1504949135655305246>", "realrimerahater": "<:RealRimeraHaterRadio:1504949135655305246>", "realrimerahaterradio": "<:RealRimeraHaterRadio:1504949135655305246>", "real-rimera-hater": "<:RealRimeraHaterRadio:1504949135655305246>", "real-rimera-hater-radio": "<:RealRimeraHaterRadio:1504949135655305246>", "real_rimera_hater": "<:RealRimeraHaterRadio:1504949135655305246>", "real_rimera_hater_radio": "<:RealRimeraHaterRadio:1504949135655305246>", "rrhr": "<:RealRimeraHaterRadio:1504949135655305246>", "rrh radio": "<:RealRimeraHaterRadio:1504949135655305246>", "hater radio": "<:RealRimeraHaterRadio:1504949135655305246>", "rimera hater radio": "<:RealRimeraHaterRadio:1504949135655305246>", "real hater radio": "<:RealRimeraHaterRadio:1504949135655305246>",
    "rimera": "<:Pinkface:1430050553752190996>", "rimera music": "<:Pinkface:1430050553752190996>", "rimera song": "<:Pinkface:1430050553752190996>", "rimera track": "<:Pinkface:1430050553752190996>", "rimera album": "<:Pinkface:1430050553752190996>", "rimera artist": "<:Pinkface:1430050553752190996>", "rimera music artist": "<:Pinkface:1430050553752190996>", "rimerarimera": "<:Pinkface:1430050553752190996>", "rimera rimera": "<:Pinkface:1430050553752190996>", "the rimera": "<:Pinkface:1430050553752190996>", "that rimera": "<:Pinkface:1430050553752190996>", "rimera era": "<:Pinkface:1430050553752190996>", "rimera records": "<:Pinkface:1430050553752190996>", "rimera music artist": "<:Pinkface:1430050553752190996>", "rimera artist music": "<:Pinkface:1430050553752190996>",
    "cd": "<:TheCDKeeper:1482891305171554304>", "c.d.": "<:TheCDKeeper:1482891305171554304>", "cds": "<:TheCDKeeper:1482891305171554304>", "cd's": "<:TheCDKeeper:1482891305171554304>", "compact disc": "<:TheCDKeeper:1482891305171554304>", "compact disk": "<:TheCDKeeper:1482891305171554304>", "physical cd": "<:TheCDKeeper:1482891305171554304>", "music cd": "<:TheCDKeeper:1482891305171554304>", "album cd": "<:TheCDKeeper:1482891305171554304>", "rimera cd": "<:TheCDKeeper:1482891305171554304>", "rimera cds": "<:TheCDKeeper:1482891305171554304>", "cd album": "<:TheCDKeeper:1482891305171554304>", "cd copy": "<:TheCDKeeper:1482891305171554304>", "cd copy of": "<:TheCDKeeper:1482891305171554304>", "physical copy": "<:TheCDKeeper:1482891305171554304>", "physical music": "<:TheCDKeeper:1482891305171554304>", "physical album": "<:TheCDKeeper:1482891305171554304>", "disc copy": "<:TheCDKeeper:1482891305171554304>", "disc album": "<:TheCDKeeper:1482891305171554304>",
    "dense": "<:dense:1512748563648479342>", "dense music": "<:dense:1512748563648479342>", "dense song": "<:dense:1512748563648479342>", "dense track": "<:dense:1512748563648479342>", "dense album": "<:dense:1512748563648479342>", "the dense": "<:dense:1512748563648479342>", "that dense": "<:dense:1512748563648479342>", "dense era": "<:dense:1512748563648479342>", "dense project": "<:dense:1512748563648479342>", "dense record": "<:dense:1512748563648479342>", "dense rimera": "<:dense:1512748563648479342>", "rimera dense": "<:dense:1512748563648479342>", "dense music project": "<:dense:1512748563648479342>", "dense album era": "<:dense:1512748563648479342>", "dense record project": "<:dense:1512748563648479342>",
    "cw": "<:CAMPWANDER:1492324641556008970>", "c.w.": "<:CAMPWANDER:1492324641556008970>", "campwander": "<:CAMPWANDER:1492324641556008970>", "camp wander": "<:CAMPWANDER:1492324641556008970>", "camp-wander": "<:CAMPWANDER:1492324641556008970>", "camp_wander": "<:CAMPWANDER:1492324641556008970>", "camp wanderer": "<:CAMPWANDER:1492324641556008970>", "camp wander project": "<:CAMPWANDER:1492324641556008970>", "camp wander music": "<:CAMPWANDER:1492324641556008970>", "camp wander song": "<:CAMPWANDER:1492324641556008970>", "camp wander track": "<:CAMPWANDER:1492324641556008970>", "camp wander album": "<:CAMPWANDER:1492324641556008970>", "campwander music": "<:CAMPWANDER:1492324641556008970>", "campwander song": "<:CAMPWANDER:1492324641556008970>", "campwander track": "<:CAMPWANDER:1492324641556008970>", "campwander album": "<:CAMPWANDER:1492324641556008970>", "campwander project": "<:CAMPWANDER:1492324641556008970>", "cw music": "<:CAMPWANDER:1492324641556008970>", "cw song": "<:CAMPWANDER:1492324641556008970>", "cw track": "<:CAMPWANDER:1492324641556008970>", "cw album": "<:CAMPWANDER:1492324641556008970>", "cw project": "<:CAMPWANDER:1492324641556008970>", "cw music project": "<:CAMPWANDER:1492324641556008970>", "campwander music project": "<:CAMPWANDER:1492324641556008970>",
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
            logger.error("Discord rejected reaction %s on message %s. Check Add Reactions and Use External Emojis permissions and that the emoji is available to this server.", emoji_text, message.id)
        except discord.HTTPException as exc:
            logger.error("Failed to add reaction %s to message %s: %s", emoji_text, message.id, exc)
