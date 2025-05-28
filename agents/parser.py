# agents/parser.py
import re, textwrap
import json
from typing import Dict, Any, List

def parse_query(query_data: Dict[str, Any]) -> Dict[str, Any]:
    """Parse user query and extract task information"""
    task = query_data.get("task", "")
    keyword = query_data.get("keyword", "")
    
    if not task or not keyword:
        raise ValueError("Both task and keyword are required")
    
    # Extract search terms from keyword
    search_terms = keyword.strip().split()
    
    return {
        "parsed_task": task.strip(),
        "search_terms": search_terms,
        "original_keyword": keyword
    }

def parser_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph node for parsing user input"""
    try:
        # Parse the query
        parsed_result = parse_query({
            "task": state.get("task", ""),
            "keyword": state.get("keyword", "")
        })
        
        # Update state with parsed information
        state.update(parsed_result)
        state["parsing_success"] = True
        
    except Exception as e:
        state["parsing_success"] = False
        state["parsing_error"] = str(e)
    
    return state

def clean_text(raw: str, *, max_len: int = 8_000) -> str:
    """改行・多重スペースを正規化し長さを丸める。"""
    text = re.sub(r"\s+", " ", raw).strip()
    return textwrap.shorten(text, max_len, placeholder="…")
