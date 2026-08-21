import html
import json
import logging
import os
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("rimera-bot.instagram-fallback")


class InstagramFallbackError(Exception):
    pass


class InstagramPublicStoryFallback:
    """Best-effort anonymous fallback using public Story viewer sites.

    These services are browser sites rather than documented APIs. The scraper therefore
    discovers the site's search mechanism and extracts media URLs from HTML/JSON.
    """

    SERVICES = (
        "https://downloadigstory.com/",
        "https://storiesdown.dev/",
    )
    COMMON_ENDPOINTS = (
        "/api/search",
        "/api/stories",
        "/api/story",
        "/api/instagram",
        "/api/lookup",
        "/search",
        "/stories",
    )
    MEDIA_EXTENSIONS = (".mp4", ".jpg", ".jpeg", ".png", ".webp", ".m4v", ".mov")
    ABSOLUTE_URL_RE = re.compile(r"https?://[^\"'<>\s]+", re.IGNORECASE)
    ENDPOINT_RE = re.compile(
        r"(?:fetch|axios\.(?:get|post)|url:\s*)\(?(?:\s*[\"'])(/[^\"']+)[\"']",
        re.IGNORECASE,
    )
    CDN_HINTS = ("cdn", "instagram", "fbcdn", "scontent", "story")

    def __init__(self, timeout=20):
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

    @staticmethod
    def _looks_like_media_url(value):
        if not isinstance(value, str) or not value.startswith(("http://", "https://")):
            return False
        parsed = urlparse(value)
        lower = parsed.path.lower()
        if any(lower.endswith(ext) for ext in InstagramPublicStoryFallback.MEDIA_EXTENSIONS):
            return True
        lowered = value.lower()
        return any(hint in lowered for hint in InstagramPublicStoryFallback.CDN_HINTS) and (
            "jpg" in lowered or "jpeg" in lowered or "png" in lowered or "webp" in lowered
            or "mp4" in lowered or "video" in lowered
        )

    @classmethod
    def _collect_media_values(cls, value, base_url, found):
        if isinstance(value, dict):
            for child in value.values():
                cls._collect_media_values(child, base_url, found)
            return
        if isinstance(value, list):
            for child in value:
                cls._collect_media_values(child, base_url, found)
            return
        if not isinstance(value, str):
            return

        absolute = urljoin(base_url, html.unescape(value))
        if cls._looks_like_media_url(absolute):
            found.add(absolute)

    @classmethod
    def _candidate_media(cls, response_text, base_url):
        found = set()
        soup = BeautifulSoup(response_text, "lxml")

        for tag in soup.find_all(True):
            for attr in ("href", "src", "poster", "data-src", "data-url", "data-download", "data-video", "content"):
                value = tag.get(attr)
                if value:
                    absolute = urljoin(base_url, html.unescape(value))
                    if cls._looks_like_media_url(absolute):
                        found.add(absolute)

        for script in soup.find_all("script"):
            text = script.string or script.get_text(" ", strip=False)
            if not text:
                continue
            for match in cls.ABSOLUTE_URL_RE.findall(html.unescape(text)):
                if cls._looks_like_media_url(match):
                    found.add(match)
            try:
                payload = json.loads(text)
                cls._collect_media_values(payload, base_url, found)
            except Exception:
                pass

        for match in cls.ABSOLUTE_URL_RE.findall(html.unescape(response_text)):
            if cls._looks_like_media_url(match):
                found.add(match)

        return sorted(found)

    def _discover_endpoints(self, service_url, page_text):
        endpoints = list(self.COMMON_ENDPOINTS)
        soup = BeautifulSoup(page_text, "lxml")
        for script in soup.find_all("script", src=True):
            src = urljoin(service_url, script["src"])
            try:
                response = self.session.get(src, timeout=self.timeout)
                response.raise_for_status()
                for match in self.ENDPOINT_RE.findall(response.text):
                    endpoint = match.replace("\\u002F", "/")
                    if endpoint not in endpoints:
                        endpoints.append(endpoint)
            except Exception as exc:
                logger.debug("Could not inspect fallback script %s: %s", src, exc)
        return endpoints

    def _request_search(self, service_url, endpoint, username):
        target = urljoin(service_url, endpoint)
        query_variants = (
            {"username": username},
            {"user": username},
            {"handle": username},
            {"query": username},
            {"search": username},
            {"q": username},
        )
        for params in query_variants:
            for method in ("get", "post"):
                try:
                    if method == "get":
                        response = self.session.get(target, params=params, timeout=self.timeout)
                    else:
                        response = self.session.post(target, data=params, timeout=self.timeout)
                    if response.status_code >= 400:
                        continue
                    media = self._candidate_media(response.text, response.url)
                    if media:
                        return media
                    content_type = response.headers.get("content-type", "")
                    if "application/json" in content_type:
                        try:
                            payload = response.json()
                            found = set()
                            self._collect_media_values(payload, response.url, found)
                            if found:
                                return sorted(found)
                        except Exception:
                            pass
                except requests.RequestException:
                    continue
        return []

    def _submit(self, service_url, username, page_text):
        soup = BeautifulSoup(page_text, "lxml")
        for form in soup.find_all("form"):
            payload = {}
            target = None
            for field in form.find_all("input"):
                name = (field.get("name") or "").lower()
                if not name:
                    continue
                if any(token in name for token in ("username", "user", "handle", "query", "search")):
                    target = field.get("name")
                elif field.get("type") == "hidden":
                    payload[field.get("name")] = field.get("value", "")
            if not target:
                continue
            payload[target] = username
            action = urljoin(service_url, form.get("action") or service_url)
            try:
                if (form.get("method") or "get").lower() == "post":
                    response = self.session.post(action, data=payload, timeout=self.timeout)
                else:
                    response = self.session.get(action, params=payload, timeout=self.timeout)
                response.raise_for_status()
                media = self._candidate_media(response.text, response.url)
                if media:
                    return media
            except requests.RequestException:
                continue

        return []

    def fetch(self, instagram_url, output_dir):
        username = self.username_from_url(instagram_url)
        if not username:
            raise InstagramFallbackError("Could not determine the Instagram username from the URL.")

        errors = []
        for service_url in self.SERVICES:
            try:
                page = self.session.get(service_url, timeout=self.timeout)
                page.raise_for_status()

                media_urls = self._submit(service_url, username, page.text)
                if not media_urls:
                    for endpoint in self._discover_endpoints(service_url, page.text):
                        media_urls = self._request_search(service_url, endpoint, username)
                        if media_urls:
                            break

                if not media_urls:
                    errors.append(f"{service_url}: search returned no media")
                    continue

                downloaded = []
                for index, media_url in enumerate(media_urls, 1):
                    try:
                        with self.session.get(media_url, stream=True, timeout=self.timeout, allow_redirects=True) as response:
                            response.raise_for_status()
                            content_type = (response.headers.get("content-type") or "").lower()
                            extension = os.path.splitext(urlparse(response.url).path)[1].lower()
                            if extension not in self.MEDIA_EXTENSIONS:
                                extension = ".mp4" if "video/" in content_type else ".jpg" if "image/" in content_type else None
                            if not extension:
                                continue
                            output = os.path.join(output_dir, f"story-fallback-{index:03d}{extension}")
                            with open(output, "wb") as handle:
                                for chunk in response.iter_content(chunk_size=262144):
                                    if chunk:
                                        handle.write(chunk)
                            if os.path.getsize(output) > 0:
                                downloaded.append(output)
                    except requests.RequestException as exc:
                        logger.debug("Could not download fallback media %s: %s", media_url, exc)

                if downloaded:
                    logger.info("Instagram fallback %s returned %d media item(s) for @%s", service_url, len(downloaded), username)
                    return downloaded
                errors.append(f"{service_url}: media URLs could not be downloaded")
            except Exception as exc:
                errors.append(f"{service_url}: {exc}")

        raise InstagramFallbackError("; ".join(errors) or "No public fallback media was found.")
