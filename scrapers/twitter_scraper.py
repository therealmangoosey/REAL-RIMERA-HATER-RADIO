import requests
from bs4 import BeautifulSoup
import logging
import random

logger = logging.getLogger('rimera-bot.twitter')

class TwitterScraper:
    def __init__(self, handle, instances):
        self.handle = handle
        self.instances = instances

    def get_latest_tweets(self):
        # Shuffle instances to avoid overusing one
        shuffled_instances = self.instances[:]
        random.shuffle(shuffled_instances)

        for instance in shuffled_instances:
            try:
                url = f"{instance}/{self.handle}"
                logger.info(f"Scraping Nitter instance: {url}")
                response = requests.get(url, timeout=15, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                })
                
                if response.status_code != 200:
                    logger.warning(f"Failed to scrape {instance}: Status {response.status_code}")
                    continue

                soup = BeautifulSoup(response.text, 'lxml')
                tweets = []
                
                # Nitter tweet container
                tweet_items = soup.find_all('div', class_='timeline-item')
                
                for item in tweet_items:
                    # Skip if it's a "pinned" tweet or thread container if needed, 
                    # but for now we'll take them all and let state manager handle dedupe
                    link_tag = item.find('a', class_='tweet-link')
                    if not link_tag:
                        continue
                    
                    tweet_id = link_tag['href'].split('/')[-1].split('#')[0]
                    content_tag = item.find('div', class_='tweet-content')
                    content = content_tag.get_text(strip=True) if content_tag else ""
                    
                    timestamp_tag = item.find('span', class_='tweet-date')
                    timestamp = timestamp_tag.find('a')['title'] if timestamp_tag and timestamp_tag.find('a') else ""

                    tweets.append({
                        'id': tweet_id,
                        'content': content,
                        'url': f"https://twitter.com/{self.handle}/status/{tweet_id}",
                        'timestamp': timestamp,
                        'source': 'Twitter'
                    })
                
                return tweets
            except Exception as e:
                logger.error(f"Error scraping {instance}: {e}")
                continue
        
        return []

if __name__ == "__main__":
    # Test
    logging.basicConfig(level=logging.INFO)
    scraper = TwitterScraper("rimera_official", ["https://nitter.net"])
    print(scraper.get_latest_tweets())
