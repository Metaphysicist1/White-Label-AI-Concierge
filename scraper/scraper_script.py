import requests
from bs4 import BeautifulSoup
import json
import os
from pathlib import Path
from urllib.parse import urljoin, urlparse
from collections import deque

# Ensure the data directory exists
current_dir = os.path.dirname(os.path.abspath(__file__))

os.makedirs(os.path.join(current_dir, "data"), exist_ok=True)

# Default fallback URLs
DEFAULT_URLS_TO_SCRAPE = [
    "https://de.dussmann.de/", 
    "https://en.dussmann.de/",
    "https://de.dussmann.de/news-stories",
    "https://en.dussmann.de/news-stories",
    "https://de.dussmann.de/kontakt",
    "https://de.dussmann.de/standorte#/?country=DE",
    "https://de.dussmann.de/ueber-uns",
    "https://en.dussmann.de/about-us",
    "https://de.dussmann.de/ueber-uns/unternehmen",
    "https://de.dussmann.de/ueber_uns/integriertes-managementsystem",
    "https://de.dussmann.de/ueber-uns/nachhaltigkeit"
]

URLS_FILE_PATH = os.path.join(current_dir, "data", "urls.txt")
REQUEST_TIMEOUT_SECONDS = 15
MAX_PAGES_PER_DOMAIN = 20
MAX_CRAWL_DEPTH = 2

def scrape_page(url):
    print(f"Scraping {url}...")
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract title
        title = soup.title.string if soup.title else "No Title"
        
        # Extract main text (removing scripts, styles, and extra whitespace)
        for script in soup(["script", "style", "nav", "footer"]):
            script.decompose()
            
        text = soup.get_text(separator=' ')
        clean_text = ' '.join(text.split())
        
        return {
            "url": url,
            "title": title,
            "content": clean_text
        }
    except Exception as e:
        print(f"Failed to scrape {url}: {e}")
        return None

def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    normalized = parsed._replace(fragment="", query="")
    return normalized.geturl().rstrip("/")

def same_domain(url: str, root_domain: str) -> bool:
    return urlparse(url).netloc == root_domain

def extract_internal_links(soup: BeautifulSoup, base_url: str, root_domain: str) -> list[str]:
    links: list[str] = []
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        absolute = urljoin(base_url, href)
        normalized = normalize_url(absolute)
        if same_domain(normalized, root_domain):
            links.append(normalized)
    return links

def crawl_domain(seed_url: str, max_pages: int = MAX_PAGES_PER_DOMAIN, max_depth: int = MAX_CRAWL_DEPTH):
    seed = normalize_url(seed_url)
    domain = urlparse(seed).netloc

    queue = deque([(seed, 0)])
    visited: set[str] = set()
    scraped_items: list[dict] = []

    while queue and len(scraped_items) < max_pages:
        current_url, depth = queue.popleft()
        if current_url in visited:
            continue
        visited.add(current_url)

        try:
            response = requests.get(current_url, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
        except Exception as e:
            print(f"Failed to crawl {current_url}: {e}")
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        for script in soup(["script", "style", "nav", "footer"]):
            script.decompose()

        title = soup.title.string if soup.title else "No Title"
        text = soup.get_text(separator=" ")
        clean_text = " ".join(text.split())
        if clean_text:
            scraped_items.append(
                {
                    "url": current_url,
                    "title": title,
                    "content": clean_text,
                }
            )
            print(f"Crawled ({len(scraped_items)}/{max_pages}): {current_url}")

        if depth >= max_depth:
            continue

        for link in extract_internal_links(soup, current_url, domain):
            if link not in visited:
                queue.append((link, depth + 1))

    return scraped_items

def load_urls() -> list[str]:
    urls_file = Path(URLS_FILE_PATH)
    if urls_file.exists():
        lines = [line.strip() for line in urls_file.read_text(encoding="utf-8").splitlines()]
        urls = [line for line in lines if line and not line.startswith("#")]
        if urls:
            print(f"Loaded {len(urls)} URLs from {URLS_FILE_PATH}")
            return urls
    print("Using default URL list from script.")
    return DEFAULT_URLS_TO_SCRAPE

def main():
    scraped_data = []
    urls_to_scrape = load_urls()
    
    for url in urls_to_scrape:
        scraped_data.extend(crawl_domain(url))
            
    # Save to JSON
    output_path = os.path.join(current_dir, "data", "knowledge.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(scraped_data, f, indent=4, ensure_ascii=False)
        
    print(f"Successfully saved {len(scraped_data)} pages to {output_path}")

if __name__ == "__main__":
    main()