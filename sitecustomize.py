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

# Install the reaction listener without adding a second Discord event loop or
# touching bot.py. sitecustomize is loaded before bot.py by normal Python startup.
try:
    from discord.ext import commands

    _original_bot_init = commands.Bot.__init__

    def _bot_init_with_keyword_reactions(self, *args, **kwargs):
        _original_bot_init(self, *args, **kwargs)
        try:
            from keyword_reactions import react_to_message
        except Exception:
            return

        original_on_message = self.on_message

        async def _on_message_with_keyword_reactions(message):
            await original_on_message(message)
            try:
                await react_to_message(message)
            except Exception:
                # Reactions are best-effort and must never interfere with the bot.
                pass

        self.on_message = _on_message_with_keyword_reactions

    commands.Bot.__init__ = _bot_init_with_keyword_reactions
except Exception:
    logging.getLogger("rimera-bot.sitecustomize").debug("Keyword reaction bootstrap unavailable", exc_info=True)
