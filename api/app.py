# api/app.py
import sys, os
from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from utils.local_llm_ollama import summarize_text, classify_topic, expand_query

import uvicorn

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from indexer.index_builder import Builder
from local_fetcher.fetch_and_extract import fetch_html, extract_text
from local_crawler.scraper import smart_meta_search  # ✅ multi-engine
# keep a tiny canonicalizer in app as well
def canonical_url(url: str) -> str:
    if not url: return ""
    url = url.strip()
    if url.startswith("//"): url = "https:" + url
    return url

APP_TITLE = "⚡ HyperSerp (BM25 + Multi-Engine)"

app = FastAPI(title=APP_TITLE)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

INDEX_PATH = os.environ.get("HYPER_INDEX_PATH", "bm25.index")
META_DB   = os.environ.get("HYPER_META_DB", "metadata.db")
builder = Builder(index_path=INDEX_PATH, meta_db=META_DB)

class IngestRequest(BaseModel):
    url: str
    snippet: Optional[str] = ""
    title: Optional[str] = ""

class ScrapeAndIngestRequest(BaseModel):
    query: str
    fetch_pages: Optional[bool] = True
    max_results: Optional[int] = 10

@app.get("/")
def root():
    return {"message": "✅ HyperSerp BM25 + Multi-Engine — /search, /scrape_and_ingest, /ingest, /docs"}

@app.post("/ingest")
def ingest(req: IngestRequest):
    url = canonical_url(req.url)
    html = fetch_html(url)
    if not html:
        raise HTTPException(status_code=502, detail="Failed to fetch URL")
    d = extract_text(url, html)
    if not d:
        raise HTTPException(status_code=500, detail="Failed to extract content")
    d["snippet"] = (req.snippet or d.get("text","")[:300]).replace("\n"," ")
    ids = builder.ingest_docs([d])
    return {"ingested_ids": ids}

@app.post("/scrape_and_ingest")
def scrape_and_ingest(req: ScrapeAndIngestRequest):
    serp = smart_meta_search(req.query, max_results=req.max_results, summarize_wiki=True)
    docs = []
    seen_urls = set()

    for hit in serp:
        url = canonical_url(hit.get("url",""))
        if not url:
            continue
        seen_urls.add(url)
        if req.fetch_pages:
            html = fetch_html(url)
            if not html:
                continue
            d = extract_text(url, html)
            if not d:
                continue
            d["snippet"] = (hit.get("snippet") or d.get("text","")[:300]).replace("\n"," ")
            docs.append(d)
        else:
            docs.append({"url": url, "title": hit.get("title",""), "snippet": hit.get("snippet",""), "text": ""})
    if not docs:
        return {"ingested": 0, "error": "no docs"}
    ids = builder.ingest_docs(docs)
    return {"ingested": len(ids), "ids": ids}

@app.get("/search")
def search(q: str = Query(...), top_k: int = 10, summarize_top: int = 3):
    # 0) Optional: expand short queries to improve recall (silent boost)
    expansions = expand_query(q) if len(q.split()) <= 2 else []
    combined_query = q  # you could also merge expansions into your meta search if you want

    # 1) Live multi-engine results
    serp = smart_meta_search(combined_query, max_results=10, summarize_wiki=True)
    live_docs = []
    seen_live = set()
    for hit in serp:
        url = canonical_url(hit.get("url",""))
        if not url or url in seen_live:
            continue
        html = fetch_html(url)
        if not html:
            continue
        d = extract_text(url, html)
        if not d:
            continue
        d["snippet"] = (hit.get("snippet") or d.get("text","")[:300]).replace("\n"," ")
        # attach title if extractor didn't
        d["title"] = d.get("title") or hit.get("title","") or url
        live_docs.append(d)
        seen_live.add(url)

    # 2) Ingest scraped pages into BM25 before searching
    if live_docs:
        builder.ingest_docs(live_docs)

    # 3) Local BM25 ranking
    results = builder.search(q, top_k=top_k)

    # 4) Dedupe by URL
    unique_results = []
    seen_urls = set()
    for r in results:
        url = r.get("url", "")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        unique_results.append(r)

    # 5) Fill with live_docs if BM25 < top_k
    if len(unique_results) < top_k:
        needed = top_k - len(unique_results)
        for d in live_docs:
            if d["url"] not in seen_urls:
                unique_results.append({
                    "id": "live-" + d["url"],
                    "url": d["url"],
                    "title": d.get("title") or d["url"],
                    "snippet": d["snippet"],
                    "summary": None,
                    "topic": None,
                    "score": 0.0
                })
                seen_urls.add(d["url"])
                if len(unique_results) >= top_k:
                    break

    # 6) LLM summaries & topics for the first few items (fast, local)
    for i, r in enumerate(unique_results):
        if i < summarize_top:
            try:
                # fetch page again for rich text if needed (or cache text in metadata later)
                html = fetch_html(r["url"])
                if html:
                    d = extract_text(r["url"], html)
                    txt = (d.get("text","") if d else "")[:3000]
                else:
                    txt = ""
                r["summary"] = summarize_text(txt) if txt else summarize_text(r.get("snippet",""))
                r["topic"]   = classify_topic(r.get("snippet",""))
            except Exception:
                r["summary"] = None
                r["topic"] = None
        else:
            r.setdefault("summary", None)
            r.setdefault("topic", None)

    return {
        "query": q,
        "expansions": expansions,   # show in UI as “Did you mean…”
        "results": [
            {
                "id": r["id"],
                "url": r["url"],
                "title": r["title"],
                "snippet": r["snippet"],
                "score": r.get("_score", 0.0),
                "summary": r.get("summary"),
                "topic": r.get("topic"),
            }
            for r in unique_results
        ],
    }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)
