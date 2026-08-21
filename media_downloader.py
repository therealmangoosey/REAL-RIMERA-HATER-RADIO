import glob
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import yt_dlp

DISCORD_FREE_LIMIT = 20 * 1024 * 1024
URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)


class MediaDownloadError(Exception):
    pass


class MediaDownloader:
    """Download public media URLs with yt-dlp and return local files."""

    def __init__(self, max_bytes=DISCORD_FREE_LIMIT):
        self.max_bytes = max_bytes

    @staticmethod
    def extract_urls(text):
        return [url.rstrip(".,!?)]}") for url in URL_RE.findall(text or "")]

    def download(self, url):
        workdir = tempfile.mkdtemp(prefix="rimera-media-")
        output_template = os.path.join(workdir, "%(id)s.%(ext)s")

        options = {
            "format": "bv*+ba/b",
            "merge_output_format": "mp4",
            "outtmpl": output_template,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "restrictfilenames": True,
            "retries": 2,
            "fragment_retries": 2,
            "concurrent_fragment_downloads": 4,
            "socket_timeout": 15,
            "overwrites": True,
        }

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

            files.sort(key=lambda path: os.path.getsize(path), reverse=True)
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
