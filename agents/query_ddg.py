# agents/query_ddg.py
from duckduckgo_search import DDGS
import requests, bs4, textwrap
import logging

logger = logging.getLogger(__name__)

def query_web(keyword: str, *, max_chars: int = 6_000) -> str:
    """DuckDuckGo で 1 位 URL を取得し本文を返す（超簡易版）。"""
    try:
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
    except Exception as e:
        logger.error(f"query_web error: {e}")
        return f"[Error searching for '{keyword}': {str(e)}]"

def query_node(state: dict) -> dict:
    """LangGraph node for web search"""
    keyword = state.get("keyword", "")
    
    if not keyword:
        state["query"] = state.get("task", "")
        state["search_error"] = "No keyword provided"
        return state
    
    try:
        # Web検索を実行
        result = query_web(keyword)
        
        # 検索結果をstateに追加
        state["search_result"] = result
        state["query"] = f"Context from web search:\n{result}\n\nTask: {state.get('task', '')}"
        
        logger.info(f"Successfully searched for: {keyword}")
        
    except Exception as e:
        logger.error(f"Search error: {str(e)}")
        state["search_error"] = str(e)
        # エラーでも処理を続行
        state["query"] = f"Task: {state.get('task', '')}\n(Search failed: {str(e)})"
    
    return state