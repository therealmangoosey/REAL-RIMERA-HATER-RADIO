import glob
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import requests
import yt_dlp
from bs4 import BeautifulSoup

from instagram_fallback import InstagramFallbackError, InstagramPublicStoryFallback

DISCORD_FREE_LIMIT = 20 * 1024 * 1024
DISCORD_MAX_ATTACHMENTS = 10
URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)


class MediaDownloadError(Exception):
    pass


class MediaDownloader:
    """Download media with platform-specific fallbacks."""

    def __init__(self, max_bytes=DISCORD_FREE_LIMIT):
        self.max_bytes = max_bytes
        configured = os.getenv("YT_DLP_COOKIES_FILE", "").strip()
        candidates = [configured, "instagram-cookies.txt", os.path.expanduser("~/instagram-cookies.txt")]
        self.cookies_file = next((path for path in candidates if path and os.path.isfile(path)), None)
        self.instagram_fallback = InstagramPublicStoryFallback()
        self.http = requests.Session()
        self.http.headers.update({
            "User-Agent": "Mozilla/5.0 (Linux; Android 11) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })

    @staticmethod
    def extract_urls(text):
        return [url.rstrip(".,!?)]}") for url in URL_RE.findall(text or "")]

    @staticmethod
    def _is_instagram(url):
        return "instagram.com/" in url.lower() or "instagr.am/" in url.lower()

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

    @staticmethod
    def _instagram_media_urls_from_html(response_text):
        soup = BeautifulSoup(response_text, "lxml")
        candidates = []

        for selector in (
            'meta[property="og:image"]',
            'meta[property="og:image:url"]',
            'meta[name="twitter:image"]',
            'meta[name="twitter:image:src"]',
        ):
            for tag in soup.select(selector):
                value = tag.get("content")
                if value:
                    candidates.append(value)

        # JSON-LD can contain image fields without requiring the brittle yt-dlp API path.
        for script in soup.find_all("script", type="application/ld+json"):
            text = script.string or script.get_text(" ", strip=False)
            if text:
                candidates.extend(re.findall(r'https?://[^"\\\']+', text))

        # Some Instagram HTML embeds CDN image URLs directly in scripts.
        for script in soup.find_all("script"):
            text = script.string or script.get_text(" ", strip=False)
            if not text:
                continue
            for match in re.findall(r'https?://[^"\\\']+', text):
                lower = match.lower()
                if any(token in lower for token in ("scontent", "fbcdn")):
                    candidates.append(match)

        result = []
        seen = set()
        for candidate in candidates:
            candidate = candidate.replace("\\/", "/").replace("\\u0026", "&").replace("&amp;", "&")
            if not candidate.startswith(("http://", "https://")) or candidate in seen:
                continue
            seen.add(candidate)
            result.append(candidate)
        return result

    def _instagram_photo_fallback(self, url, workdir):
        """Download public Instagram post images without requiring video extraction."""
        response = self.http.get(url, timeout=18, allow_redirects=True)
        response.raise_for_status()
        if "html" not in (response.headers.get("content-type") or "").lower():
            return []

        candidates = self._instagram_media_urls_from_html(response.text)
        downloaded = []
        for candidate in candidates:
            try:
                media = self.http.get(candidate, stream=True, timeout=18, allow_redirects=True)
                media.raise_for_status()
                media_type = (media.headers.get("content-type") or "").lower()
                if not media_type.startswith("image/"):
                    media.close()
                    continue
                extension = ".jpg"
                if "png" in media_type:
                    extension = ".png"
                elif "webp" in media_type:
                    extension = ".webp"
                output = os.path.join(workdir, f"instagram-photo-{len(downloaded)+1:03d}{extension}")
                with open(output, "wb") as handle:
                    for chunk in media.iter_content(chunk_size=262144):
                        if chunk:
                            handle.write(chunk)
                media.close()
                if os.path.getsize(output) > 1024:
                    downloaded.append(output)
            except requests.RequestException:
                continue
        return downloaded

    def _instagram_public_post_fallbacks(self, url, workdir):
        """Try photo metadata after yt-dlp, including a public-page HTML route."""
        errors = []
        try:
            files = self._instagram_photo_fallback(url, workdir)
            if files:
                return files
            errors.append("no public image metadata")
        except Exception as exc:
            errors.append(str(exc))

        # A trailing slash/no-query variant can expose the public OG metadata even
        # when Instagram's redirect/API response is problematic.
        try:
            parsed = urlparse(url)
            clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if clean_url != url:
                files = self._instagram_photo_fallback(clean_url, workdir)
                if files:
                    return files
                errors.append("clean URL contained no public image metadata")
        except Exception as exc:
            errors.append(str(exc))
        return []

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
                        return workdir, files, {"source": "anonymous-web-fallback"}
                except InstagramFallbackError as exc:
                    fallback_error = str(exc)
                    logging.getLogger("rimera-bot").warning(
                        "Instagram anonymous Story fallback chain failed: %s", fallback_error
                    )
            elif self._instagram_post_or_reel(url):
                try:
                    files = self._instagram_public_post_fallbacks(url, workdir)
                    if files:
                        return workdir, files, {"source": "anonymous-instagram-photo"}
                    fallback_error = "public Instagram photo metadata returned no usable image"
                except Exception as exc:
                    fallback_error = str(exc)
                    logging.getLogger("rimera-bot").warning(
                        "Instagram public photo fallback failed: %s", fallback_error
                    )

            if self.cookies_file:
                try:
                    info, files = self._extract(url, workdir, use_cookies=True)
                    if files:
                        return workdir, files, info
                except Exception as cookie_error:
                    if self._is_instagram_story(url):
                        raise MediaDownloadError(
                            "Instagram Story could not be downloaded. "
                            f"Anonymous yt-dlp: {anonymous_error}. "
                            f"Public fallbacks: {fallback_error or 'none returned media'}. "
                            f"Authenticated session: {cookie_error}"
                        ) from cookie_error

            if self._is_instagram_story(url):
                raise MediaDownloadError(
                    "Instagram Story could not be downloaded. "
                    f"Anonymous yt-dlp: {anonymous_error}. "
                    f"Public fallbacks: {fallback_error or 'no fallback media returned'}."
                )
            if self._instagram_post_or_reel(url):
                raise MediaDownloadError(
                    "Instagram post/reel could not be downloaded. "
                    f"yt-dlp: {anonymous_error}. Public photo fallback: {fallback_error or 'not available'}."
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
