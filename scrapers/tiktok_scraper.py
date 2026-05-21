from bs4 import BeautifulSoup
import logging
import time

logger = logging.getLogger('rimera-bot.tiktok')

class TikTokScraper:
    def __init__(self, handle):
        self.handle = handle
        self.url = f"https://www.tiktok.com/@{handle}"

    def get_latest_videos(self):
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
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

        driver = None
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            logger.info(f"Scraping TikTok profile: {self.url}")
            driver.get(self.url)
            
            # Wait for video items to load
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "[data-e2e='user-post-item']"))
            )
            
            # Scroll down a bit to ensure items are rendered
            driver.execute_script("window.scrollTo(0, 500);")
            time.sleep(2)

            soup = BeautifulSoup(driver.page_source, 'lxml')
            videos = []
            
            video_items = soup.select("[data-e2e='user-post-item']")
            logger.info(f"Found {len(video_items)} TikTok videos")

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
            logger.error(f"Error scraping TikTok: {e}")
            return []
        finally:
            if driver:
                driver.quit()

if __name__ == "__main__":
    # Test
    logging.basicConfig(level=logging.INFO)
    scraper = TikTokScraper("rimera_official")
    print(scraper.get_latest_videos())
