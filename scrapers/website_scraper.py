import requests
from bs4 import BeautifulSoup
import logging
from urllib.parse import urljoin

logger = logging.getLogger('rimera-bot.website')

class WebsiteScraper:
    def __init__(self, url="https://rimerarimera.com"):
        self.url = url.rstrip('/')
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36'
        }

    def get_latest_products(self):
        products = self._get_products_from_shopify_json()
        if products:
            return products

        return self._get_products_from_collection_page()

    def _get_products_from_shopify_json(self):
        try:
            target_url = f"{self.url}/products.json?limit=250"
            logger.info(f"Scraping Shopify products endpoint: {target_url}")
            response = requests.get(target_url, timeout=15, headers=self.headers)

            if response.status_code != 200:
                logger.warning(f"Failed to scrape products endpoint: Status {response.status_code}")
                return []

            data = response.json()
            products = []

            for product in data.get('products', []):
                variants = product.get('variants', [])
                available_variants = [variant for variant in variants if variant.get('available')]
                first_variant = variants[0] if variants else {}
                images = product.get('images') or []
                image = product.get('image') or (images[0] if images else {})
                price = first_variant.get('price') or ""
                handle = product.get('handle') or str(product.get('id'))
                description = self._clean_html(product.get('body_html', ''))

                products.append({
                    'id': str(product.get('id') or handle),
                    'content': description or product.get('title', 'Product update'),
                    'url': f"{self.url}/products/{handle}",
                    'source': 'Website',
                    'title': product.get('title', 'Product update'),
                    'description': description,
                    'price': self._format_price(price),
                    'sold_out': len(available_variants) == 0,
                    'available': len(available_variants) > 0,
                    'variants_available': len(available_variants),
                    'variants_total': len(variants),
                    'image_url': image.get('src') if isinstance(image, dict) else None,
                    'published_at': product.get('published_at') or '',
                })

            logger.info(f"Found {len(products)} products from Shopify endpoint")
            return products
        except Exception as e:
            logger.error(f"Error scraping Shopify products endpoint: {e}")
            return []

    def _get_products_from_collection_page(self):
        try:
            logger.info(f"Scraping collection page: {self.url}")
            target_url = f"{self.url}/collections/all"
            response = requests.get(target_url, timeout=15, headers=self.headers)

            if response.status_code != 200:
                logger.warning(f"Failed to scrape collection page: Status {response.status_code}")
                return []

            soup = BeautifulSoup(response.text, 'lxml')
            products = []

            # Common Shopify selectors
            product_items = soup.select('.grid-view-item, .product-card, .grid__item, .card-wrapper, li.grid__item')
            logger.info(f"Found {len(product_items)} potential product items")

            for item in product_items:
                link_tag = item.find('a', href=True)
                if not link_tag:
                    continue
                
                # Filter for actual product links
                href = link_tag['href']
                if '/products/' not in href:
                    continue

                product_url = urljoin(self.url, href)
                product_id = href.split('/')[-1].split('?')[0]

                title_tag = item.select_one('.grid-view-item__title, .product-card__title, .card__heading, h3, .h4')
                title = title_tag.get_text(strip=True) if title_tag else "New Product"

                price_tag = item.select_one('.price, .product-card__price, .grid-view-item__meta')
                price = price_tag.get_text(strip=True) if price_tag else ""

                item_text = item.get_text(" ", strip=True).lower()
                item_html = str(item).lower()
                sold_out = (
                    "sold out" in item_text
                    or "out of stock" in item_text
                    or "sold-out" in item_html
                    or "sold_out" in item_html
                )
                image_tag = item.find('img')
                image_url = None
                if image_tag:
                    image_src = image_tag.get('src') or image_tag.get('data-src')
                    image_url = urljoin('https:', image_src) if image_src and image_src.startswith('//') else image_src

                products.append({
                    'id': product_id,
                    'content': title,
                    'url': product_url,
                    'source': 'Website',
                    'title': title,
                    'description': '',
                    'price': price,
                    'sold_out': sold_out,
                    'available': not sold_out,
                    'image_url': image_url,
                })

            return products
        except Exception as e:
            logger.error(f"Error scraping collection page: {e}")
            return []

    @staticmethod
    def _format_price(price):
        if price in (None, ""):
            return ""
        try:
            return f"GBP {float(price):.2f}"
        except (TypeError, ValueError):
            return str(price)

    @staticmethod
    def _clean_html(html):
        if not html:
            return ""
        return BeautifulSoup(html, 'lxml').get_text(" ", strip=True)

if __name__ == "__main__":
    # Test
    logging.basicConfig(level=logging.INFO)
    scraper = WebsiteScraper()
    print(scraper.get_latest_products())
