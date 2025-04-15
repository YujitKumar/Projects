from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import random
from urllib.parse import urljoin, urlparse
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple
import csv
import os
import pandas as pd
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

@dataclass
class Product:
    title: str
    price: str
    rating: Optional[str]
    reviews: Optional[str]
    delivery: Optional[str]
    url: str
    sponsored: bool = False
    deal: Optional[str] = None

class AmazonScraper:
    def __init__(self, visible_browser=False):
        self.base_url = "https://www.amazon.in"
        self.visible_browser = visible_browser
        self.driver = self._init_driver()
        self.delay_range = (1, 3)

    def _init_driver(self):
        options = Options()
        if not self.visible_browser:
            options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--log-level=3")  # Suppress WebGL warnings
        options.add_argument("--silent")
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        driver = webdriver.Chrome(options=options)
        return driver

    def _random_delay(self):
        delay = random.uniform(*self.delay_range)
        time.sleep(delay)

    def _validate_amazon_url(self, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.netloc.endswith('amazon.in') or parsed.netloc.endswith('amazon.com')

    def _get_page(self, url: str) -> Optional[str]:
        try:
            self._random_delay()
            self.driver.get(url)
            
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.s-result-item")))
            
            if "api-services-support@amazon.com" in self.driver.page_source:
                raise Exception("CAPTCHA detected - Amazon is blocking requests")
                
            return self.driver.page_source
        except Exception as e:
            logger.error(f"Error loading page {url}: {e}")
            return None

    def _extract_product_data(self, item) -> Optional[Product]:
        try:
            link = item.select_one('h2 a.a-link-normal, a.a-link-normal.s-line-clamp-2, a.a-link-normal.s-line-clamp-3')
            if not link:
                return None
                
            raw_url = link.get('href', '')
            product_url = urljoin(self.base_url, raw_url.split('?')[0])
            title = link.get_text(strip=True)

            price_whole = item.select_one('span.a-price-whole')
            price = price_whole.get_text(strip=True).replace(',', '') if price_whole else None

            rating = item.select_one('span.a-icon-alt')
            rating = rating.get_text(strip=True).split()[0] if rating else None

            reviews = item.select_one('span.a-size-base[aria-label], span.a-size-base.s-underline-text')
            reviews = reviews.get_text(strip=True) if reviews else None

            delivery = item.select_one('span.a-color-base.a-text-bold')
            delivery = delivery.get_text(strip=True) if delivery else None

            deal = item.select_one('span.a-badge-text')
            deal = deal.get_text(strip=True) if deal else None

            sponsored = bool(item.select_one('span.a-color-secondary:contains("Sponsored"), span:contains("Sponsored Ad")'))

            return Product(
                title=title,
                price=price,
                rating=rating,
                reviews=reviews,
                delivery=delivery,
                url=product_url,
                sponsored=sponsored,
                deal=deal
            )
        except Exception as e:
            logger.error(f"Error extracting product data: {e}")
            return None

    def _get_next_page_url(self, soup) -> Optional[str]:
        next_button = soup.select_one('a.s-pagination-next')
        if next_button and not 'a-disabled' in next_button.get('class', []):
            return urljoin(self.base_url, next_button['href'])
        return None

    def scrape_amazon(self, search_query: str, max_pages: int = 1) -> List[Product]:
        if not search_query:
            return []
            
        all_products = []
        current_page = 1
        current_url = search_query  # Use the full URL provided
        
        try:
            while current_url and current_page <= max_pages:
                logger.info(f"Scraping page {current_page}")
                html = self._get_page(current_url)
                if not html:
                    break

                soup = BeautifulSoup(html, 'html.parser')
                items = soup.select('div.s-result-item[data-component-type="s-search-result"]')
                
                page_products = []
                for item in items:
                    product = self._extract_product_data(item)
                    if product:
                        page_products.append(product)
                
                all_products.extend(page_products)
                logger.info(f"Found {len(page_products)} products on page {current_page}")

                # Get next page URL
                current_url = self._get_next_page_url(soup)
                current_page += 1
                
                if not current_url:
                    break
                    
                self._random_delay()

            # Save the results
            if all_products:
                # Ensure output directory exists
                os.makedirs('output', exist_ok=True)
                
                # Save as CSV
                df = pd.DataFrame([p.__dict__ for p in all_products])
                df.to_csv('output/amazon_products.csv', index=False)
                logger.info(f"Saved {len(all_products)} products to CSV")
                
                # Save as Excel
                df.to_excel('output/amazon_products.xlsx', index=False)
                logger.info(f"Saved {len(all_products)} products to Excel")
                
                # Save as JSON
                with open('output/amazon_products.json', 'w', encoding='utf-8') as f:
                    json.dump([p.__dict__ for p in all_products], f, indent=2)
                logger.info(f"Saved {len(all_products)} products to JSON")

            return all_products

        except Exception as e:
            logger.error(f"Error during scraping: {e}")
            return []
        finally:
            self.close()

    def close(self):
        self.driver.quit()