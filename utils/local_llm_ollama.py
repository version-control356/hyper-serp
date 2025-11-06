# utils/local_llm_ollama.py
import requests, textwrap

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
MODEL = "tinyllama"  # or "phi3:mini"

def _gen(prompt: str, max_tokens: int = 200, temperature: float = 0.3, timeout: int = 60) -> str:
    try:
        r = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens},
            },
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
        return (data.get("response") or "").strip()
    except Exception:
        return ""

def summarize_text(text: str, max_tokens: int = 180) -> str:
    if not text: return ""
    prompt = textwrap.dedent(f"""
    You are a concise summarizer.
    Summarize the content below in 3-5 bullets.

    CONTENT:
    {text[:2000]}

    BULLETS:
    - 
    """)
    return _gen(prompt, max_tokens=max_tokens, temperature=0.3).strip()

def classify_topic(text: str) -> str:
    if not text: return "misc"
    prompt = textwrap.dedent(f"""
    Classify the snippet into one topic:
    Choices: music, biography, tech, business, politics, film, sports, education, news, social, misc.

    SNIPPET:
    {text[:500]}

    Only output the single topic:
    """)
    out = _gen(prompt, max_tokens=8, temperature=0.0).lower().strip()
    for c in ["music","biography","tech","business","politics","film","sports","education","news","social","misc"]:
        if c in out:
            return c
    return "misc"

def expand_query(q: str) -> list[str]:
    prompt = f'Give 3 short alternative queries for: "{q}". One per line.'
    out = _gen(prompt, max_tokens=60, temperature=0.7)
    return [l.strip("- ").strip() for l in (out or "").splitlines() if l.strip()][:3]
