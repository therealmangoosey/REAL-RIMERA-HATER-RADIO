import html
import logging
import os
import re
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("rimera-bot.story-endpoint-fallback")


class StoryEndpointFallback:
    """Resolve public Instagram Stories through verified free Story providers."""

    PROVIDERS = (
        ("PasteDL", "https://www.pastedl.com/instagram/stories"),
        ("EnSaver", "https://ensaver.net/instagram-story-downloader"),
        ("DownloadIGStory", "https://downloadigstory.com/"),
        ("StoryClone", "https://insta.storyclone.com/stories"),
        ("SocialDawn", "https://www.socialdawn.com/instagram-story-downloader"),
        ("IGnony", "https://www.ignony.com/"),
    )
    URL_RE = re.compile(r"https?://[^\"'<>\s]+", re.I)
    MEDIA_EXTENSIONS = (".mp4", ".jpg", ".jpeg", ".png", ".webp", ".m4v", ".mov")
    MEDIA_TYPES = {
        "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
        "video/mp4": ".mp4", "video/quicktime": ".mov", "video/x-m4v": ".m4v",
    }
    BAD_PATHS = (
        "/assets/", "/static/", "/css/", "/js/", "/fonts/", "/favicon", "/logo",
        "/icon", "/avatar", "/profile", "/banner", "/badge", "/button",
        "/placeholder", "/sprite", "/thumbnail", "/thumb/", "/screenshot",
    )
    MEDIA_HINTS = (
        "download", "media", "video", "image", "photo", "story", "file",
        "source", "original", "direct", "attachment",
    )

    def __init__(self, timeout=8, max_total_time=20):
        self.timeout = timeout
        self.max_total_time = max_total_time
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Linux; Android 11) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
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
    def _is_media_url(cls, value, allow_plain_media=False):
        if not isinstance(value, str) or not value.startswith(("http://", "https://")):
            return False
        value = html.unescape(value).replace("\\/", "/").strip()
        parsed = urlparse(value)
        path = parsed.path.lower()
        if not path or any(marker in path for marker in cls.BAD_PATHS):
            return False
        host = (parsed.hostname or "").lower()
        if host == "instagram.com" or host == "www.instagram.com" or host.endswith(".instagram.com"):
            return False
        if any(token in host for token in ("cdninstagram", "fbcdn", "scontent", "igcdn")):
            return True
        if path.endswith(cls.MEDIA_EXTENSIONS):
            return allow_plain_media or any(token in path for token in ("/media", "/download", "/story", "/video", "/photo", "/image", "/file"))
        return False

    @classmethod
    def _collect_media_urls(cls, payload):
        found = []

        def walk(value, hint=""):
            normalized_hint = str(hint or "").lower()
            explicit = any(token in normalized_hint for token in cls.MEDIA_HINTS)
            if isinstance(value, dict):
                for key, child in value.items():
                    walk(child, key)
            elif isinstance(value, list):
                for child in value:
                    walk(child, hint)
            elif isinstance(value, str):
                text = html.unescape(value).replace("\\/", "/").replace("\\u0026", "&").strip()
                candidates = cls.URL_RE.findall(text)
                if explicit and text.startswith(("http://", "https://")):
                    candidates.append(text)
                for candidate in candidates:
                    if cls._is_media_url(candidate, allow_plain_media=explicit):
                        found.append(candidate)

        walk(payload)
        return list(dict.fromkeys(found))

    @classmethod
    def _embedded_story_urls(cls, html_text, story_id):
        """Extract media URLs only when they are tied to the requested Story ID."""
        text = html.unescape(html_text or "").replace("\\/", "/").replace("\\u0026", "&")
        found = []
        story_id = str(story_id or "")
        soup = BeautifulSoup(text, "lxml")

        for tag in soup.find_all(True):
            attrs = tag.attrs or {}
            tag_story_id = str(attrs.get("data-story-id", ""))
            if story_id and tag_story_id != story_id:
                continue
            for attr in ("data-video", "data-media", "data-image", "data-file", "data-download", "data-src"):
                value = attrs.get(attr)
                if isinstance(value, str) and value.startswith(("http://", "https://")):
                    value = html.unescape(value).replace("\\/", "/").strip()
                    if cls._is_media_url(value, allow_plain_media=True):
                        found.append(value)

        if story_id:
            for match in cls.URL_RE.finditer(text):
                candidate = match.group(0)
                context = text[max(0, match.start() - 1200):min(len(text), match.end() + 1200)]
                if story_id in context and cls._is_media_url(candidate, allow_plain_media=True):
                    found.append(candidate)

        return list(dict.fromkeys(found))

    @classmethod
    def _extract_candidates(cls, response, story_id, trusted_result=False):
        text = html.unescape(response.text).replace("\\/", "/").replace("\\u0026", "&")
        candidates = []
        try:
            candidates.extend(cls._collect_media_urls(response.json()))
        except (ValueError, requests.exceptions.JSONDecodeError):
            pass
        candidates.extend(cls._embedded_story_urls(text, story_id))

        soup = BeautifulSoup(text, "lxml")
        for tag in soup.find_all(["video", "source", "a"]):
            for attr in ("src", "href", "data-src", "data-media", "data-video", "data-image", "data-file", "data-download"):
                value = tag.get(attr)
                if not value:
                    continue
                candidate = urljoin(response.url, html.unescape(value).strip())
                label = (" ".join(tag.stripped_strings) + " " + str(tag.attrs)).lower()
                if cls._is_media_url(candidate, allow_plain_media=trusted_result) and (trusted_result or any(h in label for h in cls.MEDIA_HINTS)):
                    candidates.append(candidate)

        return list(dict.fromkeys(candidates))

    def _submit_forms(self, page, story_url, username, deadline):
        responses = []
        soup = BeautifulSoup(page.text, "lxml")
        for form in soup.find_all("form"):
            if time.monotonic() >= deadline:
                break
            fields = {}
            for control in form.find_all(["input", "textarea", "select"]):
                name = control.get("name")
                if not name:
                    continue
                hint = " ".join([name.lower(), (control.get("placeholder") or "").lower(), (control.get("aria-label") or "").lower()])
                value = control.get("value", "")
                if any(x in hint for x in ("story", "url", "link", "input", "query", "search", "text")):
                    value = story_url
                elif any(x in hint for x in ("username", "handle", "user", "profile")):
                    value = username
                fields[name] = value
            if not fields:
                continue
            action = urljoin(page.url, form.get("action") or page.url)
            method = (form.get("method") or "get").lower()
            try:
                remaining = max(1, deadline - time.monotonic())
                result = self.session.post(action, data=fields, timeout=min(self.timeout, remaining), allow_redirects=True) if method == "post" else self.session.get(action, params=fields, timeout=min(self.timeout, remaining), allow_redirects=True)
                responses.append((result, True))
            except requests.RequestException:
                continue
        return responses

    def _submit_generic_requests(self, page, story_url, username, deadline):
        responses = []
        for key in ("url", "link", "query", "q", "text", "input", "search", "instagram_url", "story_url"):
            if time.monotonic() >= deadline:
                break
            for method in ("get", "post"):
                try:
                    remaining = max(1, deadline - time.monotonic())
                    kwargs = {"params": {key: story_url}} if method == "get" else {"data": {key: story_url}}
                    responses.append((getattr(self.session, method)(page.url, timeout=min(self.timeout, remaining), allow_redirects=True, **kwargs), True))
                except requests.RequestException:
                    continue
        return responses

    def _download(self, urls, workdir, deadline):
        files = []
        for url in list(dict.fromkeys(urls)):
            if time.monotonic() >= deadline:
                break
            try:
                remaining = max(1, deadline - time.monotonic())
                response = self.session.get(url, stream=True, timeout=min(self.timeout, remaining), allow_redirects=True)
                response.raise_for_status()
                content_type = (response.headers.get("content-type") or "").split(";", 1)[0].lower().strip()
                ext = self.MEDIA_TYPES.get(content_type)
                if not ext:
                    response.close()
                    continue
                path = os.path.join(workdir, f"instagram-story-{len(files)+1:03d}{ext}")
                with open(path, "wb") as handle:
                    for chunk in response.iter_content(262144):
                        if time.monotonic() >= deadline:
                            break
                        if chunk:
                            handle.write(chunk)
                response.close()
                if time.monotonic() >= deadline or os.path.getsize(path) <= 4096:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                    continue
                with open(path, "rb") as handle:
                    head = handle.read(32)
                valid = ((content_type == "image/jpeg" and head.startswith(b"\xff\xd8\xff")) or (content_type == "image/png" and head.startswith(b"\x89PNG\r\n\x1a\n")) or (content_type == "image/webp" and head.startswith(b"RIFF") and b"WEBP" in head[:16]) or (content_type in {"video/mp4", "video/quicktime", "video/x-m4v"} and len(head) >= 8 and head[4:8] == b"ftyp"))
                if valid:
                    files.append(path)
                else:
                    os.remove(path)
            except (requests.RequestException, OSError):
                continue
        return files

    def fetch(self, story_url, workdir):
        username = self.username_from_url(story_url)
        if not username:
            return []
        story_id = self._story_id(story_url)
        deadline = time.monotonic() + self.max_total_time
        for name, homepage in self.PROVIDERS:
            if time.monotonic() >= deadline:
                break
            try:
                remaining = max(1, deadline - time.monotonic())
                page = self.session.get(homepage, timeout=min(self.timeout, remaining), allow_redirects=True)
                page.raise_for_status()
            except requests.RequestException:
                continue
            submissions = self._submit_forms(page, story_url, username, deadline)
            submissions.extend(self._submit_generic_requests(page, story_url, username, deadline))
            for response, trusted in submissions:
                if time.monotonic() >= deadline:
                    break
                files = self._download(self._extract_candidates(response, story_id, trusted_result=trusted), workdir, deadline)
                if files:
                    logger.info("%s returned %d validated Story media file(s)", name, len(files))
                    return files
        return []
