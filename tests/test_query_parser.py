# tests/test_query_parser.py
from agents.query_ddg import query_web
from agents.parser import clean_text

def test_query_parser():
    raw = query_web("python lambda expression", max_chars=2000)
    cleaned = clean_text(raw, max_len=1000)
    assert len(cleaned) <= 1000 and len(cleaned) > 0