import glob
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import yt_dlp

from instagram_fallback import InstagramFallbackError, InstagramPublicStoryFallback

DISCORD_FREE_LIMIT = 20 * 1024 * 1024
DISCORD_MAX_ATTACHMENTS = 10
URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)


class MediaDownloadError(Exception):
    pass


class MediaDownloader:
    """Download media, trying anonymous yt-dlp first and public fallbacks second."""

    def __init__(self, max_bytes=DISCORD_FREE_LIMIT):
        configured = os.getenv("YT_DLP_COOKIES_FILE", "").strip()
        candidates = [configured, "instagram-cookies.txt", os.path.expanduser("~/instagram-cookies.txt")]
        self.cookies_file = next((path for path in candidates if path and os.path.isfile(path)), None)
        self.instagram_fallback = InstagramPublicStoryFallback()

    @staticmethod
    def extract_urls(text):
        return [url.rstrip(".,!?)]}") for url in URL_RE.findall(text or "")]

    @staticmethod
    def _is_instagram(url):
        return "instagram.com/" in url.lower() or "instagr.am/" in url.lower()

    @staticmethod
    def _is_instagram_story(url):
        return "/stories/" in url.lower()

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

    def download(self, url):
        workdir = tempfile.mkdtemp(prefix="rimera-media-")
        try:
            # 1. Anonymous yt-dlp first.
            try:
                info, files = self._extract(url, workdir, use_cookies=False)
                if files:
                    return workdir, files, info
            except Exception as exc:
                anonymous_error = str(exc)
            else:
                anonymous_error = "yt-dlp returned no media"

            # 2. Free anonymous public Story web fallback for Instagram Stories.
            if self._is_instagram_story(url):
                try:
                    files = self.instagram_fallback.fetch(url, workdir)
                    if files:
                        return workdir, files, {"source": "anonymous-web-fallback"}
                except InstagramFallbackError:
                    pass

            # 3. Optional authorized cookie fallback last.
            if self.cookies_file:
                try:
                    info, files = self._extract(url, workdir, use_cookies=True)
                    if files:
                        return workdir, files, info
                except Exception as cookie_error:
                    if self._is_instagram_story(url):
                        raise MediaDownloadError(
                            f"Instagram Story could not be accessed anonymously or with the configured session: {cookie_error}"
                        ) from cookie_error

            if self._is_instagram_story(url):
                raise MediaDownloadError(
                    f"Instagram Story is not publicly accessible. Anonymous download failed: {anonymous_error}"
                )
            raise MediaDownloadError(f"No media was returned by yt-dlp: {anonymous_error}")
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
