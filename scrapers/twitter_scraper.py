import logging
import os
import random

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

logger = logging.getLogger('rimera-bot.twitter')
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


class TwitterScraper:
    def __init__(self, handle, instances):
        self.handle = handle
        self.instances = [instance.rstrip('/') for instance in instances if instance]

    def get_latest_tweets(self):
        shuffled_instances = self.instances[:]
        random.shuffle(shuffled_instances)

        for instance in shuffled_instances:
            try:
                url = f"{instance}/{self.handle}"
                logger.info(f"Scraping Nitter instance: {url}")
                proxy = get_random_proxy()
                if proxy:
                    logger.info("Using configured proxy")

                response = requests.get(
                    url,
                    timeout=15,
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Linux; Android 11) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.9',
                        'DNT': '1',
                        'Connection': 'keep-alive',
                    },
                    proxies=proxy,
                )

                if response.status_code != 200:
                    logger.warning(f"Failed to scrape {instance}: Status {response.status_code}")
                    continue

                soup = BeautifulSoup(response.text, 'lxml')
                tweets = []
                for item in soup.find_all('div', class_='timeline-item'):
                    link_tag = item.find('a', class_='tweet-link')
                    if not link_tag or not link_tag.get('href'):
                        continue
                    tweet_id = link_tag['href'].split('/')[-1].split('#')[0]
                    if not tweet_id:
                        continue
                    content_tag = item.find('div', class_='tweet-content')
                    content = content_tag.get_text(strip=True) if content_tag else ""
                    timestamp_tag = item.find('span', class_='tweet-date')
                    anchor = timestamp_tag.find('a') if timestamp_tag else None
                    timestamp = anchor.get('title', '') if anchor else ""
                    tweets.append({
                        'id': tweet_id,
                        'content': content,
                        'url': f"https://twitter.com/{self.handle}/status/{tweet_id}",
                        'timestamp': timestamp,
                        'source': 'Twitter',
                    })

                return tweets
            except requests.RequestException as e:
                logger.warning(f"Request failed for {instance}: {e}")
            except Exception as e:
                logger.error(f"Error scraping {instance}: {e}")

        return []


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scraper = TwitterScraper("rimera_official", ["https://nitter.net"])
    print(scraper.get_latest_tweets())
