# agents/parser.py
import re, textwrap

def clean_text(raw: str, *, max_len: int = 8_000) -> str:
    """改行・多重スペースを正規化し長さを丸める。"""
    text = re.sub(r"\s+", " ", raw).strip()
    return textwrap.shorten(text, max_len, placeholder="…")

def parser_node(state: dict) -> dict:
    state["context"] = clean_text(state["article"])
    return state
