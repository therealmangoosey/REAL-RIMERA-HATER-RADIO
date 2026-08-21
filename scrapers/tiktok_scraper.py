import json
import logging
import os
import random
import re
import time

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

logger = logging.getLogger('rimera-bot.tiktok')
load_dotenv()


def _proxy_hosts():
    raw = os.getenv('WEBSHARE_PROXY_HOSTS', '')
    return [item.strip() for item in raw.split(',') if item.strip()]

PROXIES = _proxy_hosts()
PROXY_USERNAME = os.getenv('WEBSHARE_PROXY_USERNAME', '').strip()
PROXY_PASSWORD = os.getenv('WEBSHARE_PROXY_PASSWORD', '').strip()


def get_random_proxy():
    """Return an optional authenticated proxy; direct connection is the default."""
    if not PROXIES or not PROXY_USERNAME:
        return None
    proxy = random.choice(PROXIES)
    if PROXY_PASSWORD:
        proxy_url = f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{proxy}"
    else:
        proxy_url = f"http://{PROXY_USERNAME}@{proxy}"
    return {'http': proxy_url, 'https': proxy_url}


class TikTokScraper:
    def __init__(self, handle):
        self.handle = handle
        self.url = f"https://www.tiktok.com/@{handle}"

    def get_latest_videos(self):
        videos = self._scrape_with_requests()
        if videos:
            return videos
        return self._scrape_with_selenium()

    def _scrape_with_requests(self):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 11) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': 'https://www.tiktok.com/',
            }
            proxy = get_random_proxy()
            logger.info("Using configured proxy" if proxy else "No proxy configured, using direct connection")
            logger.info(f"Attempting HTTP-based TikTok scraping: {self.url}")
            response = requests.get(self.url, headers=headers, proxies=proxy, timeout=15)
            if response.status_code != 200:
                logger.warning(f"HTTP request failed with status {response.status_code}")
                return []

            soup = BeautifulSoup(response.text, 'html.parser')
            videos = []
            for script in soup.find_all('script'):
                if not script.string or ('video' not in script.string.lower() and 'item' not in script.string.lower()):
                    continue
                try:
                    json_match = re.search(r'__DEFAULT_STATE__\s*=\s*({.+?});', script.string)
                    if json_match:
                        data = json.loads(json_match.group(1))
                        videos = self._parse_tiktok_json(data)
                        if videos:
                            logger.info(f"Found {len(videos)} videos from JSON data")
                            return videos
                except (json.JSONDecodeError, KeyError):
                    continue

            video_links = soup.find_all('a', href=re.compile(r'/video/\d+'))
            logger.info(f"Found {len(video_links)} video links in HTML")
            for link in video_links[:10]:
                href = link.get('href', '')
                video_id = re.search(r'/video/(\d+)', href)
                if video_id:
                    videos.append({
                        'id': video_id.group(1),
                        'content': link.get_text(strip=True) or "TikTok video",
                        'url': f"https://www.tiktok.com{href}" if href.startswith('/') else href,
                        'source': 'TikTok',
                    })
            return videos
        except requests.RequestException as e:
            logger.warning(f"TikTok HTTP request failed: {e}")
            return []
        except Exception as e:
            logger.error(f"Error in HTTP-based TikTok scraping: {e}")
            return []

    def _parse_tiktok_json(self, data):
        videos = []
        try:
            if isinstance(data, dict):
                for key, value in data.items():
                    if isinstance(value, dict):
                        videos.extend(self._parse_tiktok_json(value))
                    elif isinstance(value, list):
                        for item in value:
                            if isinstance(item, dict):
                                videos.extend(self._parse_tiktok_json(item))
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        videos.extend(self._parse_tiktok_json(item))

            if isinstance(data, dict) and 'id' in data and 'desc' in data:
                videos.append({
                    'id': str(data.get('id')),
                    'content': data.get('desc', ''),
                    'url': f"https://www.tiktok.com/@{self.handle}/video/{data.get('id')}",
                    'source': 'TikTok',
                })
        except Exception as e:
            logger.debug(f"Error parsing TikTok JSON: {e}")
        return videos

    def _scrape_with_selenium(self):
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from webdriver_manager.chrome import ChromeDriverManager
        except ImportError as e:
            logger.info(f"TikTok browser fallback unavailable: {e}")
            return []

        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-software-rasterizer")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-dev-tools")
        chrome_options.add_argument("--no-first-run")
        chrome_options.add_argument("--no-default-browser-check")
        chrome_options.add_argument("--disable-background-networking")
        chrome_options.add_argument("--disable-sync")
        chrome_options.add_argument("--disable-translate")
        chrome_options.add_argument("--metrics-recording-only")
        chrome_options.add_argument("--disable-default-apps")
        chrome_options.add_argument("--safebrowsing-disable-auto-update")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36")

        driver = None
        try:
            try:
                service = Service('/usr/bin/chromedriver')
                driver = webdriver.Chrome(service=service, options=chrome_options)
            except Exception as e:
                logger.info(f"System ChromeDriver unavailable: {e}; trying ChromeDriverManager")
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=chrome_options)

            logger.info(f"Scraping TikTok profile with Selenium: {self.url}")
            driver.get(self.url)
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "[data-e2e='user-post-item']"))
            )
            driver.execute_script("window.scrollTo(0, 500);")
            time.sleep(2)

            soup = BeautifulSoup(driver.page_source, 'lxml')
            videos = []
            video_items = soup.select("[data-e2e='user-post-item']")
            logger.info(f"Found {len(video_items)} TikTok videos with Selenium")
            for item in video_items:
                link_tag = item.find('a')
                if not link_tag or not link_tag.get('href'):
                    continue
                video_url = link_tag['href']
                video_id = video_url.split('/')[-1].split('?')[0]
                desc_tag = item.find('img')
                description = desc_tag.get('alt', '') if desc_tag else ""
                videos.append({
                    'id': video_id,
                    'content': description,
                    'url': video_url,
                    'source': 'TikTok',
                })
            return videos
        except Exception as e:
            logger.error(f"Error scraping TikTok with Selenium: {e}")
            return []
        finally:
            if driver:
                driver.quit()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scraper = TikTokScraper("rimera_official")
    print(scraper.get_latest_videos())
