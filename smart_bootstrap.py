# smart_bootstrap.py
from typing import List, Dict, Set
from local_fetcher.fetch_and_extract import fetch_html, extract_text
from indexer.index_builder import Builder
from utils.url import canonical_url
from fallback_sources import SEED_URLS

def bootstrap_index(builder: Builder, max_pages: int = 80) -> int:
    """
    Fetch & ingest a curated set of public pages once at startup.
    Idempotent enough for demos; minimal dedup by canonical URL.
    """
    seen: Set[str] = set()
    docs: List[Dict] = []

    for url in SEED_URLS[:max_pages]:
        cu = canonical_url(url)
        if not cu or cu in seen:
            continue
        html = fetch_html(cu)
        if not html:
            continue
        d = extract_text(cu, html)
        if not d or not (d.get("text") or "").strip():
            continue
        d["snippet"] = (d.get("text", "")[:300]).replace("\n", " ")
        docs.append(d)
        seen.add(cu)

    if not docs:
        return 0
    builder.ingest_docs(docs)
    return len(docs)
