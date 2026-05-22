import requests
from bs4 import BeautifulSoup
import logging
import json
import re
import random
import os
from dotenv import load_dotenv

logger = logging.getLogger('rimera-bot.tiktok')

# Load environment variables
load_dotenv()

# Webshare proxies
PROXIES = [
    '38.154.203.95:5863',
    '198.105.121.200:6462',
    '64.137.96.74:6641',
    '209.127.138.10:5784',
    '38.154.185.97:6370',
    '84.247.60.125:6095',
    '142.111.67.146:5611',
    '194.39.32.164:6461',
    '191.96.254.138:6185',
    '31.58.9.4:6077'
]

PROXY_USERNAME = os.getenv('WEBSHARE_PROXY_USERNAME', '')
PROXY_PASSWORD = os.getenv('WEBSHARE_PROXY_PASSWORD', '')

def get_random_proxy():
    """Get a random proxy with authentication"""
    if not PROXIES or not PROXY_USERNAME:
        return None
    proxy = random.choice(PROXIES)
    # Webshare proxy format: username:password@ip:port
    if PROXY_PASSWORD:
        proxy_url = f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{proxy}"
    else:
        proxy_url = f"http://{PROXY_USERNAME}@{proxy}"
    return {
        'http': proxy_url,
        'https': proxy_url
    }

class TikTokScraper:
    def __init__(self, handle):
        self.handle = handle
        self.url = f"https://www.tiktok.com/@{handle}"

    def get_latest_videos(self):
        # Try HTTP-based scraping first (no Chrome required)
        videos = self._scrape_with_requests()
        if videos:
            return videos

        # Fallback to Selenium if available
        return self._scrape_with_selenium()

    def _scrape_with_requests(self):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': 'https://www.tiktok.com/',
            }
            
            proxy = get_random_proxy()
            if proxy:
                logger.info(f"Using proxy: {proxy['http'][:30]}...")
            else:
                logger.info("No proxy configured, using direct connection")
            
            logger.info(f"Attempting HTTP-based TikTok scraping: {self.url}")
            response = requests.get(self.url, headers=headers, proxies=proxy, timeout=15)
            
            if response.status_code != 200:
                logger.warning(f"HTTP request failed with status {response.status_code}")
                return []

            # Try to extract video data from the HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            videos = []

            # Method 1: Look for JSON data in script tags
            script_tags = soup.find_all('script')
            for script in script_tags:
                if script.string and ('video' in script.string.lower() or 'item' in script.string.lower()):
                    try:
                        # Try to extract JSON data
                        json_match = re.search(r'__DEFAULT_STATE__\s*=\s*({.+?});', script.string)
                        if json_match:
                            data = json.loads(json_match.group(1))
                            # Parse the JSON structure for video data
                            videos = self._parse_tiktok_json(data)
                            if videos:
                                logger.info(f"Found {len(videos)} videos from JSON data")
                                return videos
                    except (json.JSONDecodeError, KeyError):
                        continue

            # Method 2: Parse HTML directly for video links
            video_links = soup.find_all('a', href=re.compile(r'/video/\d+'))
            logger.info(f"Found {len(video_links)} video links in HTML")
            
            for link in video_links[:10]:  # Limit to first 10
                href = link.get('href', '')
                video_id = re.search(r'/video/(\d+)', href)
                if video_id:
                    videos.append({
                        'id': video_id.group(1),
                        'content': link.get_text(strip=True) or "TikTok video",
                        'url': f"https://www.tiktok.com{href}" if href.startswith('/') else href,
                        'source': 'TikTok'
                    })
            
            return videos

        except Exception as e:
            logger.error(f"Error in HTTP-based TikTok scraping: {e}")
            return []

    def _parse_tiktok_json(self, data):
        videos = []
        try:
            # Navigate the TikTok JSON structure
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
            
            # Extract video data from the structure
            if 'id' in data and 'desc' in data:
                videos.append({
                    'id': str(data.get('id')),
                    'content': data.get('desc', ''),
                    'url': f"https://www.tiktok.com/@{self.handle}/video/{data.get('id')}",
                    'source': 'TikTok'
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
            logger.error(f"TikTok scraping is disabled because a dependency is missing: {e}")
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
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        driver = None
        try:
            # Try to use system Chrome first (more reliable on VPS)
            try:
                service = Service('/usr/bin/chromedriver')
                driver = webdriver.Chrome(service=service, options=chrome_options)
            except Exception as e:
                logger.info(f"System ChromeDriver not available: {e}, trying ChromeDriverManager")
                # Fallback to ChromeDriverManager
                try:
                    service = Service(ChromeDriverManager().install())
                    driver = webdriver.Chrome(service=service, options=chrome_options)
                except Exception as e2:
                    logger.error(f"ChromeDriverManager also failed: {e2}")
                    logger.error("TikTok scraping requires Chrome/ChromeDriver to be installed on the VPS")
                    return []
            logger.info(f"Scraping TikTok profile with Selenium: {self.url}")
            driver.get(self.url)
            
            # Wait for video items to load
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "[data-e2e='user-post-item']"))
            )
            
            # Scroll down a bit to ensure items are rendered
            driver.execute_script("window.scrollTo(0, 500);")
            import time
            time.sleep(2)

            soup = BeautifulSoup(driver.page_source, 'lxml')
            videos = []
            
            video_items = soup.select("[data-e2e='user-post-item']")
            logger.info(f"Found {len(video_items)} TikTok videos with Selenium")

            for item in video_items:
                link_tag = item.find('a')
                if not link_tag or 'href' not in link_tag.attrs:
                    continue
                
                video_url = link_tag['href']
                video_id = video_url.split('/')[-1].split('?')[0]
                
                desc_tag = item.find('img')
                description = desc_tag['alt'] if desc_tag and 'alt' in desc_tag.attrs else ""

                videos.append({
                    'id': video_id,
                    'content': description,
                    'url': video_url,
                    'source': 'TikTok'
                })
            
            return videos
        except Exception as e:
            logger.error(f"Error scraping TikTok with Selenium: {e}")
            return []
        finally:
            if driver:
                driver.quit()

if __name__ == "__main__":
    # Test
    logging.basicConfig(level=logging.INFO)
    scraper = TikTokScraper("rimera_official")
    print(scraper.get_latest_videos())
