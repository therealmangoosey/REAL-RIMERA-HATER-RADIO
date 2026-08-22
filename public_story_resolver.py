import html
import logging
import re
from urllib.parse import urljoin, urlencode

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("rimera-bot.public-story-resolver")

MEDIA_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/x-m4v": ".m4v",
}
MEDIA_EXTENSIONS = tuple(MEDIA_TYPES.values())
BLOCKED_PATH = ("/logo", "/logos/", "/icon", "/favicon", "/assets/", "/static/", "/css/", "/js/", "/screenshot")
ABS_URL = re.compile(r"https?://[^\"'<>\s]+", re.I)

SERVICES = (
    ("PasteDL", "https://www.pastedl.com/instagram/stories"),
    ("DownloadIGStory", "https://downloadigstory.com/"),
    ("StoryClone", "https://insta.storyclone.com/stories"),
)


def _candidate_urls(text):
    found = []
    for raw in ABS_URL.findall(html.unescape(text or "").replace("\\/", "/")):
        lower = raw.lower()
        path = raw.split("?", 1)[0].lower().rstrip("/")
        if any(token in path for token in BLOCKED_PATH):
            continue
        if any(ext in path for ext in MEDIA_EXTENSIONS) or any(token in path for token in ("/media", "/download", "/story", "/video", "/image", "/photo", "/file")):
            found.append(raw)
    return list(dict.fromkeys(found))


def _extract_candidates(response):
    candidates = []
    candidates.extend(_candidate_urls(response.text))
    try:
        payload = response.json()
        def walk(value):
            if isinstance(value, dict):
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
            elif isinstance(value, str) and value.startswith(("http://", "https://")):
                candidates.extend(_candidate_urls(value))
        walk(payload)
    except ValueError:
        pass
    soup = BeautifulSoup(response.text, "lxml")
    for tag in soup.find_all(["video", "source", "img", "a"]):
        for attr in ("src", "href", "data-src", "data-media", "data-video", "data-download", "data-file", "content"):
            value = tag.get(attr)
            if not value:
                continue
            absolute = urljoin(response.url, html.unescape(value))
            if absolute.startswith(("http://", "https://")):
                candidates.extend(_candidate_urls(absolute))
    return list(dict.fromkeys(candidates))


def _download(candidates, output_dir, session, timeout):
    files = []
    for source in candidates:
        try:
            response = session.get(source, stream=True, timeout=timeout, allow_redirects=True)
            response.raise_for_status()
            content_type = (response.headers.get("content-type") or "").split(";", 1)[0].lower().strip()
            extension = MEDIA_TYPES.get(content_type)
            if not extension:
                response.close()
                continue
            path = f"{output_dir}/instagram-story-{len(files)+1:03d}{extension}"
            with open(path, "wb") as handle:
                for chunk in response.iter_content(262144):
                    if chunk:
                        handle.write(chunk)
            response.close()
            with open(path, "rb") as handle:
                head = handle.read(32)
            valid = (
                (content_type == "image/jpeg" and head.startswith(b"\xff\xd8\xff"))
                or (content_type == "image/png" and head.startswith(b"\x89PNG\r\n\x1a\n"))
                or (content_type == "image/webp" and head.startswith(b"RIFF") and b"WEBP" in head[:16])
                or (content_type.startswith("video/") and len(head) >= 8 and head[4:8] == b"ftyp")
            )
            if not valid or __import__("os").path.getsize(path) <= 4096:
                __import__("os").remove(path)
                continue
            files.append(path)
        except (requests.RequestException, OSError):
            continue
    return files


def resolve_public_story(story_url, output_dir, timeout=8):
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Linux; Android 11) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.instagram.com/",
    })

    query_variants = ("url", "story_url", "instagram_url", "link")
    for name, endpoint in SERVICES:
        urls = []
        for key in query_variants:
            urls.append(endpoint + ("&" if "?" in endpoint else "?") + urlencode({key: story_url}))
        for request_url in urls:
            try:
                response = session.get(request_url, timeout=timeout, allow_redirects=True)
                if response.status_code >= 400:
                    continue
                files = _download(_extract_candidates(response), output_dir, session, timeout)
                if files:
                    logger.info("%s direct public Story resolver returned %d file(s)", name, len(files))
                    return files
            except requests.RequestException:
                continue

        for key in query_variants:
            try:
                response = session.post(endpoint, data={key: story_url}, timeout=timeout, allow_redirects=True)
                if response.status_code >= 400:
                    continue
                files = _download(_extract_candidates(response), output_dir, session, timeout)
                if files:
                    logger.info("%s POST public Story resolver returned %d file(s)", name, len(files))
                    return files
            except requests.RequestException:
                continue
    return []
