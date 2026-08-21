import glob
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import parth_dl
import yt_dlp

from instagram_fallback import InstagramFallbackError, InstagramPublicFallback

DISCORD_FREE_LIMIT = 20 * 1024 * 1024
DISCORD_MAX_ATTACHMENTS = 10
URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)


class MediaDownloadError(Exception):
    pass


class MediaDownloader:
    """Download public media with platform-specific, validated fallbacks."""

    def __init__(self, max_bytes=DISCORD_FREE_LIMIT):
        self.max_bytes = max_bytes
        configured = os.getenv("YT_DLP_COOKIES_FILE", "").strip()
        candidates = [configured, "instagram-cookies.txt", os.path.expanduser("~/instagram-cookies.txt")]
        self.cookies_file = next((path for path in candidates if path and os.path.isfile(path)), None)
        self.instagram_fallback = InstagramPublicFallback()

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
        is_instagram = self._is_instagram(url)
        options = {
            "format": "bv*+ba/b",
            "merge_output_format": "mp4",
            "outtmpl": os.path.join(workdir, "%(playlist_index|0)03d-%(id)s.%(ext)s"),
            "noplaylist": not is_instagram,
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
            if os.path.isfile(path) and not path.endswith(".part")
        )

    def _extract(self, url, workdir, use_cookies=False):
        with yt_dlp.YoutubeDL(self._options(url, workdir, use_cookies)) as ydl:
            info = ydl.extract_info(url, download=True)
        return info, self._files(workdir)

    def _parth_dl_fallback(self, url, workdir):
        """Use parth-dl for public Instagram posts, reels and carousels."""
        try:
            result = parth_dl.download(
                url,
                output_path=workdir,
                quality="best",
                verbose=False,
            )
        except Exception as exc:
            logging.getLogger("rimera-bot").warning(
                "parth-dl Instagram fallback failed for %s: %s", url, exc
            )
            return []

        if result is None:
            return []
        if isinstance(result, (str, os.PathLike)):
            candidates = [os.fspath(result)]
        else:
            candidates = [os.fspath(item) for item in result if isinstance(item, (str, os.PathLike))]

        valid = []
        for path in candidates:
            if not os.path.isabs(path):
                path = os.path.join(workdir, path)
            if os.path.isfile(path) and os.path.getsize(path) > 4096:
                valid.append(path)
        return sorted(set(valid))

    def download(self, url):
        workdir = tempfile.mkdtemp(prefix="rimera-media-")
        try:
            anonymous_error = ""
            try:
                info, files = self._extract(url, workdir, use_cookies=False)
                if files:
                    return workdir, files, info
            except Exception as exc:
                anonymous_error = str(exc)
            else:
                anonymous_error = "yt-dlp returned no media"

            fallback_error = None

            if self._is_instagram_story(url):
                try:
                    files = self.instagram_fallback.fetch(url, workdir)
                    if files:
                        return workdir, files, {"source": "anonymous-instagram-story-fallback"}
                except InstagramFallbackError as exc:
                    fallback_error = str(exc)
                    logging.getLogger("rimera-bot").warning(
                        "Instagram anonymous Story fallback chain failed: %s", fallback_error
                    )
            elif self._instagram_post_or_reel(url):
                files = self._parth_dl_fallback(url, workdir)
                if files:
                    logging.getLogger("rimera-bot").info(
                        "parth-dl returned %d Instagram post media item(s)", len(files)
                    )
                    return workdir, files, {"source": "parth-dl-instagram-fallback"}
                fallback_error = "parth-dl returned no usable media"

            if self.cookies_file and self._is_instagram(url):
                try:
                    info, files = self._extract(url, workdir, use_cookies=True)
                    if files:
                        return workdir, files, info
                except Exception as cookie_error:
                    fallback_error = f"{fallback_error or 'public fallbacks failed'}; authenticated session: {cookie_error}"

            raise MediaDownloadError(
                f"Instagram media could not be downloaded. yt-dlp: {anonymous_error}. "
                f"Fallback: {fallback_error or 'no fallback returned media'}."
            )
        except MediaDownloadError:
            shutil.rmtree(workdir, ignore_errors=True)
            raise
        except Exception as exc:
            shutil.rmtree(workdir, ignore_errors=True)
            raise MediaDownloadError(str(exc)) from exc

    def fit_for_discord(self, path):
        if os.path.getsize(path) <= self.max_bytes:
            return path
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return None
        suffix = Path(path).suffix.lower()
        if suffix in {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}:
            output = f"{Path(path).stem}-discord.mp4"
            command = [
                ffmpeg, "-y", "-i", path,
                "-vf", "scale='min(1280,iw)':-2",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "30",
                "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", output,
            ]
            subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            if os.path.exists(output) and os.path.getsize(output) <= self.max_bytes:
                return output
        return None

    @staticmethod
    def cleanup(workdir):
        shutil.rmtree(workdir, ignore_errors=True)
