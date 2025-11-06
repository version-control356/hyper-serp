# local_crawler/scraper.py
# Multi-engine meta search with fallbacks and URL dedupe.
# Engines: DuckDuckGo (HTML), Brave (RSS), Startpage (HTML best-effort),
# Wikipedia (API), GitHub (HTML). No API keys required.

from __future__ import annotations
import requests, time, random, urllib.parse, re
from typing import List, Dict
from bs4 import BeautifulSoup
from xml.etree import ElementTree as ET

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
HDRS = {
    "User-Agent": UA,
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

def _sleep():
    time.sleep(random.uniform(0.5, 1.1))

def _canonical_url(url: str) -> str:
    if not url:
        return ""
    url = url.strip()
    if url.startswith("//"):
        url = "https:" + url
    # strip DDG redirect
    if "duckduckgo.com/l/?" in url and "uddg=" in url:
        try:
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            real = q.get("uddg", [None])[0]
            if real:
                return urllib.parse.unquote(real)
        except:
            pass
    # remove common trackers
    parsed = urllib.parse.urlsplit(url)
    params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)
    STRIP = {"utm_source","utm_medium","utm_campaign","utm_term","utm_content","gclid","fbclid","utm_id"}
    params = [(k,v) for (k,v) in params if k not in STRIP]
    new_query = urllib.parse.urlencode(params, doseq=True)
    return urllib.parse.urlunsplit(("https", parsed.netloc.lower(), parsed.path, new_query, ""))

def _get(url: str, params: dict | None = None, headers: dict | None = None, timeout: int = 15):
    try:
        r = requests.get(url, params=params, headers=headers or HDRS, timeout=timeout)
        if r.status_code == 200:
            return r
        # duckduckgo sometimes 202 → try mirror
        return None
    except:
        return None

# -------------------------------
# DuckDuckGo (HTML) – primary
# -------------------------------
def scrape_duckduckgo(query: str, pages: int = 1, per_page: int = 10) -> List[Dict]:
    results: List[Dict] = []
    pages = max(1, min(pages, 3))
    for p in range(pages):
        params = {"q": query}
        r = _get("https://duckduckgo.com/html/", params=params)
        # try HTML mirror if main blocks
        if r is None:
            r = _get("https://html.duckduckgo.com/html/", params=params)
        if r is None:
            break

        soup = BeautifulSoup(r.text, "html.parser")
        # DDG classic HTML layout
        for blk in soup.select("div.result__body"):
            a = blk.select_one("a.result__a")
            if not a:
                continue
            title = a.get_text(" ", strip=True)
            href = _canonical_url(a.get("href", ""))
            sn = blk.select_one(".result__snippet")
            snippet = sn.get_text(" ", strip=True) if sn else ""
            if href:
                results.append({"title": title, "url": href, "snippet": snippet})
            if len(results) >= per_page:
                break
        if len(results) >= per_page:
            break
        _sleep()
    return results[:per_page]

# -------------------------------
# Brave Search (RSS) – secondary
# -------------------------------
def scrape_brave_rss(query: str, max_results: int = 10) -> List[Dict]:
    # Brave has an RSS view that often works without keys
    url = "https://search.brave.com/search"
    params = {"q": query, "source": "rss"}
    r = _get(url, params=params, headers={"User-Agent": UA, "Accept": "application/rss+xml"})
    out: List[Dict] = []
    if r is None:
        return out
    try:
        root = ET.fromstring(r.text.encode("utf-8", errors="ignore"))
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = _canonical_url(item.findtext("link") or "")
            desc = (item.findtext("description") or "").strip()
            if link:
                out.append({"title": title, "url": link, "snippet": desc})
            if len(out) >= max_results:
                break
    except Exception:
        return []
    return out

