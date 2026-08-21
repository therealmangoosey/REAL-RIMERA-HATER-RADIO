import html
import os
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


class InstagramFallbackError(Exception):
    pass


class InstagramPublicStoryFallback:
    """Best-effort anonymous fallback using public Story viewer sites."""

    SERVICES = (
        "https://downloadigstory.com/",
        "https://storiesdown.dev/",
    )
    MEDIA_EXTENSIONS = (".mp4", ".jpg", ".jpeg", ".png", ".webp", ".m4v", ".mov")
    URL_RE = re.compile(r"https?://[^\"'<>\s]+", re.IGNORECASE)

    def __init__(self, timeout=20):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Linux; Android 11) AppleWebKit/537.36 Chrome/120 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })

    @staticmethod
    def username_from_url(url):
        match = re.search(r"instagram\.com/(?:stories/)?([A-Za-z0-9._]+)/", url, re.IGNORECASE)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def _candidate_media(response_text, base_url):
        soup = BeautifulSoup(response_text, "lxml")
        values = []
        attrs = ("href", "src", "data-src", "data-url", "data-download", "data-video", "content")
        for tag in soup.find_all(True):
            for attr in attrs:
                value = tag.get(attr)
                if value:
                    values.append(value)
        values.extend(InstagramPublicStoryFallback.URL_RE.findall(html.unescape(response_text)))

        media = []
        for value in values:
            absolute = urljoin(base_url, value)
            parsed = urlparse(absolute)
            if parsed.scheme not in {"http", "https"}:
                continue
            lower = parsed.path.lower()
            if any(lower.endswith(ext) for ext in InstagramPublicStoryFallback.MEDIA_EXTENSIONS):
                media.append(absolute)

        seen = set()
        return [url for url in media if not (url in seen or seen.add(url))]

    def _submit(self, service_url, username):
        page = self.session.get(service_url, timeout=self.timeout)
        page.raise_for_status()
        soup = BeautifulSoup(page.text, "lxml")
        forms = soup.find_all("form")
        if not forms:
            return []

        for form in forms:
            inputs = form.find_all("input")
            target = None
            payload = {}
            for field in inputs:
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
            method = (form.get("method") or "get").lower()
            if method == "post":
                response = self.session.post(action, data=payload, timeout=self.timeout)
            else:
                response = self.session.get(action, params=payload, timeout=self.timeout)
            response.raise_for_status()
            media = self._candidate_media(response.text, response.url)
            if media:
                return media

        return []

    def fetch(self, instagram_url, output_dir):
        username = self.username_from_url(instagram_url)
        if not username:
            raise InstagramFallbackError("Could not determine the Instagram username from the URL.")

        errors = []
        for service in self.SERVICES:
            try:
                media_urls = self._submit(service, username)
                if not media_urls:
                    errors.append(f"{service}: no media links returned")
                    continue

                downloaded = []
                for index, media_url in enumerate(media_urls, 1):
                    extension = os.path.splitext(urlparse(media_url).path)[1].lower()
                    extension = extension if extension in self.MEDIA_EXTENSIONS else ".bin"
                    output = os.path.join(output_dir, f"story-fallback-{index:03d}{extension}")
                    with self.session.get(media_url, stream=True, timeout=self.timeout) as response:
                        response.raise_for_status()
                        with open(output, "wb") as handle:
                            for chunk in response.iter_content(chunk_size=1024 * 256):
                                if chunk:
                                    handle.write(chunk)
                    if os.path.getsize(output) > 0:
                        downloaded.append(output)

                if downloaded:
                    return downloaded
            except Exception as exc:
                errors.append(f"{service}: {exc}")

        raise InstagramFallbackError("; ".join(errors) or "No public fallback media was found.")
