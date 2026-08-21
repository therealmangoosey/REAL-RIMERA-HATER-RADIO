import glob
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import yt_dlp

DISCORD_FREE_LIMIT = 20 * 1024 * 1024
DISCORD_MAX_ATTACHMENTS = 10
URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)


class MediaDownloadError(Exception):
    pass


class MediaDownloader:
    """Download public media URLs, including multi-item Instagram posts/stories."""

    def __init__(self, max_bytes=DISCORD_FREE_LIMIT):
        self.max_bytes = max_bytes
        self.cookies_file = os.getenv("YT_DLP_COOKIES_FILE")

    @staticmethod
    def extract_urls(text):
        return [url.rstrip(".,!?)]}") for url in URL_RE.findall(text or "")]

    @staticmethod
    def _is_instagram(url):
        return "instagram.com/" in url.lower() or "instagr.am/" in url.lower()

    def _options(self, url, workdir):
        # Instagram URLs may expand to multiple media entries (carousels/stories).
        # Other platforms stay single-item unless their extractor returns a single
        # media entry itself.
        options = {
            "format": "bv*+ba/b",
            "merge_output_format": "mp4",
            "outtmpl": os.path.join(workdir, "%(playlist_index|0)03d-%(id)s.%(ext)s"),
            "noplaylist": not self._is_instagram(url),
            "quiet": True,
            "no_warnings": True,
            "restrictfilenames": True,
            "retries": 2,
            "fragment_retries": 2,
            "concurrent_fragment_downloads": 4,
            "socket_timeout": 15,
            "overwrites": True,
            "ignoreerrors": True,
        }
        # Optional cookies allow authorized access to login-gated Instagram media.
        if self.cookies_file and os.path.isfile(self.cookies_file):
            options["cookiefile"] = self.cookies_file
        return options

    def download(self, url):
        workdir = tempfile.mkdtemp(prefix="rimera-media-")
        options = self._options(url, workdir)

        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    raise MediaDownloadError("No media was returned by yt-dlp.")

            files = [
                path for path in glob.glob(os.path.join(workdir, "*"))
                if os.path.isfile(path) and not path.endswith(".part")
            ]
            if not files:
                raise MediaDownloadError("The platform returned no downloadable media.")

            files.sort()
            return workdir, files, info
        except Exception as exc:
            shutil.rmtree(workdir, ignore_errors=True)
            if isinstance(exc, MediaDownloadError):
                raise
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
                ffmpeg,
                "-y",
                "-i", path,
                "-vf", "scale='min(1280,iw)':-2",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "30",
                "-c:a", "aac",
                "-b:a", "96k",
                "-movflags", "+faststart",
                output,
            ]
            subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            if os.path.exists(output) and os.path.getsize(output) <= self.max_bytes:
                return output

        return None

    @staticmethod
    def cleanup(workdir):
        shutil.rmtree(workdir, ignore_errors=True)
