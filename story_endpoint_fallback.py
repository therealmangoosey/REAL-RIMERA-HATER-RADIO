import html
import logging
import os
import re
import time
from urllib.parse import urljoin, urlparse

import requests

logger = logging.getLogger("rimera-bot.story-endpoint-fallback")


class StoryEndpointFallback:
    """Lightweight, no-browser Story resolver."""

    PROVIDERS = (
        ("DownloadIGStory", "https://downloadigstory.com/"),
        ("StoryClone", "https://insta.storyclone.com/stories"),
        ("IGViewer", "https://igviewer.io/en"),
        ("PasteDL", "https://www.pastedl.com/instagram/stories"),
        ("SocialDawn", "https://www.socialdawn.com/instagram-story-downloader"),
        ("IGnony", "https://www.ignony.com/"),
    )
    ABS_URL = re.compile(r"https?://[^\"'<>\s]+", re.I)
    API_PATH = re.compile(r"[\"'](\/(?:api|ajax|graphql|v1|v2|fetch|download)[^\"']*)[\"']", re.I)
    ATTR_URL = re.compile(
        r"(?:href|src|data-src|data-media|data-video|data-image|data-file|data-download)=[\"']([^\"']+)[\"']",
        re.I,
    )
    MEDIA_EXTENSIONS = (".mp4", ".jpg", ".jpeg", ".png", ".webp", ".m4v", ".mov")
    MEDIA_TYPES = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "video/mp4": ".mp4",
        "video/quicktime": ".mov",
        "video/x-m4v": ".m4v",
    }

    def __init__(self, timeout=8, max_total_time=15):
        self.timeout = timeout
        self.max_total_time = max_total_time
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Linux; Android 11) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36",
            "Accept": "application/json,text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.instagram.com/",
        })

    @staticmethod
    def username_from_url(url):
        match = re.search(r"instagram\.com/(?:stories/)?([A-Za-z0-9._]+)/", url, re.I)
        return match.group(1) if match else None

    @staticmethod
    def _story_id(url):
        match = re.search(r"/stories/[A-Za-z0-9._]+/(\d+)", url, re.I)
        return match.group(1) if match else ""

    @classmethod
    def _is_media_url(cls, value):
        if not isinstance(value, str) or not value.startswith(("http://", "https://")):
            return False
        value = html.unescape(value).replace("\\/", "/").strip()
        parsed = urlparse(value)
        path = parsed.path.lower().rstrip("/")
        if not path:
            return False
        host = (parsed.hostname or "").lower()
        # Never treat Instagram's own page/assets as a downloaded source file.
        if host == "instagram.com" or host.endswith(".instagram.com"):
            return False
        if any(bad in path for bad in ("/logo", "/icon", "/favicon", "/screenshot", "/assets/", "/static/", "/css/", "/js/")):
            return False
        ext = any(path.endswith(item) for item in cls.MEDIA_EXTENSIONS)
        route = any(token in path for token in ("/media", "/download", "/story", "/video", "/photo", "/image", "/file"))
        return ext and route

    @classmethod
    def _embedded_story_urls(cls, text, story_id, page_url=""):
        """Return only provider-hosted media explicitly tied to this Story ID.

        Generic provider images, logos, thumbnails and profile assets are never
        accepted. A candidate must be in a Story-specific context containing the
        exact requested Story ID and must look like a real media source URL.
        """
        if not isinstance(text, str) or not story_id:
            return []
        text = html.unescape(text).replace("\\/", "/").replace("\\u0026", "&")
        found = []

        def add(candidate, context):
            candidate = html.unescape(candidate).replace("\\/", "/").strip()
            if candidate.startswith(("http://", "https://")):
                candidate = urljoin(page_url, candidate)
            parsed = urlparse(candidate)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                return
            if story_id.lower() not in context.lower():
                return
            if not cls._is_media_url(candidate):
                return
            found.append(candidate)

        for match in cls.ABS_URL.finditer(text):
            context = text[max(0, match.start() - 1200): min(len(text), match.end() + 1200)]
            add(match.group(0), context)

        for match in cls.ATTR_URL.finditer(text):
            context = text[max(0, match.start() - 1200): min(len(text), match.end() + 1200)]
            add(match.group(1), context)

        return list(dict.fromkeys(found))

    def _valid_media(self, path, content_type):
        try:
            with open(path, "rb") as fh:
                head = fh.read(32)
        except OSError:
            return False
        if content_type == "image/jpeg":
            return head.startswith(b"\xff\xd8\xff")
        if content_type == "image/png":
            return head.startswith(b"\x89PNG\r\n\x1a\n")
        if content_type == "image/webp":
            return head.startswith(b"RIFF") and b"WEBP" in head[:16]
        if content_type in {"video/mp4", "video/quicktime", "video/x-m4v"}:
            return len(head) >= 8 and head[4:8] == b"ftyp"
        return False

    def _download(self, urls, workdir, prefix, deadline):
        files = []
        seen = set()
        for url in urls:
            if time.monotonic() >= deadline:
                break
            if url in seen:
                continue
            seen.add(url)
            try:
                remaining = max(1, deadline - time.monotonic())
                response = self.session.get(url, stream=True, timeout=min(self.timeout, remaining), allow_redirects=True)
                response.raise_for_status()
                final_host = (urlparse(response.url).hostname or "").lower()
                if final_host == "instagram.com" or final_host.endswith(".instagram.com"):
                    response.close()
                    continue
                content_type = (response.headers.get("content-type") or "").split(";", 1)[0].lower().strip()
                extension = self.MEDIA_TYPES.get(content_type)
                if not extension:
                    response.close()
                    continue
                output = os.path.join(workdir, f"{prefix}-{len(files)+1:03d}{extension}")
                with open(output, "wb") as fh:
                    for chunk in response.iter_content(262144):
                        if time.monotonic() >= deadline:
                            break
                        if chunk:
                            fh.write(chunk)
                response.close()
                if time.monotonic() >= deadline:
                    try:
                        os.remove(output)
                    except OSError:
                        pass
                    break
                if os.path.getsize(output) <= 4096 or not self._valid_media(output, content_type):
                    try:
                        os.remove(output)
                    except OSError:
                        pass
                    continue
                files.append(output)
            except requests.RequestException:
                continue
        return files

    def _script_endpoints(self, page, deadline):
        endpoints = set()
        for src in re.findall(r"<script[^>]+src=[\"']([^\"']+)", page.text, re.I):
            if time.monotonic() >= deadline:
                break
            script_url = urljoin(page.url, html.unescape(src))
            try:
                remaining = max(1, deadline - time.monotonic())
                script = self.session.get(script_url, timeout=min(self.timeout, remaining))
            except requests.RequestException:
                continue
            if script.status_code >= 400:
                continue
            for path in self.API_PATH.findall(script.text):
                endpoints.add(urljoin(script_url, path))
            for absolute in self.ABS_URL.findall(script.text):
                if "/api/" in absolute or "/ajax/" in absolute or "/fetch" in absolute or "/download" in absolute:
                    endpoints.add(absolute)
        return list(endpoints)[:20]

    def _request_variants(self, endpoint, story_url, story_id, deadline):
        payloads = [
            {"url": story_url},
            {"instagram_url": story_url},
            {"story_url": story_url},
        ]
        if story_id:
            payloads.extend([
                {"story_id": story_id, "url": story_url},
                {"story_id": story_id},
            ])
        responses = []
        for payload in payloads:
            if time.monotonic() >= deadline:
                break
            remaining = max(1, deadline - time.monotonic())
            request_timeout = min(self.timeout, remaining)
            try:
                responses.append(self.session.post(endpoint, json=payload, timeout=request_timeout))
            except requests.RequestException:
                pass
            if time.monotonic() >= deadline:
                break
            remaining = max(1, deadline - time.monotonic())
            request_timeout = min(self.timeout, remaining)
            try:
                responses.append(self.session.post(endpoint, data=payload, timeout=request_timeout))
            except requests.RequestException:
                pass
            if time.monotonic() >= deadline:
                break
            remaining = max(1, deadline - time.monotonic())
            request_timeout = min(self.timeout, remaining)
            try:
                responses.append(self.session.get(endpoint, params=payload, timeout=request_timeout))
            except requests.RequestException:
                pass
        return responses

    def fetch(self, story_url, workdir):
        username = self.username_from_url(story_url)
        if not username:
            logger.warning("Rejected invalid Instagram Story URL: %s", story_url)
            return []
        story_id = self._story_id(story_url)
        deadline = time.monotonic() + self.max_total_time
        logger.info("Starting public Story resolver for %s (story_id=%s)", story_url, story_id or "unknown")

        for provider, homepage in self.PROVIDERS:
            if time.monotonic() >= deadline:
                break
            logger.info("Trying Story provider %s", provider)
            try:
                remaining = max(1, deadline - time.monotonic())
                page = self.session.get(homepage, timeout=min(self.timeout, remaining), allow_redirects=True)
                if page.status_code >= 400:
                    logger.info("Story provider %s returned HTTP %s", provider, page.status_code)
                    continue
            except requests.RequestException as exc:
                logger.info("Story provider %s request failed: %s", provider, exc)
                continue

            # Only exact Story-ID-linked source files are considered.
            media_urls = self._embedded_story_urls(page.text, story_id, page.url)
            files = self._download(media_urls, workdir, "instagram-story", deadline)
            if files:
                logger.info("%s direct Story-source extraction returned %d media item(s)", provider, len(files))
                return files

            endpoints = self._script_endpoints(page, deadline)
            for action in re.findall(r"<form[^>]+action=[\"']([^\"']+)[\"']", page.text, re.I):
                endpoints.append(urljoin(page.url, html.unescape(action)))
            endpoints = list(dict.fromkeys(endpoints))

            for endpoint in endpoints:
                if time.monotonic() >= deadline:
                    break
                for response in self._request_variants(endpoint, story_url, story_id, deadline):
                    if time.monotonic() >= deadline:
                        break
                    if response.status_code >= 400:
                        continue
                    # Parse raw response text only: this preserves the exact
                    # Story-ID context around each candidate and prevents
                    # unrelated provider logos/images from being selected.
                    candidates = self._embedded_story_urls(response.text, story_id, response.url)
                    files = self._download(candidates, workdir, "instagram-story", deadline)
                    if files:
                        logger.info("%s Story-source fallback returned %d media item(s)", provider, len(files))
                        return files

        logger.info("Public Story resolver finished without media for %s", story_url)
        return []
