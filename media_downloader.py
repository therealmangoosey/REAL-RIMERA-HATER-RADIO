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

DISCORD_FREE_LIMIT = 20_000_000
DISCORD_SAFE_MARGIN = 100_000
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

    @staticmethod
    def _safe_target(max_bytes):
        return max(1, int(max_bytes) - DISCORD_SAFE_MARGIN)

    @staticmethod
    def _video_duration(path):
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            return 0.0
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True,
            text=True,
            check=False,
        )
        try:
            return max(0.0, float(result.stdout.strip()))
        except (TypeError, ValueError):
            return 0.0

    def _compress_video(self, path, target_bytes):
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return None
        duration = self._video_duration(path)
        if duration <= 0:
            return None

        output = f"{Path(path).stem}-discord.mp4"
        audio_kbps = 96
        usable_bits = max(64_000, (target_bytes - 24_000) * 8)
        total_kbps = max(180, int(usable_bits / duration / 1000))
        video_kbps = max(80, total_kbps - audio_kbps)

        # Iteratively approach the largest safe size. Encoding overhead makes
        # exact byte equality impractical, so the target is the closest safe
        # size below Discord's limit rather than a risky one-byte-over upload.
        bitrate = video_kbps
        best = None
        for attempt in range(7):
            candidate = f"{Path(path).stem}-discord-{attempt}.mp4"
            command = [
                ffmpeg, "-y", "-i", path,
                "-map", "0:v:0", "-map", "0:a?",
                "-c:v", "libx264", "-preset", "slow",
                "-b:v", f"{int(bitrate)}k", "-maxrate", f"{int(bitrate)}k",
                "-bufsize", f"{int(max(2 * bitrate, 320))}k",
                "-c:a", "aac", "-b:a", f"{audio_kbps}k",
                "-movflags", "+faststart", candidate,
            ]
            subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            if not os.path.exists(candidate):
                bitrate *= 0.75
                continue
            size = os.path.getsize(candidate)
            if size <= target_bytes:
                if best and best != candidate:
                    try:
                        os.remove(best)
                    except OSError:
                        pass
                best = candidate
                if target_bytes - size <= 32_768:
                    break
                bitrate *= min(1.08, target_bytes / max(size, 1))
            else:
                try:
                    os.remove(candidate)
                except OSError:
                    pass
                bitrate *= max(0.55, (target_bytes / size) * 0.97)

        if best:
            os.replace(best, output)
            return output
        return None

    def _compress_image(self, path, target_bytes):
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return None
        output = f"{Path(path).stem}-discord.jpg"
        original = os.path.getsize(path)
        # Start high-quality and progressively reduce JPEG quality/resolution.
        quality = 95
        scale = 1.0
        best = None
        for attempt in range(9):
            candidate = f"{Path(path).stem}-discord-{attempt}.jpg"
            filters = []
            if scale < 0.999:
                filters.append(f"scale=trunc(iw*{scale}/2)*2:trunc(ih*{scale}/2)*2")
            vf = ["-vf", ",".join(filters)] if filters else []
            command = [
                ffmpeg, "-y", "-i", path, *vf,
                "-frames:v", "1", "-c:v", "mjpeg", "-q:v", str(max(2, quality)), candidate,
            ]
            subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            if not os.path.exists(candidate):
                quality -= 7
                continue
            size = os.path.getsize(candidate)
            if size <= target_bytes:
                if best and best != candidate:
                    try:
                        os.remove(best)
                    except OSError:
                        pass
                best = candidate
                if target_bytes - size <= 32_768:
                    break
                if original > target_bytes and scale > 0.7:
                    scale *= 0.97
                else:
                    quality -= 2
            else:
                try:
                    os.remove(candidate)
                except OSError:
                    pass
                quality = max(45, quality - 8)
                scale *= 0.94

        if best:
            os.replace(best, output)
            return output
        return None

    def fit_for_discord(self, path, max_bytes=None):
        """Return original or the highest-quality version that safely fits max_bytes."""
        limit = int(max_bytes or self.max_bytes)
        if os.path.getsize(path) <= limit:
            return path

        target = self._safe_target(limit)
        suffix = Path(path).suffix.lower()
        if suffix in {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}:
            return self._compress_video(path, target)
        if suffix in {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}:
            return self._compress_image(path, target)
        return None

    @staticmethod
    def cleanup(workdir):
        shutil.rmtree(workdir, ignore_errors=True)
