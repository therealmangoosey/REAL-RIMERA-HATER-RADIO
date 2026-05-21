import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from html import unescape
from urllib.parse import quote_plus, urlparse

import requests
from bs4 import BeautifulSoup


logger = logging.getLogger('rimera-bot.social')


class SocialScraper:
    def __init__(self, config):
        self.config = config
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36'
        }

    def get_tumblr_updates(self):
        blog_url = self._normalize_tumblr_url(self.config.get('tumblr_url', '')).rstrip('/')
        if not blog_url:
            return []
        return self._read_rss(f"{blog_url}/rss", 'Tumblr')

    def get_youtube_updates(self):
        channel_id = self.config.get('youtube_channel_id')
        youtube_url = self.config.get('youtube_url')
        if not channel_id and youtube_url:
            channel_id = self._discover_youtube_channel_id(youtube_url)
        if not channel_id:
            logger.warning("No YouTube channel ID configured or discovered.")
            return []
        return self._read_rss(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}", 'YouTube')

    def get_instagram_updates(self):
        return self._page_signature_update('Instagram', self.config.get('instagram_url'))

    def get_apple_music_updates(self):
        return self._page_signature_update('Apple Music', self.config.get('apple_music_url'))

    def get_soundcloud_updates(self):
        return self._page_signature_update('SoundCloud', self.config.get('soundcloud_url'))

    def get_spotify_updates(self):
        spotify_url = self.config.get('spotify_url')
        if not spotify_url:
            return []

        oembed_url = f"https://open.spotify.com/oembed?url={quote_plus(spotify_url)}"
        try:
            response = requests.get(oembed_url, timeout=15, headers=self.headers)
            if response.status_code == 200:
                data = response.json()
                title = data.get('title') or 'Spotify update'
                image_url = data.get('thumbnail_url')
                item_id = self._hash_parts(title, image_url, data.get('html'))
                return [{
                    'id': item_id,
                    'source': 'Spotify',
                    'title': title,
                    'content': 'Spotify profile or release metadata changed.',
                    'description': 'Spotify profile or release metadata changed.',
                    'url': spotify_url,
                    'image_url': image_url,
                }]
        except Exception as e:
            logger.error(f"Error checking Spotify oEmbed: {e}")

        return self._page_signature_update('Spotify', spotify_url)

    def _read_rss(self, url, source):
        try:
            response = requests.get(url, timeout=15, headers=self.headers)
            if response.status_code != 200:
                logger.warning(f"Failed to fetch {source} feed: Status {response.status_code}")
                return []

            root = ET.fromstring(response.content)
            channel = root.find('channel')
            if channel is not None:
                updates = self._parse_rss_items(channel.findall('item'), source, url)
            else:
                updates = self._parse_atom_entries(root.findall('{http://www.w3.org/2005/Atom}entry'), source, url)

            logger.info(f"Found {len(updates)} {source} feed item(s)")
            return updates
        except Exception as e:
            logger.error(f"Error reading {source} feed: {e}")
            return []

    def _parse_rss_items(self, items, source, url):
        updates = []

        for item in items[:10]:
            title = self._xml_text(item, 'title') or f'{source} update'
            link = self._xml_text(item, 'link') or url
            description = self._clean_html(self._xml_text(item, 'description'))
            guid = self._xml_text(item, 'guid') or link
            published = self._xml_text(item, 'pubDate')
            image_url = self._first_image_url(self._xml_text(item, 'description'))

            updates.append({
                'id': guid,
                'source': source,
                'title': title,
                'content': description or title,
                'description': description,
                'url': link,
                'timestamp': published,
                'image_url': image_url,
            })

        return updates

    def _parse_atom_entries(self, entries, source, url):
        updates = []
        atom_ns = '{http://www.w3.org/2005/Atom}'
        media_ns = '{http://search.yahoo.com/mrss/}'

        for entry in entries[:10]:
            title = self._xml_text(entry, f'{atom_ns}title') or f'{source} update'
            entry_id = self._xml_text(entry, f'{atom_ns}id')
            published = self._xml_text(entry, f'{atom_ns}published')
            description = self._xml_text(entry, f'{media_ns}group/{media_ns}description')
            link_tag = entry.find(f'{atom_ns}link')
            thumbnail_tag = entry.find(f'{media_ns}group/{media_ns}thumbnail')
            link = link_tag.get('href') if link_tag is not None else url
            image_url = thumbnail_tag.get('url') if thumbnail_tag is not None else None

            updates.append({
                'id': entry_id or link,
                'source': source,
                'title': title,
                'content': description or title,
                'description': description,
                'url': link,
                'timestamp': published,
                'image_url': image_url,
            })

        return updates

    def _page_signature_update(self, source, url):
        if not url:
            return []
        try:
            response = requests.get(url, timeout=15, headers=self.headers)
            if response.status_code != 200:
                logger.warning(f"Failed to fetch {source} page: Status {response.status_code}")
                return []

            soup = BeautifulSoup(response.text, 'lxml')
            title = self._meta(soup, 'og:title') or self._title(soup) or f'{source} update'
            description = self._meta(soup, 'og:description') or self._meta(soup, 'description') or ''
            image_url = self._meta(soup, 'og:image')
            canonical_url = self._meta(soup, 'og:url') or url
            signature_text = " ".join([
                title,
                description,
                image_url or '',
                canonical_url,
                self._visible_text_sample(soup),
            ])
            item_id = self._hash_parts(signature_text)

            return [{
                'id': item_id,
                'source': source,
                'title': title,
                'content': description or f'{source} page changed.',
                'description': description,
                'url': canonical_url,
                'image_url': image_url,
            }]
        except Exception as e:
            logger.error(f"Error checking {source}: {e}")
            return []

    def _discover_youtube_channel_id(self, url):
        try:
            response = requests.get(url, timeout=15, headers=self.headers)
            if response.status_code != 200:
                return None
            patterns = [
                r'"channelId"\s*:\s*"(UC[^"]+)"',
                r'<meta itemprop="channelId" content="(UC[^"]+)"',
                r'https://www.youtube.com/channel/(UC[^"/?]+)',
            ]
            for pattern in patterns:
                match = re.search(pattern, response.text)
                if match:
                    return match.group(1)
        except Exception as e:
            logger.error(f"Error discovering YouTube channel ID: {e}")
        return None

    @staticmethod
    def _normalize_tumblr_url(url):
        if not url:
            return ''
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        path = parsed.path.strip('/')
        if host in {'www.tumblr.com', 'tumblr.com'} and path:
            handle = path.split('/')[0]
            return f"https://{handle}.tumblr.com"
        return url

    @staticmethod
    def _xml_text(item, tag):
        child = item.find(tag)
        return child.text.strip() if child is not None and child.text else ''

    @staticmethod
    def _clean_html(html):
        if not html:
            return ''
        return BeautifulSoup(unescape(html), 'lxml').get_text(" ", strip=True)

    @staticmethod
    def _first_image_url(html):
        if not html:
            return None
        soup = BeautifulSoup(unescape(html), 'lxml')
        image = soup.find('img')
        return image.get('src') if image else None

    @staticmethod
    def _meta(soup, name):
        tag = soup.find('meta', property=name) or soup.find('meta', attrs={'name': name})
        return tag.get('content', '').strip() if tag else ''

    @staticmethod
    def _title(soup):
        return soup.title.get_text(strip=True) if soup.title else ''

    @staticmethod
    def _visible_text_sample(soup):
        for tag in soup(['script', 'style', 'noscript']):
            tag.decompose()
        return soup.get_text(" ", strip=True)[:2000]

    @staticmethod
    def _hash_parts(*parts):
        raw = "||".join(str(part or '') for part in parts)
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()
