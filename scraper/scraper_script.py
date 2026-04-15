import requests
from bs4 import BeautifulSoup
import json
import os

# Ensure the data directory exists
current_dir = os.path.dirname(os.path.abspath(__file__))

os.makedirs(os.path.join(current_dir, "data"), exist_ok=True)

# URLs you want to scrape (e.g., their Services or Career page)
URLS_TO_SCRAPE = [
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

def scrape_page(url):
    print(f"Scraping {url}...")
    try:
        response = requests.get(url)
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

def main():
    scraped_data = []
    
    for url in URLS_TO_SCRAPE:
        data = scrape_page(url)
        if data:
            scraped_data.append(data)
            
    # Save to JSON
    output_path = os.path.join(current_dir, "data", "knowledge.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(scraped_data, f, indent=4, ensure_ascii=False)
        
    print(f"Successfully saved {len(scraped_data)} pages to {output_path}")

if __name__ == "__main__":
    main()