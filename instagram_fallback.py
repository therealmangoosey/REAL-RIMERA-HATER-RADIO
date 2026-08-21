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
    """Anonymous best-effort Instagram fallback using public downloader/viewer sites."""

    STORY_SERVICES = (
        ("StoryClone", "https://insta.storyclone.com", ("/stories/{username}", "/stories?username={username}", "/stories?url={url}")),
        ("DownloadIGStory", "https://downloadigstory.com", ("/{username}", "/?username={username}", "/?url={url}")),
        ("StoriesDown", "https://storiesdown.dev", ("/{username}", "/?username={username}", "/?url={url}")),
        ("PasteDL", "https://www.pastedl.com", ("/instagram/stories?username={username}", "/instagram/stories?url={url}")),
        ("SocialDawn", "https://www.socialdawn.com", ("/instagram-story-downloader?username={username}", "/instagram-story-downloader?url={url}")),
        ("IGnony", "https://www.ignony.com", ("/?username={username}", "/?url={url}")),
        ("ViewIGStory", "https://www.view-ig-story.com", ("/download-instagram-story?username={username}", "/download-instagram-story?url={url}")),
    )

    PHOTO_SERVICES = (
        ("InstaLoadr-direct", "https://www.instaloadr.com", ("/{raw_url}", "/?url={url}")),
        ("Tikt-direct", "https://tikt.com", ("/{raw_url}", "/instagram/?url={url}")),
        ("FastReels", "https://fastreels.net", ("/instagram-photo-downloader?url={url}", "/instagram-photo-downloader?link={url}")),
        ("Instappa", "https://instappa.com", ("/instagram-image-downloader/?url={url}", "/instagram-image-downloader/?link={url}")),
        ("SaveGr", "https://savegr.com", ("/instagram-photo-downloader?url={url}", "/instagram-photo-downloader?link={url}")),
        ("PasteDL-photo", "https://www.pastedl.com", ("/instagram/photo?url={url}", "/instagram/photo?link={url}")),
        ("GramPeek", "https://grampeek.com", ("/instagram-photo-downloader?url={url}", "/instagram-photo-downloader?link={url}")),
    )

    MEDIA_EXTENSIONS = (".mp4", ".jpg", ".jpeg", ".png", ".webp", ".m4v", ".mov")
    ABSOLUTE_URL_RE = re.compile(r"https?://[^\"'<>\s]+", re.IGNORECASE)

    def __init__(self, timeout=18):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Linux; Android 11) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36",
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
        value = html.unescape(value).replace("\\/", "/").replace("\\u0026", "&")
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"}:
            return False
        path = parsed.path.lower()
        whole = value.lower()
        if any(path.endswith(ext) for ext in cls.MEDIA_EXTENSIONS):
            return True
        return any(token in whole for token in ("scontent", "fbcdn", "cdn")) and any(
            token in whole for token in ("image", "photo", "video", "media", "story")
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
    def _candidate_urls(cls, response_text, base_url):
        found = set()
        soup = BeautifulSoup(response_text, "lxml")

        for tag in soup.find_all(True):
            for attr in ("href", "src", "poster", "content", "data-src", "data-url", "data-download", "data-video", "data-image", "data-media", "data-href", "data-file"):
                value = tag.get(attr)
                if not value:
                    continue
                absolute = urljoin(base_url, html.unescape(value))
                if cls._looks_like_media_url(absolute):
                    found.add(absolute)

        for script in soup.find_all("script"):
            text = script.string or script.get_text(" ", strip=False)
            if not text:
                continue
            decoded = html.unescape(text).replace("\\/", "/").replace("\\u002F", "/").replace("\\u0026", "&")
            for match in cls.ABSOLUTE_URL_RE.findall(decoded):
                if cls._looks_like_media_url(match):
                    found.add(match)
            try:
                cls._collect_media_values(json.loads(decoded), base_url, found)
            except Exception:
                pass

        return sorted(found)

    @staticmethod
    def _extract_download_links(response_text, base_url):
        soup = BeautifulSoup(response_text, "lxml")
        links = []
        for tag in soup.find_all("a", href=True):
            href = urljoin(base_url, html.unescape(tag["href"]))
            text = " ".join(tag.stripped_strings).lower()
            if "download" in text or "save" in text or "media" in text:
                links.append(href)
        return list(dict.fromkeys(links))

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
                content_type = (response.headers.get("content-type") or "").lower()
                final_url = response.url
                ext = os.path.splitext(urlparse(final_url).path)[1].lower()

                if content_type.startswith("image/"):
                    ext = ".png" if "png" in content_type else ".webp" if "webp" in content_type else ".jpg"
                elif content_type.startswith("video/"):
                    ext = ".mp4" if ext not in self.MEDIA_EXTENSIONS else ext
                elif ext not in self.MEDIA_EXTENSIONS:
                    response.close()
                    continue

                output = os.path.join(output_dir, f"{prefix}-{len(downloaded)+1:03d}{ext}")
                with open(output, "wb") as handle:
                    for chunk in response.iter_content(chunk_size=262144):
                        if chunk:
                            handle.write(chunk)
                response.close()

                if os.path.getsize(output) <= 4096:
                    try:
                        os.remove(output)
                    except OSError:
                        pass
                    continue
                downloaded.append(output)
            except requests.RequestException:
                continue
        return downloaded

    def _visit_variants(self, base, patterns, username, instagram_url):
        return [
            base + pattern.format(
                username=quote_plus(username or ""),
                url=quote_plus(instagram_url),
                raw_url=instagram_url,
            )
            for pattern in patterns
        ]

    def fetch_story(self, instagram_url, output_dir):
        username = self.username_from_url(instagram_url)
        if not username:
            raise InstagramFallbackError("Could not determine the Instagram username from the Story URL.")

        errors = []
        for name, base, patterns in self.STORY_SERVICES:
            for page_url in self._visit_variants(base, patterns, username, instagram_url):
                try:
                    page = self.session.get(page_url, timeout=self.timeout, allow_redirects=True)
                    if page.status_code >= 400:
                        continue
                    media = self._candidate_urls(page.text, page.url)
                    if not media:
                        media = self._extract_download_links(page.text, page.url)
                    if media:
                        files = self._download_candidates(media, output_dir, "instagram-story")
                        if files:
                            logger.info("%s returned %d Story media item(s)", name, len(files))
                            return files
                except requests.RequestException as exc:
                    errors.append(f"{name}: {exc}")
        raise InstagramFallbackError(" | ".join(errors) if errors else "No public Story fallback returned usable media.")

    def fetch_post(self, instagram_url, output_dir):
        errors = []

        for name, base, patterns in self.PHOTO_SERVICES:
            for page_url in self._visit_variants(base, patterns, self.username_from_url(instagram_url) or "", instagram_url):
                try:
                    page = self.session.get(page_url, timeout=self.timeout, allow_redirects=True)
                    if page.status_code >= 400:
                        continue

                    media = self._candidate_urls(page.text, page.url)
                    download_links = self._extract_download_links(page.text, page.url)
                    files = self._download_candidates(media + download_links, output_dir, "instagram-post")
                    if files:
                        logger.info("%s returned %d Instagram post media item(s)", name, len(files))
                        return files
                except requests.RequestException as exc:
                    errors.append(f"{name}: {exc}")

        # Last anonymous attempt: direct public Instagram HTML/metadata.
        for page_url in (instagram_url, instagram_url.split("?", 1)[0]):
            try:
                page = self.session.get(page_url, timeout=self.timeout, allow_redirects=True)
                if page.status_code >= 400:
                    continue
                direct = []
                soup = BeautifulSoup(page.text, "lxml")
                for selector in (
                    'meta[property="og:image"]',
                    'meta[property="og:image:url"]',
                    'meta[name="twitter:image"]',
                    'meta[name="twitter:image:src"]',
                ):
                    for tag in soup.select(selector):
                        value = tag.get("content")
                        if value:
                            direct.append(value)
                direct.extend(self._candidate_urls(page.text, page.url))
                files = self._download_candidates(direct, output_dir, "instagram-post")
                if files:
                    return files
            except requests.RequestException as exc:
                errors.append(f"instagram-direct: {exc}")

        raise InstagramFallbackError(" | ".join(errors) if errors else "No public post/photo fallback returned usable media.")

    def fetch(self, instagram_url, output_dir):
        if "/stories/" in instagram_url.lower():
            return self.fetch_story(instagram_url, output_dir)
        return self.fetch_post(instagram_url, output_dir)
