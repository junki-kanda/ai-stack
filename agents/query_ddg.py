# agents/query_ddg.py
from duckduckgo_search import DDGS
import requests, bs4, textwrap

def query_web(keyword: str, *, max_chars: int = 6_000) -> str:
    """DuckDuckGo で 1 位 URL を取得し本文を返す（超簡易版）。"""
    with DDGS() as ddgs:
        hits = list(ddgs.text(keyword, max_results=1))
    if not hits:
        return f"[No result for '{keyword}']"
    url = hits[0]["href"]

    # HTML 取得 → パース
    html = requests.get(url, timeout=10).text
    soup = bs4.BeautifulSoup(html, "lxml")
    # script/style 等を除去
    for bad in soup(["script", "style", "noscript"]):
        bad.decompose()
    text = " ".join(soup.get_text(" ", strip=True).split())
    return textwrap.shorten(text, max_chars, placeholder="…")

def query_node(state: dict) -> dict:
    text = query_web(state["keyword"])
    state["article"] = text            # ← 既存 state を直接更新
    return state                       #    so task, keyword が残る
