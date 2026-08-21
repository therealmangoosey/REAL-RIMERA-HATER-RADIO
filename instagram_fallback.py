import html
import json
import logging
import os
import re
from urllib.parse import quote_plus, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("rimera-bot.instagram-fallback")


class InstagramFallbackError(Exception):
    pass


class InstagramPublicFallback:
    """Anonymous Instagram fallback.

    Structured resolver first; webpage scraping only as a last resort.
    """

    STRUCTURED_RESOLVER = "https://www.smdownloader.com/api/extract"
    STORY_SERVICES = (
        ("DownloadIGStory", "https://downloadigstory.com", ("/{username}", "/?username={username}", "/?url={url}")),
        ("StoriesDown", "https://storiesdown.dev", ("/{username}", "/?username={username}", "/?url={url}")),
        ("PasteDL", "https://www.pastedl.com", ("/instagram/stories?username={username}", "/instagram/stories?url={url}")),
        ("SocialDawn", "https://www.socialdawn.com", ("/instagram-story-downloader?username={username}", "/instagram-story-downloader?url={url}")),
    )

    MEDIA_EXTENSIONS = (".mp4", ".jpg", ".jpeg", ".png", ".webp", ".m4v", ".mov")
    CDN_HOST_HINTS = ("scontent", "fbcdn", "cdninstagram", "igcdn")
    SERVICE_ASSET_PATHS = (
        "/static/", "/assets/", "/images/", "/img/", "/icons/", "/icon/", "/favicon",
        "/logo", "/logos/", "/css/", "/js/", "/fonts/", "/screenshots/", "/screenshot/",
    )
    BLOCKED_ASSET_HOSTS = (
        "googleusercontent.com", "googleapis.com", "gstatic.com", "google.com",
        "play.google.com", "microsoft.com", "windows.net", "bing.com",
        "apple.com", "mzstatic.com", "cloudflare.com",
    )
    MEDIA_PATH_HINTS = ("/download", "/media", "/file", "/video", "/photo", "/image", "/story", "/reel")
    ABSOLUTE_URL_RE = re.compile(r"https?://[^\"'<>\s]+", re.IGNORECASE)

    def __init__(self, timeout=20):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Linux; Android 11) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36",
            "Accept": "application/json,text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.instagram.com/",
        })

    @staticmethod
    def username_from_url(url):
        match = re.search(r"instagram\.com/(?:stories/)?([A-Za-z0-9._]+)/", url, re.IGNORECASE)
        return match.group(1) if match else None

    @classmethod
    def _looks_like_media_url(cls, value):
        if not isinstance(value, str):
            return False
        value = html.unescape(value).replace("\\/", "/").replace("\\u0026", "&").strip()
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"}:
            return False
        path = parsed.path.lower()
        hostname = (parsed.hostname or "").lower()
        if any(path.startswith(prefix) for prefix in cls.SERVICE_ASSET_PATHS):
            return False
        if any(hostname == host or hostname.endswith("." + host) for host in cls.BLOCKED_ASSET_HOSTS):
            return False
        if any(token in path for token in ("favicon", "logo", "icon", "placeholder", "app-store", "play-store", "microsoft-store")):
            return False
        is_cdn = any(hint in hostname for hint in cls.CDN_HOST_HINTS) or hostname.endswith(("fbcdn.net", "cdninstagram.com"))
        has_ext = any(path.endswith(ext) for ext in cls.MEDIA_EXTENSIONS)
        has_route = any(token in path for token in cls.MEDIA_PATH_HINTS)
        return bool(is_cdn and (has_ext or has_route) or (has_route and has_ext))

    @classmethod
    def _extract_urls_from_json(cls, payload):
        found = []
        def walk(value):
            if isinstance(value, dict):
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
            elif isinstance(value, str):
                cleaned = html.unescape(value).replace("\\/", "/").replace("\\u0026", "&")
                for match in cls.ABSOLUTE_URL_RE.findall(cleaned):
                    if cls._looks_like_media_url(match):
                        found.append(match)
                if cls._looks_like_media_url(cleaned):
                    found.append(cleaned)
        walk(payload)
        return list(dict.fromkeys(found))

    def _download_candidates(self, urls, output_dir, prefix):
        downloaded = []
        seen = set()
        for source_url in urls:
            if source_url in seen:
                continue
            seen.add(source_url)
            try:
                response = self.session.get(source_url, stream=True, timeout=self.timeout, allow_redirects=True)
                response.raise_for_status()
                content_type = (response.headers.get("content-type") or "").lower().split(";", 1)[0].strip()
                ext = {
                    "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "video/mp4": ".mp4"
                }.get(content_type)
                if not ext:
                    response.close()
                    continue
                output = os.path.join(output_dir, f"{prefix}-{len(downloaded)+1:03d}{ext}")
                with open(output, "wb") as handle:
                    for chunk in response.iter_content(chunk_size=262144):
                        if chunk:
                            handle.write(chunk)
                response.close()
                if os.path.getsize(output) <= 4096 or not self._valid_signature(output, content_type):
                    try:
                        os.remove(output)
                    except OSError:
                        pass
                    continue
                downloaded.append(output)
            except requests.RequestException:
                continue
        return downloaded

    @staticmethod
    def _valid_signature(path, content_type):
        try:
            with open(path, "rb") as handle:
                head = handle.read(32)
        except OSError:
            return False
        if content_type == "image/jpeg":
            return head.startswith(b"\xff\xd8\xff")
        if content_type == "image/png":
            return head.startswith(b"\x89PNG\r\n\x1a\n")
        if content_type == "image/webp":
            return head.startswith(b"RIFF") and b"WEBP" in head[:16]
        if content_type == "video/mp4":
            return len(head) >= 8 and head[4:8] == b"ftyp"
        return False

    def _structured_extract(self, instagram_url, output_dir, prefix):
        response = self.session.post(
            self.STRUCTURED_RESOLVER,
            json={"url": instagram_url},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        urls = self._extract_urls_from_json(payload)
        if not urls:
            return []
        files = self._download_candidates(urls, output_dir, prefix)
        if files:
            logger.info("SMDownloader structured resolver returned %d media item(s)", len(files))
        return files

    def _visit_variants(self, base, patterns, username, instagram_url):
        return [
            base + pattern.format(
                username=quote_plus(username or ""),
                url=quote_plus(instagram_url),
            )
            for pattern in patterns
        ]

    def _page_fallback(self, instagram_url, output_dir, prefix):
        """Last-resort page fallback. Only explicit download/media links are used."""
        errors = []
        username = self.username_from_url(instagram_url)
        variants = []
        for name, base, patterns in self.STORY_SERVICES:
            variants.extend((name, page) for page in self._visit_variants(base, patterns, username, instagram_url))

        for name, page_url in variants:
            try:
                page = self.session.get(page_url, timeout=self.timeout, allow_redirects=True)
                if page.status_code >= 400:
                    continue
                soup = BeautifulSoup(page.text, "lxml")
                links = []
                for tag in soup.find_all("a", href=True):
                    label = " ".join(tag.stripped_strings).lower()
                    if not any(word in label for word in ("download", "save media", "download media", "original")):
                        continue
                    href = urljoin(page.url, html.unescape(tag["href"]))
                    if self._looks_like_media_url(href):
                        links.append(href)
                files = self._download_candidates(links, output_dir, prefix)
                if files:
                    logger.info("%s page fallback returned %d media item(s)", name, len(files))
                    return files
            except requests.RequestException as exc:
                errors.append(f"{name}: {exc}")
        return []

    def fetch(self, instagram_url, output_dir):
        prefix = "instagram-story" if "/stories/" in instagram_url.lower() else "instagram-post"
        try:
            files = self._structured_extract(instagram_url, output_dir, prefix)
            if files:
                return files
        except (requests.RequestException, ValueError) as exc:
            logger.warning("SMDownloader structured resolver failed for %s: %s", instagram_url, exc)

        if "/stories/" in instagram_url.lower():
            files = self._page_fallback(instagram_url, output_dir, prefix)
            if files:
                return files
        raise InstagramFallbackError("No public Instagram fallback returned validated media.")
