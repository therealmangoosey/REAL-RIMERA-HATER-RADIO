import os
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from scrapers.twitter_scraper import TwitterScraper
from scrapers.social_scraper import SocialScraper
from scrapers.website_scraper import WebsiteScraper
from state_manager import StateManager
# TikTok requires Selenium/Chrome, so we'll skip it in basic CI-like tests but can test manually

class TestScrapers(unittest.TestCase):
    def test_twitter_init(self):
        scraper = TwitterScraper("test", ["https://nitter.net"])
        self.assertEqual(scraper.handle, "test")

    def test_website_init(self):
        scraper = WebsiteScraper()
        self.assertEqual(scraper.url, "https://rimerarimera.com")

    @patch('scrapers.website_scraper.requests.get')
    def test_website_shopify_products_include_stock_status(self, mock_get):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "products": [{
                "id": 123,
                "title": "Rimera CD",
                "handle": "rimera-cd",
                "body_html": "<p>Limited CD with instrumentals.</p>",
                "image": {"src": "https://example.com/cd.jpg"},
                "variants": [
                    {"price": "10.00", "available": False},
                    {"price": "10.00", "available": True},
                ],
            }]
        }
        mock_get.return_value = response

        products = WebsiteScraper().get_latest_products()

        self.assertEqual(products[0]["id"], "123")
        self.assertFalse(products[0]["sold_out"])
        self.assertEqual(products[0]["variants_available"], 1)
        self.assertEqual(products[0]["url"], "https://rimerarimera.com/products/rimera-cd")
        self.assertEqual(products[0]["description"], "Limited CD with instrumentals.")
        self.assertEqual(products[0]["image_url"], "https://example.com/cd.jpg")

    @patch('scrapers.social_scraper.requests.get')
    def test_social_scraper_reads_youtube_atom_feed(self, mock_get):
        response = Mock()
        response.status_code = 200
        response.content = b'''<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/">
          <entry>
            <id>yt:video:test</id>
            <title>New video</title>
            <link rel="alternate" href="https://www.youtube.com/watch?v=test"/>
            <published>2026-05-21T12:00:00+00:00</published>
            <media:group>
              <media:description>Video description</media:description>
              <media:thumbnail url="https://example.com/thumb.jpg"/>
            </media:group>
          </entry>
        </feed>'''
        mock_get.return_value = response

        updates = SocialScraper({"youtube_channel_id": "UCtest"}).get_youtube_updates()

        self.assertEqual(updates[0]["source"], "YouTube")
        self.assertEqual(updates[0]["title"], "New video")
        self.assertEqual(updates[0]["image_url"], "https://example.com/thumb.jpg")

    @patch('scrapers.social_scraper.requests.get')
    def test_social_scraper_reads_tumblr_rss_feed(self, mock_get):
        response = Mock()
        response.status_code = 200
        response.content = b'''<?xml version="1.0" encoding="UTF-8"?>
        <rss><channel><item>
          <title>New post</title>
          <link>https://example.tumblr.com/post/1</link>
          <guid>post-1</guid>
          <description><![CDATA[<p>Post body</p><img src="https://example.com/post.jpg" />]]></description>
        </item></channel></rss>'''
        mock_get.return_value = response

        updates = SocialScraper({"tumblr_url": "https://example.tumblr.com"}).get_tumblr_updates()

        self.assertEqual(updates[0]["source"], "Tumblr")
        self.assertEqual(updates[0]["description"], "Post body")
        self.assertEqual(updates[0]["image_url"], "https://example.com/post.jpg")

    def test_product_updates_detect_restock_after_first_run(self):
        with TemporaryDirectory() as temp_dir:
            cache_path = os.path.join(temp_dir, "cache.json")
            state = StateManager(cache_file=cache_path)
            state.state = {"Website": {}}
            state.get_product_updates([{
                "id": "cd",
                "title": "Rimera CD",
                "sold_out": True,
                "available": False,
            }])

            updates = state.get_product_updates([{
                "id": "cd",
                "title": "Rimera CD",
                "sold_out": False,
                "available": True,
            }])

        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0]["event_type"], "restocked")

if __name__ == '__main__':
    unittest.main()
