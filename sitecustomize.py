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
