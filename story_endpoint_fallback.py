import html
import json
import logging
import os
import re
import time
from urllib.parse import urljoin, urlparse

import requests

logger = logging.getLogger("rimera-bot.story-endpoint-fallback")


class StoryEndpointFallback:
    """Lightweight, no-browser Story resolver with a hard overall timeout."""

    PROVIDERS = (
        ("DownloadIGStory", "https://downloadigstory.com/"),
        ("StoryClone", "https://insta.storyclone.com/stories"),
        ("IGViewer", "https://igviewer.io/en"),
        ("PasteDL", "https://www.pastedl.com/instagram/stories"),
        ("SocialDawn", "https://www.socialdawn.com/instagram-story-downloader"),
        ("IGnony", "https://www.ignony.com/"),
    )
    ABS_URL = re.compile(r"https?://[^\"'<>\\s]+", re.I)
    API_PATH = re.compile(r"[\"'](\/(?:api|ajax|graphql|v1|v2|fetch|download)[^\"']*)[\"']", re.I)
    MEDIA_EXTENSIONS = (".mp4", ".jpg", ".jpeg", ".png", ".webp", ".m4v", ".mov")
    MEDIA_TYPES = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "video/mp4": ".mp4",
        "video/quicktime": ".mov",
        "video/x-m4v": ".m4v",
    }

    def __init__(self, timeout=20, max_fetch_seconds=45):
        self.timeout = timeout
        self.max_fetch_seconds = max_fetch_seconds
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
        if any(bad in path for bad in ("/logo", "/icon", "/favicon", "/screenshot", "/assets/", "/static/", "/css/", "/js/")):
            return False
        host = (parsed.hostname or "").lower()
        cdn = any(token in host for token in ("cdninstagram", "fbcdn", "scontent", "igcdn"))
        ext = any(path.endswith(item) for item in cls.MEDIA_EXTENSIONS)
        route = any(token in path for token in ("/media", "/download", "/story", "/video", "/photo", "/image", "/file"))
        return cdn or (ext and route)

    @classmethod
    def _collect_media_urls(cls, value):
        found = []

        def add_candidate(candidate):
            if not isinstance(candidate, str):
                return
            candidate = html.unescape(candidate).replace("\\/", "/").strip()
            parsed = urlparse(candidate)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                return
            path = parsed.path.rstrip("/")
            if not path:
                return
            found.append(candidate)

        def walk(obj, key_hint=""):
            key = str(key_hint).lower()
            media_context = any(token in key for token in ("media", "download", "video", "image", "photo", "story", "file", "source", "url", "href"))
            if isinstance(obj, dict):
                for k, v in obj.items():
                    walk(v, k)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item, key_hint)
            elif isinstance(obj, str):
                text = html.unescape(obj).replace("\\/", "/")
                for candidate in cls.ABS_URL.findall(text):
                    if media_context or cls._is_media_url(candidate):
                        add_candidate(candidate)
                if media_context and text.startswith(("http://", "https://")):
                    add_candidate(text)

        walk(value)
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

    def _download(self, urls, workdir, prefix):
        files = []
        seen = set()
        for url in urls:
            if url in seen:
                continue
            seen.add(url)
            try:
                response = self.session.get(url, stream=True, timeout=self.timeout, allow_redirects=True)
                response.raise_for_status()
                content_type = (response.headers.get("content-type") or "").split(";", 1)[0].lower().strip()
                extension = self.MEDIA_TYPES.get(content_type)
                if not extension:
                    response.close()
                    continue
                output = os.path.join(workdir, f"{prefix}-{len(files)+1:03d}{extension}")
                with open(output, "wb") as fh:
                    for chunk in response.iter_content(262144):
                        if chunk:
                            fh.write(chunk)
                response.close()
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

    def _script_endpoints(self, page):
        endpoints = set()
        for src in re.findall(r"<script[^>]+src=[\"']([^\"']+)", page.text, re.I):
            script_url = urljoin(page.url, html.unescape(src))
            try:
                script = self.session.get(script_url, timeout=self.timeout)
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

    def _request_variants(self, endpoint, username, story_url, story_id):
        payloads = [
            {"url": story_url}, {"instagram_url": story_url}, {"story_url": story_url},
            {"username": username}, {"handle": username}, {"user": username},
            {"url": story_url, "username": username},
            {"username": username, "story_id": story_id},
            {"story_id": story_id, "url": story_url},
        ]
        responses = []
        for payload in payloads:
            try:
                responses.append(self.session.post(endpoint, json=payload, timeout=self.timeout))
            except requests.RequestException:
                pass
            try:
                responses.append(self.session.post(endpoint, data=payload, timeout=self.timeout))
            except requests.RequestException:
                pass
            try:
                responses.append(self.session.get(endpoint, params=payload, timeout=self.timeout))
            except requests.RequestException:
                pass
        return responses

    def fetch(self, story_url, workdir):
        username = self.username_from_url(story_url)
        if not username:
            return []
        story_id = self._story_id(story_url)
        deadline = time.monotonic() + self.max_fetch_seconds

        for provider, homepage in self.PROVIDERS:
            if time.monotonic() >= deadline:
                logger.warning("Story fallback timed out after %ss for %s", self.max_fetch_seconds, story_url)
                break
            try:
                remaining = max(1, min(self.timeout, int(deadline - time.monotonic())))
                page = self.session.get(homepage, timeout=remaining, allow_redirects=True)
                if page.status_code >= 400:
                    continue
            except requests.RequestException:
                continue

            endpoints = self._script_endpoints(page)
            for action in re.findall(r"<form[^>]+action=[\"']([^\"']+)", page.text, re.I):
                endpoints.append(urljoin(page.url, html.unescape(action)))
            endpoints = list(dict.fromkeys(endpoints))

            for endpoint in endpoints:
                if time.monotonic() >= deadline:
                    break
                for response in self._request_variants(endpoint, username, story_url, story_id):
                    if time.monotonic() >= deadline:
                        break
                    if response.status_code >= 400:
                        continue
                    media_urls = []
                    try:
                        media_urls.extend(self._collect_media_urls(response.json()))
                    except ValueError:
                        for match in self.ABS_URL.findall(response.text):
                            if self._is_media_url(match):
                                media_urls.append(match)
                    files = self._download(media_urls, workdir, "instagram-story")
                    if files:
                        logger.info("%s JS/API fallback returned %d Story media item(s)", provider, len(files))
                        return files

        return []
