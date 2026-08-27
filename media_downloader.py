import glob
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp

from instagram_fallback import InstagramFallbackError, InstagramPublicFallback
from story_endpoint_fallback import StoryEndpointFallback

DISCORD_FREE_LIMIT = 20_000_000
DISCORD_SAFE_MARGIN = 4_096
DISCORD_MAX_ATTACHMENTS = 10
URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)


class MediaDownloadError(Exception):
    pass


class MediaDownloader:
    """Download public media with validated fallbacks and Discord-safe compression."""

    def __init__(self, max_bytes=DISCORD_FREE_LIMIT):
        self.max_bytes = max_bytes
        configured = os.getenv("YT_DLP_COOKIES_FILE", "").strip()
        candidates = [configured, "instagram-cookies.txt", os.path.expanduser("~/instagram-cookies.txt")]
        self.cookies_file = next((path for path in candidates if path and os.path.isfile(path)), None)
        self.instagram_fallback = InstagramPublicFallback()
        self.story_endpoint_fallback = StoryEndpointFallback()

    @staticmethod
    def extract_urls(text):
        return [url.rstrip(".,!?)]}") for url in URL_RE.findall(text or "")]

    @staticmethod
    def _is_instagram(url):
        lowered = url.lower()
        return "instagram.com/" in lowered or "instagr.am/" in lowered

    @staticmethod
    def _is_instagram_story(url):
        return "/stories/" in url.lower()

    @staticmethod
    def _instagram_post_or_reel(url):
        path = urlparse(url).path.lower()
        return any(path.startswith(prefix) for prefix in ("/p/", "/reel/", "/reels/", "/tv/"))

    def _options(self, url, workdir, use_cookies=False):
        options = {
            "format": "bv*+ba/b",
            "merge_output_format": "mp4",
            "outtmpl": os.path.join(workdir, "%(playlist_index|0)03d-%(id)s.%(ext)s"),
            "noplaylist": not self._is_instagram(url),
            "quiet": True,
            "no_warnings": False,
            "restrictfilenames": True,
            "retries": 2,
            "fragment_retries": 2,
            "concurrent_fragment_downloads": 4,
            "socket_timeout": 15,
            "overwrites": True,
            "ignoreerrors": False,
            "impersonate": [],
        }
        if use_cookies and self.cookies_file:
            options["cookiefile"] = self.cookies_file
        return options

    @staticmethod
    def _files(workdir):
        return sorted(
            path for path in glob.glob(os.path.join(workdir, "*"))
            if os.path.isfile(path)
        )
