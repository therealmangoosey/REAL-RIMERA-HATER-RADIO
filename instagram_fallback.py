import html
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
    """Anonymous Instagram fallback with a dedicated Story resolver path."""

    STRUCTURED_RESOLVER = "https://www.smdownloader.com/api/extract"
    STORY_SERVICES = (
        ("PasteDL", "https://www.pastedl.com", ("/instagram/stories", "/instagram/story")),
        ("DownloadIGStory", "https://downloadigstory.com", ("/",)),
        ("StoriesDown", "https://storiesdown.dev", ("/",)),
        ("SocialDawn", "https://www.socialdawn.com", ("/instagram-story-downloader",)),
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
    STRUCTURED_MEDIA_KEYS = {
        "media", "medias", "items", "results", "data", "downloads", "download",
        "download_url", "downloadurl", "media_url", "mediaurl", "video_url", "videourl",
        "image_url", "imageurl", "story_url", "storyurl", "file_url", "fileurl", "source",
        "src", "href", "url", "video", "image", "photo", "story", "stories",
    }

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
        return bool((is_cdn and (has_ext or has_route)) or (has_route and has_ext))

    @classmethod
    def _structured_urls(cls, payload):
        found = []

        def walk(value, key_hint=""):
            normalized_hint = str(key_hint or "").lower().replace("-", "_")
            media_context = normalized_hint in cls.STRUCTURED_MEDIA_KEYS or any(
                token in normalized_hint for token in ("download", "media", "video", "image", "photo", "story", "file", "source")
            )
            if isinstance(value, dict):
                for key, child in value.items():
                    walk(child, key)
            elif isinstance(value, list):
                for child in value:
                    walk(child, key_hint)
            elif isinstance(value, str):
                cleaned = html.unescape(value).replace("\\/", "/").replace("\\u0026", "&").strip()
                matches = cls.ABSOLUTE_URL_RE.findall(cleaned)
                for match in matches:
                    if media_context or cls._looks_like_media_url(match):
                        found.append(match)
                if media_context and cleaned.startswith(("http://", "https://")):
                    found.append(cleaned)

        walk(payload)
        return list(dict.fromkeys(found))

    @classmethod
    def _extract_urls_from_json(cls, payload):
        return [url for url in cls._structured_urls(payload) if cls._looks_like_media_url(url)]

    def _download_candidates(self, urls, output_dir, prefix, allow_unclassified=False):
        """Download candidate targets and validate the resulting bytes.

        ``allow_unclassified`` is retained for compatibility with the regression tests and
        callers; the final response MIME type and file signature are always required.
        """
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
                    "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "video/mp4": ".mp4",
                    "video/quicktime": ".mov", "video/x-m4v": ".m4v",
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
        if content_type in {"video/mp4", "video/quicktime", "video/x-m4v"}:
            return len(head) >= 8 and head[4:8] == b"ftyp"
        return False

    def _structured_extract(self, instagram_url, output_dir, prefix, username=None):
        responses = []
        payloads = [{"url": instagram_url}, {"instagram_url": instagram_url}]
        if username:
            payloads.append({"username": username})
        for payload in payloads:
            try:
                responses.append(self.session.post(self.STRUCTURED_RESOLVER, json=payload, timeout=self.timeout))
            except requests.RequestException:
                pass
        params_list = [{"url": instagram_url}, {"instagram_url": instagram_url}]
        if username:
            params_list.append({"username": username})
        for params in params_list:
            try:
                responses.append(self.session.get(self.STRUCTURED_RESOLVER, params=params, timeout=self.timeout))
            except requests.RequestException:
                pass
        for response in responses:
            try:
                response.raise_for_status()
                payload = response.json()
            except (requests.RequestException, ValueError):
                continue
            urls = self._structured_urls(payload)
            if not urls:
                continue
            files = self._download_candidates(urls, output_dir, prefix, allow_unclassified=True)
            if files:
                logger.info("SMDownloader structured resolver returned %d media item(s)", len(files))
                return files
        return []

    @staticmethod
    def _form_fields(form, username, instagram_url):
        fields = {}
        for control in form.find_all(["input", "textarea"]):
            name = control.get("name")
            if not name:
                continue
            input_type = (control.get("type") or "text").lower()
            if input_type in {"submit", "button", "reset", "file"}:
                continue
            fields[name] = control.get("value", "")
            hint = " ".join([
                name.lower(),
                (control.get("placeholder") or "").lower(),
                (control.get("aria-label") or "").lower(),
            ])
            if any(token in hint for token in ("username", "handle", "user", "profile")):
                fields[name] = username or ""
            elif any(token in hint for token in ("story", "url", "link")):
                fields[name] = instagram_url
        return fields

    def _extract_page_candidates(self, page):
        soup = BeautifulSoup(page.text, "lxml")
        candidates = []
        for tag in soup.find_all(["video", "source", "audio"]):
            for attr in ("src", "data-src", "data-download", "data-media", "data-video", "data-file"):
                value = tag.get(attr)
                if value:
                    candidates.append(urljoin(page.url, html.unescape(value)))
        for tag in soup.find_all(True):
            for attr in ("data-download", "data-media", "data-video", "data-image", "data-file"):
                value = tag.get(attr)
                if value:
                    candidates.append(urljoin(page.url, html.unescape(value)))
        for tag in soup.find_all("a", href=True):
            label = " ".join(tag.stripped_strings).lower()
            if any(word in label for word in ("download", "save media", "download media", "original")):
                candidates.append(urljoin(page.url, html.unescape(tag["href"])))
        for script in soup.find_all("script"):
            text = script.string or script.get_text(" ")
            for value in self.ABSOLUTE_URL_RE.findall(text):
                if self._looks_like_media_url(value):
                    candidates.append(value)
        return list(dict.fromkeys(candidates))

    def _page_fallback(self, instagram_url, output_dir, prefix):
        username = self.username_from_url(instagram_url)
        if not username:
            return []
        for name, base, paths in self.STORY_SERVICES:
            for path in paths:
                page_url = urljoin(base, path)
                responses = []
                try:
                    page = self.session.get(page_url, timeout=self.timeout, allow_redirects=True)
                    if page.status_code < 400:
                        responses.append(page)
                        soup = BeautifulSoup(page.text, "lxml")
                        for form in soup.find_all("form"):
                            action = urljoin(page.url, form.get("action") or page.url)
                            method = (form.get("method") or "get").lower()
                            fields = self._form_fields(form, username, instagram_url)
                            if not fields:
                                continue
                            try:
                                if method == "post":
                                    responses.append(self.session.post(action, data=fields, timeout=self.timeout, allow_redirects=True))
                                else:
                                    responses.append(self.session.get(action, params=fields, timeout=self.timeout, allow_redirects=True))
                            except requests.RequestException:
                                continue
                except requests.RequestException:
                    continue
                for params in ({"username": username}, {"url": instagram_url}, {"story_url": instagram_url}):
                    try:
                        response = self.session.get(page_url, params=params, timeout=self.timeout, allow_redirects=True)
                        if response.status_code < 400:
                            responses.append(response)
                    except requests.RequestException:
                        continue
                for response in responses:
                    try:
                        candidates = self._extract_page_candidates(response)
                        files = self._download_candidates(candidates, output_dir, prefix, allow_unclassified=True)
                        if files:
                            logger.info("%s Story fallback returned %d media item(s)", name, len(files))
                            return files
                    except Exception:
                        logger.debug("%s Story fallback parse failed", name, exc_info=True)
        return []

    def fetch(self, instagram_url, output_dir):
        is_story = "/stories/" in instagram_url.lower()
        prefix = "instagram-story" if is_story else "instagram-post"
        username = self.username_from_url(instagram_url) if is_story else None
        files = self._structured_extract(instagram_url, output_dir, prefix, username=username)
        if files:
            return files
        if is_story:
            files = self._page_fallback(instagram_url, output_dir, prefix)
            if files:
                return files
        raise InstagramFallbackError("No public Instagram fallback returned validated media.")
