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


class InstagramPublicStoryFallback:
    """Best-effort anonymous Story downloader using several public web viewers."""

    SERVICES = (
        {
            "name": "StoryClone",
            "base": "https://insta.storyclone.com",
            "pages": ("/stories", "/stories/{username}", "/stories?username={username}", "/stories?url={url}"),
        },
        {
            "name": "DownloadIGStory",
            "base": "https://downloadigstory.com",
            "pages": ("/", "/{username}", "/?username={username}", "/?url={url}"),
        },
        {
            "name": "StoriesDown",
            "base": "https://storiesdown.dev",
            "pages": ("/", "/{username}", "/?username={username}", "/?url={url}"),
        },
        {
            "name": "PasteDL",
            "base": "https://www.pastedl.com",
            "pages": ("/instagram/stories", "/instagram/stories?username={username}", "/instagram/stories?url={url}"),
        },
        {
            "name": "SocialDawn",
            "base": "https://www.socialdawn.com",
            "pages": ("/instagram-story-downloader", "/instagram-story-downloader?username={username}", "/instagram-story-downloader?url={url}"),
        },
        {
            "name": "IGnony",
            "base": "https://www.ignony.com",
            "pages": ("/", "/?username={username}", "/?url={url}"),
        },
        {
            "name": "ViewIGStory",
            "base": "https://www.view-ig-story.com",
            "pages": ("/download-instagram-story", "/download-instagram-story?username={username}", "/download-instagram-story?url={url}"),
        },
    )

    COMMON_ENDPOINTS = (
        "/api/search", "/api/stories", "/api/story", "/api/instagram", "/api/lookup",
        "/search", "/stories", "/download", "/api/download", "/api/fetch", "/api/fetch-story",
    )
    MEDIA_EXTENSIONS = (".mp4", ".jpg", ".jpeg", ".png", ".webp", ".m4v", ".mov")
    BLOCKED_FILENAMES = ("favicon", "logo", "icon", "download", "arrow", "button", "loader", "placeholder")
    ABSOLUTE_URL_RE = re.compile(r"https?://[^\"'<>\s]+", re.IGNORECASE)
    ENDPOINT_RE = re.compile(
        r"(?:fetch|axios\.(?:get|post)|url\s*:\s*)\(?(?:\s*[\"'])(/[^\"']+)[\"']",
        re.IGNORECASE,
    )

    def __init__(self, timeout=18):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Linux; Android 11) AppleWebKit/537.36 Chrome/120 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
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
        absolute = html.unescape(value)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            return False
        path_name = os.path.basename(parsed.path).lower()
        if any(token in path_name for token in cls.BLOCKED_FILENAMES):
            return False
        lower_path = parsed.path.lower()
        lower_all = absolute.lower()
        if any(lower_path.endswith(ext) for ext in cls.MEDIA_EXTENSIONS):
            return True
        return any(hint in lower_all for hint in ("cdn", "fbcdn", "scontent", "instagram")) and any(
            token in lower_all for token in ("video", "media", "image", "photo", "mp4", "jpg", "jpeg", "png", "webp")
        )

    @classmethod
    def _collect_media_values(cls, value, base_url, found):
        if isinstance(value, dict):
            for child in value.values():
                cls._collect_media_values(child, base_url, found)
        elif isinstance(value, list):
            for child in value:
                cls._collect_media_values(child, base_url, found)
        elif isinstance(value, str):
            absolute = urljoin(base_url, html.unescape(value))
            if cls._looks_like_media_url(absolute):
                found.add(absolute)

    @classmethod
    def _candidate_media(cls, response_text, base_url):
        found = set()
        soup = BeautifulSoup(response_text, "lxml")
        for tag in soup.find_all(True):
            for attr in (
                "href", "src", "poster", "content", "data-src", "data-url", "data-download",
                "data-video", "data-image", "data-media", "data-href", "data-file",
            ):
                value = tag.get(attr)
                if value:
                    absolute = urljoin(base_url, html.unescape(value))
                    if cls._looks_like_media_url(absolute):
                        found.add(absolute)

        for script in soup.find_all("script"):
            text = script.string or script.get_text(" ", strip=False)
            if not text:
                continue
            decoded = html.unescape(text).replace("\\/", "/").replace("\\u002F", "/")
            for match in cls.ABSOLUTE_URL_RE.findall(decoded):
                if cls._looks_like_media_url(match):
                    found.add(match)
            try:
                payload = json.loads(decoded)
                cls._collect_media_values(payload, base_url, found)
            except Exception:
                pass

        for match in cls.ABSOLUTE_URL_RE.findall(html.unescape(response_text).replace("\\/", "/")):
            if cls._looks_like_media_url(match):
                found.add(match)
        return sorted(found)

    def _discover_endpoints(self, page_url, page_text):
        endpoints = list(self.COMMON_ENDPOINTS)
        soup = BeautifulSoup(page_text, "lxml")
        for script in soup.find_all("script", src=True):
            src = urljoin(page_url, script["src"])
            try:
                response = self.session.get(src, timeout=self.timeout)
                if response.status_code >= 400:
                    continue
                for match in self.ENDPOINT_RE.findall(response.text):
                    endpoint = match.replace("\\u002F", "/")
                    if endpoint not in endpoints:
                        endpoints.append(endpoint)
                for candidate in re.findall(r"[\"'](/[^\"']*(?:story|search|download|media|api)[^\"']*)[\"']", response.text, re.I):
                    if candidate not in endpoints:
                        endpoints.append(candidate)
            except requests.RequestException:
                continue
        return endpoints

    def _request_variants(self, target, username, instagram_url):
        query_variants = (
            {"username": username}, {"user": username}, {"handle": username},
            {"query": username}, {"search": username}, {"q": username},
            {"url": instagram_url}, {"link": instagram_url}, {"instagram_url": instagram_url},
        )
        for params in query_variants:
            for method in ("get", "post"):
                try:
                    response = self.session.get(target, params=params, timeout=self.timeout) if method == "get" else self.session.post(target, data=params, timeout=self.timeout)
                    if response.status_code >= 400:
                        continue
                    media = self._candidate_media(response.text, response.url)
                    if media:
                        return media
                    content_type = (response.headers.get("content-type") or "").lower()
                    if "json" in content_type:
                        try:
                            found = set()
                            self._collect_media_values(response.json(), response.url, found)
                            if found:
                                return sorted(found)
                        except Exception:
                            pass
                except requests.RequestException:
                    continue
        return []

    def _form_search(self, page_url, page_text, username, instagram_url):
        soup = BeautifulSoup(page_text, "lxml")
        for form in soup.find_all("form"):
            payload = {}
            target_name = None
            for field in form.find_all("input"):
                name = field.get("name") or ""
                lname = name.lower()
                if not name:
                    continue
                if any(token in lname for token in ("username", "user", "handle", "query", "search", "url", "link")):
                    target_name = name
                elif field.get("type") == "hidden":
                    payload[name] = field.get("value", "")
            if not target_name:
                continue
            payload[target_name] = instagram_url if any(x in target_name.lower() for x in ("url", "link")) else username
            action = urljoin(page_url, form.get("action") or page_url)
            try:
                response = self.session.post(action, data=payload, timeout=self.timeout) if (form.get("method") or "get").lower() == "post" else self.session.get(action, params=payload, timeout=self.timeout)
                if response.status_code < 400:
                    media = self._candidate_media(response.text, response.url)
                    if media:
                        return media
            except requests.RequestException:
                continue
        return []

    @staticmethod
    def _valid_media_bytes(data, content_type):
        """Reject website assets such as icons, SVGs, and download buttons."""
        content_type = (content_type or "").lower()
        if "video/" in content_type or "image/" in content_type:
            return True
        if data.startswith(b"\x00\x00\x00") and b"ftyp" in data[:32]:
            return True
        if data.startswith(b"\xFF\xD8\xFF") or data.startswith(b"\x89PNG\r\n\x1a\n"):
            return True
        if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
            return True
        return False

    def _download_media(self, media_urls, output_dir, service_name):
        downloaded = []
        for media_url in media_urls:
            try:
                with self.session.get(media_url, stream=True, timeout=self.timeout, allow_redirects=True) as response:
                    response.raise_for_status()
                    content_type = (response.headers.get("content-type") or "").lower()
                    if any(x in content_type for x in ("text/html", "text/css", "application/javascript", "image/svg")):
                        logger.debug("%s returned non-media content type for %s: %s", service_name, media_url, content_type)
                        continue
                    first_chunk = next(response.iter_content(chunk_size=64 * 1024), b"")
                    if not self._valid_media_bytes(first_chunk, content_type):
                        logger.debug("%s returned a non-media asset for %s", service_name, media_url)
                        continue

                    extension = os.path.splitext(urlparse(response.url).path)[1].lower()
                    if extension not in self.MEDIA_EXTENSIONS:
                        extension = ".mp4" if "video/" in content_type or (b"ftyp" in first_chunk[:32] and first_chunk.startswith(b"\x00\x00\x00")) else ".jpg"
                    output = os.path.join(output_dir, f"story-fallback-{len(downloaded)+1:03d}{extension}")
                    with open(output, "wb") as handle:
                        handle.write(first_chunk)
                        for chunk in response.iter_content(chunk_size=262144):
                            if chunk:
                                handle.write(chunk)
                    if os.path.getsize(output) >= 1024:
                        downloaded.append(output)
                    else:
                        os.remove(output)
            except requests.RequestException as exc:
                logger.debug("%s media download failed: %s", service_name, exc)
        return downloaded

    def fetch(self, instagram_url, output_dir):
        username = self.username_from_url(instagram_url)
        if not username:
            raise InstagramFallbackError("Could not determine the Instagram username from the URL.")

        errors = []
        for service in self.SERVICES:
            name = service["name"]
            base = service["base"]
            for page_pattern in service["pages"]:
                page_url = base + page_pattern.format(username=quote_plus(username), url=quote_plus(instagram_url))
                try:
                    page = self.session.get(page_url, timeout=self.timeout)
                    if page.status_code >= 400:
                        continue
                    media_urls = self._candidate_media(page.text, page.url)
                    if not media_urls:
                        media_urls = self._form_search(page.url, page.text, username, instagram_url)
                    if not media_urls:
                        for endpoint in self._discover_endpoints(page.url, page.text):
                            media_urls = self._request_variants(urljoin(page.url, endpoint), username, instagram_url)
                            if media_urls:
                                break
                    if not media_urls:
                        continue
                    downloaded = self._download_media(media_urls, output_dir, name)
                    if downloaded:
                        logger.info("%s returned %d valid Story media item(s) for @%s", name, len(downloaded), username)
                        return downloaded
                    errors.append(f"{name}: candidate links were not actual media")
                except Exception as exc:
                    errors.append(f"{name}: {exc}")

        raise InstagramFallbackError(" | ".join(errors) if errors else "No public Story fallback returned valid media.")
