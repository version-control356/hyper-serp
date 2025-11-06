# fetcher/fetch_and_extract.py
import requests
from bs4 import BeautifulSoup
import trafilatura
import time
import random

DEFAULT_HEADERS = {
    "User-Agent": "HyperSerp/1.0 (+https://example.com) Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept-Language": "en-US,en;q=0.9"
}

def fetch_html(url: str, timeout=15, headers=None):
    headers = headers or DEFAULT_HEADERS
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        if r.status_code == 200 and 'text/html' in r.headers.get('content-type',''):
            return r.text
    except Exception as e:
        # log quietly
        print(f"[fetch] error fetching {url}: {e}")
    return None

def extract_text(url: str, html: str = None):
    """
    Use trafilatura first (good for main content extraction), then fallback to soup.
    Return: dict(title, text, lang)
    """
    if html is None:
        html = fetch_html(url)
        if html is None:
            return None
    text = trafilatura.extract(html, include_comments=False, include_tables=False)
    if text:
        title = None
        try:
            soup = BeautifulSoup(html, "html.parser")
            title = soup.title.string.strip() if soup.title else None
        except:
            title = None
        return {"title": title or "", "text": text, "url": url}
    # fallback: simple extraction
    soup = BeautifulSoup(html, "html.parser")
    paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    joined = "\n\n".join(paragraphs)
    if not joined.strip():
        return None
    title = soup.title.string.strip() if soup.title else ""
    return {"title": title, "text": joined, "url": url}

if __name__ == "__main__":
    url = "https://en.wikipedia.org/wiki/Semantic_search"
    html = fetch_html(url)
    doc = extract_text(url, html)
    print(doc["title"])
    print(doc["text"][:500])