# -------------------------------
# Startpage (HTML) – tertiary (best-effort)
# -------------------------------
def scrape_startpage(query: str, max_results: int = 10) -> List[Dict]:
    out: List[Dict] = []
    params = {"query": query}
    r = _get("https://www.startpage.com/do/search", params=params)
    if r is None:
        return out
    soup = BeautifulSoup(r.text, "html.parser")
    # Startpage markup changes; try multiple selectors
    for wrap in soup.select("a[href].w-gl__result-title, a[href].result-link"):
        href = _canonical_url(wrap.get("href", ""))
        title = wrap.get_text(" ", strip=True)
        # snippet nearby
        snippet = ""
        par = wrap.find_parent()
        if par:
            sn = par.find(class_=re.compile("(result-|w-gl__)snippet"))
            if sn:
                snippet = sn.get_text(" ", strip=True)
        if href and title:
            out.append({"title": title, "url": href, "snippet": snippet})
        if len(out) >= max_results:
            break
    return out

# -------------------------------
# Wikipedia (API) – factual fallback
# -------------------------------
def scrape_wikipedia(query: str, max_results: int = 5) -> List[Dict]:
    # opensearch returns [query, titles[], descs[], urls[]]
    try:
        r = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={"action": "opensearch", "search": query, "limit": max_results, "namespace": 0, "format": "json"},
            headers={"User-Agent": UA},
            timeout=12,
        )
        if r.status_code != 200:
            return []
        data = r.json()
        out = []
        titles = data[1] if len(data) > 1 else []
        descs  = data[2] if len(data) > 2 else []
        urls   = data[3] if len(data) > 3 else []
        for t, d, u in zip(titles, descs, urls):
            out.append({"title": t, "url": _canonical_url(u), "snippet": d})
        return out[:max_results]
    except:
        return []

# -------------------------------
# GitHub (HTML) – always include (as requested)
# -------------------------------
def scrape_github(query: str, max_results: int = 5) -> List[Dict]:
    # Repos search
    params = {"q": query, "type": "repositories", "s": "stars"}
    r = _get("https://github.com/search", params=params)
    out: List[Dict] = []
    if r is None:
        return out
    soup = BeautifulSoup(r.text, "html.parser")
    for item in soup.select("a.v-align-middle"):
        href = item.get("href") or ""
        if not href.startswith("http"):
            href = "https://github.com" + href
        title = item.get_text(" ", strip=True)
        # description
        desc_el = item.find_parent().find_next("p")
        snippet = desc_el.get_text(" ", strip=True) if desc_el else ""
        out.append({"title": title, "url": _canonical_url(href), "snippet": snippet})
        if len(out) >= max_results:
            break
    return out

# -------------------------------
# Multi-engine meta search + dedupe
# -------------------------------
def smart_meta_search(query: str, max_results: int = 10, summarize_wiki: bool = True) -> List[Dict]:
    seen = set()
    merged: List[Dict] = []

    def add(batch: List[Dict]):
        for r in batch:
            url = _canonical_url(r.get("url", ""))
            if not url or url in seen:
                continue
            seen.add(url)
            merged.append({"title": r.get("title",""), "url": url, "snippet": r.get("snippet","")})

    # 1) DuckDuckGo
    add(scrape_duckduckgo(query, pages=1, per_page=max_results))

    # 2) Brave RSS fallback if we still need more
    if len(merged) < max_results:
        add(scrape_brave_rss(query, max_results=max_results - len(merged)))

    # 3) Startpage
    if len(merged) < max_results:
        add(scrape_startpage(query, max_results=max_results - len(merged)))

    # 4) Wikipedia (summaries)
    if len(merged) < max_results:
        wiki = scrape_wikipedia(query, max_results=max_results - len(merged))
        if summarize_wiki and wiki:
            try:
                # Lazy import to avoid backend dependency cycle
                from utils.llm import summarize
                for w in wiki:
                    if w.get("snippet"):
                        w["snippet"] = summarize(w["snippet"]) or w["snippet"]
            except Exception:
                pass
        add(wiki)

    # 5) GitHub (always include as requested)
    if len(merged) < max_results:
        add(scrape_github(query, max_results=max_results - len(merged)))

    # Cap
    return merged[:max_results]
