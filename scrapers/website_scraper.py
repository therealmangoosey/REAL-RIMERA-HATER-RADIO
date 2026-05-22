import requests
from bs4 import BeautifulSoup
import logging
from urllib.parse import urljoin
import random
import os
from dotenv import load_dotenv

logger = logging.getLogger('rimera-bot.website')

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

class WebsiteScraper:
    def __init__(self, url="https://rimerarimera.com"):
        self.url = url.rstrip('/')
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0'
        }

    def get_latest_products(self):
        # Try Shopify Storefront API first (public GraphQL)
        products = self._get_products_from_storefront_api()
        if products:
            return products

        # Try products.json endpoint
        products = self._get_products_from_shopify_json()
        if products:
            return products

        # Fallback to collection page scraping
        return self._get_products_from_collection_page()

    def _get_products_from_storefront_api(self):
        try:
            # Extract shop domain from URL
            from urllib.parse import urlparse
            parsed = urlparse(self.url)
            shop_domain = parsed.netloc.replace('www.', '')
            
            # Shopify Storefront API endpoint
            api_url = f"https://{shop_domain}/api/2024-01/graphql.json"
            
            # GraphQL query to fetch products
            query = """
            {
                products(first: 20, sortKey: CREATED_AT, reverse: true) {
                    edges {
                        node {
                            id
                            title
                            description
                            handle
                            availableForSale
                            priceRange {
                                minVariantPrice {
                                    amount
                                    currencyCode
                                }
                            }
                            images(first: 1) {
                                edges {
                                    node {
                                        url
                                    }
                                }
                            }
                            createdAt
                        }
                    }
                }
            }
            """
            
            logger.info(f"Trying Shopify Storefront API: {api_url}")
            proxy = get_random_proxy()
            if proxy:
                logger.info(f"Using proxy: {proxy['http'][:30]}...")
            
            session = requests.Session()
            session.headers.update({
                'Content-Type': 'application/json',
                'X-Shopify-Storefront-Access-Token': '',  # Public API doesn't require token for basic queries
            })
            
            response = session.post(api_url, json={'query': query}, proxies=proxy, timeout=15)
            
            if response.status_code != 200:
                logger.warning(f"Storefront API failed with status {response.status_code}")
                return []
            
            data = response.json()
            products = []
            
            if 'data' in data and 'products' in data['data']:
                for edge in data['data']['products']['edges']:
                    product = edge['node']
                    # Extract numeric ID from Shopify GID
                    product_id = product['id'].split('/').pop() if '/' in product['id'] else product['id']
                    
                    image_url = None
                    if product.get('images') and product['images'].get('edges'):
                        image_url = product['images']['edges'][0]['node']['url']
                    
                    price = ""
                    if product.get('priceRange') and product['priceRange'].get('minVariantPrice'):
                        price_info = product['priceRange']['minVariantPrice']
                        price = f"{price_info.get('currencyCode', 'USD')} {price_info.get('amount', '0.00')}"
                    
                    products.append({
                        'id': product_id,
                        'content': product.get('description', '') or product.get('title', 'Product update'),
                        'url': f"{self.url}/products/{product['handle']}",
                        'source': 'Website',
                        'title': product.get('title', 'Product update'),
                        'description': product.get('description', ''),
                        'price': price,
                        'sold_out': not product.get('availableForSale', True),
                        'available': product.get('availableForSale', True),
                        'image_url': image_url,
                        'published_at': product.get('createdAt', ''),
                    })
                
                logger.info(f"Found {len(products)} products from Storefront API")
                return products
            
            return []
            
        except Exception as e:
            logger.error(f"Error with Storefront API: {e}")
            return []

    def _get_products_from_shopify_json(self):
        try:
            target_url = f"{self.url}/products.json?limit=250"
            logger.info(f"Scraping Shopify products endpoint: {target_url}")
            # Use a session for better connection handling
            proxy = get_random_proxy()
            if proxy:
                logger.info(f"Using proxy: {proxy['http'][:30]}...")
            
            session = requests.Session()
            session.headers.update(self.headers)
            response = session.get(target_url, proxies=proxy, timeout=15)

            if response.status_code != 200:
                logger.warning(f"Failed to scrape products endpoint: Status {response.status_code}")
                logger.debug(f"Response content: {response.text[:500]}")
                return []

            # Check if response is actually JSON
            try:
                data = response.json()
            except ValueError as e:
                logger.error(f"Failed to parse JSON response: {e}")
                logger.debug(f"Response content: {response.text[:500]}")
                return []
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
            proxy = get_random_proxy()
            if proxy:
                logger.info(f"Using proxy: {proxy['http'][:30]}...")
            
            session = requests.Session()
            session.headers.update(self.headers)
            response = session.get(target_url, proxies=proxy, timeout=15)

            if response.status_code != 200:
                logger.warning(f"Failed to scrape collection page: Status {response.status_code}")
                logger.debug(f"Response content: {response.text[:500]}")
                return []

            soup = BeautifulSoup(response.text, 'lxml')
            products = []

            # Common Shopify selectors - expanded list
            product_items = soup.select('.grid-view-item, .product-card, .grid__item, .card-wrapper, li.grid__item, .product-item, .product-list-item, [data-product], .product')
            logger.info(f"Found {len(product_items)} potential product items")
            
            if len(product_items) == 0:
                # Log some of the HTML to debug
                logger.debug(f"Page HTML snippet: {str(soup)[:1000]}")
                # Try to find any links that might be products
                all_links = soup.find_all('a', href=True)
                product_links = [a for a in all_links if '/products/' in a.get('href', '')]
                logger.info(f"Found {len(product_links)} links with /products/ in href")

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
