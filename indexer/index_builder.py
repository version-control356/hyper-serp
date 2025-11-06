# indexer/index_builder.py
# Lightweight BM25 indexer (no transformers, no faiss)
# Persists BM25 state to disk and stores metadata in SQLite.

import os
import pickle
import sqlite3
import uuid
import json
from typing import List, Dict, Tuple

import numpy as np
from rank_bm25 import BM25Okapi

# -------------------------
# Tokenization utils
# -------------------------
import re
_WORD_RE = re.compile(r"[A-Za-z0-9_]+")
def tokenize(text: str) -> List[str]:
    return _WORD_RE.findall((text or "").lower())

# -------------------------
# Metadata store (SQLite)
# -------------------------
class SimpleMetadataStore:
    def __init__(self, path="metadata.db"):
        self.path = path
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self._ensure()

    def _ensure(self):
        c = self.conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS docs (
                id TEXT PRIMARY KEY,
                url TEXT,
                title TEXT,
                snippet TEXT,
                meta JSON
            )
        """)
        self.conn.commit()

    def add(self, doc_id: str, url: str, title: str, snippet: str, meta: Dict):
        c = self.conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO docs (id,url,title,snippet,meta) VALUES (?,?,?,?,?)",
            (doc_id, url, title, snippet, json.dumps(meta or {}))
        )
        self.conn.commit()

    def get(self, doc_id: str):
        c = self.conn.cursor()
        c.execute("SELECT id,url,title,snippet,meta FROM docs WHERE id = ?", (doc_id,))
        r = c.fetchone()
        if not r:
            return None
        return {"id": r[0], "url": r[1], "title": r[2], "snippet": r[3], "meta": json.loads(r[4] or "{}")}

    def search_by_ids(self, ids: List[str]):
        if not ids:
            return []
        c = self.conn.cursor()
        q = ",".join("?" for _ in ids)
        c.execute(f"SELECT id,url,title,snippet,meta FROM docs WHERE id IN ({q})", ids)
        rows = c.fetchall()
        mp = {r[0]: {"id": r[0], "url": r[1], "title": r[2], "snippet": r[3], "meta": json.loads(r[4] or "{}")} for r in rows}
        return [mp[i] for i in ids if i in mp]  # keep original order

# -------------------------
# BM25 index
# -------------------------
class BM25Index:
    def __init__(self, index_path="bm25.index"):
        self.index_path = index_path
        self.doc_ids: List[str] = []
        self.texts: List[str] = []
        self.tokens: List[List[str]] = []
        self.bm25: BM25Okapi | None = None

        if os.path.exists(self.index_path):
            self._load()

    def _load(self):
        with open(self.index_path, "rb") as f:
            data = pickle.load(f)
        self.doc_ids = data.get("doc_ids", [])
        self.texts = data.get("texts", [])
        self.tokens = data.get("tokens", [])
        if self.tokens:
            self.bm25 = BM25Okapi(self.tokens)

    def _save(self):
        with open(self.index_path, "wb") as f:
            pickle.dump({"doc_ids": self.doc_ids, "texts": self.texts, "tokens": self.tokens}, f)

    def add(self, doc_ids: List[str], texts: List[str]):
        # Append new docs
        new_tokens = [tokenize(t) for t in texts]
        self.doc_ids.extend(doc_ids)
        self.texts.extend(texts)
        self.tokens.extend(new_tokens)
        # Rebuild BM25 (cheap for 1k–5k docs; fine for hackathon)
        self.bm25 = BM25Okapi(self.tokens)
        self._save()

    def query(self, query: str, top_k: int = 5) -> Tuple[List[str], List[float]]:
        if not self.bm25 or not self.doc_ids:
            return [], []
        qtok = tokenize(query)
        scores = self.bm25.get_scores(qtok)
        # argsort descending
        order = np.argsort(scores)[::-1][:top_k]
        ids = [self.doc_ids[i] for i in order]
        sc = [float(scores[i]) for i in order]
        return ids, sc

# -------------------------
# Public Builder API (keeps your old signatures)
# -------------------------
class Builder:
    def __init__(self, index_path="bm25.index", meta_db="metadata.db"):
        self.indexer = BM25Index(index_path=index_path)
        self.meta = SimpleMetadataStore(meta_db)

    def ingest_docs(self, docs: List[Dict]):
        """
        docs: list of {url, title, snippet, text}
        """
        texts = []
        ids = []
        metas = []
        for d in docs:
            doc_id = d.get("id") or str(uuid.uuid4())
            ids.append(doc_id)
            # light concat for ranking context (no more than ~10k chars)
            t = (d.get("title","") + "\n" + d.get("snippet","") + "\n" + (d.get("text","")[:10000]))
            texts.append(t)
            metas.append((doc_id, d.get("url",""), d.get("title",""), d.get("snippet",""), {"length": len(d.get("text",""))}))
        # update BM25
        self.indexer.add(ids, texts)
        # store metadata
        for m in metas:
            self.meta.add(m[0], m[1], m[2], m[3], m[4])
        return ids

    def search(self, query: str, top_k=5):
        ids, scores = self.indexer.query(query, top_k=top_k)
        docs = self.meta.search_by_ids(ids) if ids else []
        for i, d in enumerate(docs):
            d["_score"] = scores[i]
        return docs

if __name__ == "__main__":
    b = Builder()
    ids = b.ingest_docs([
        {"url":"https://example.com/1","title":"Hello World","snippet":"demo","text":"This is a demo document about BM25 search."},
        {"url":"https://example.com/2","title":"Python Tips","snippet":"tips","text":"Python programming tips and tricks for developers."}
    ])
    print("ingested", ids)
    print(b.search("python developers", top_k=2))
