# tests/test_query_parser.py
import sys
import os
# プロジェクトルートをPythonパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from agents.parser import parse_query

def test_parse_query_basic():
    """Test basic query parsing"""
    result = parse_query({
        "task": "Create a function to calculate fibonacci",
        "keyword": "fibonacci python"
    })
    
    assert "parsed_task" in result
    assert "search_terms" in result
    assert result["parsed_task"] == "Create a function to calculate fibonacci"
    assert "fibonacci" in result["search_terms"]
    assert "python" in result["search_terms"]

def test_parse_query_empty():
    """Test parsing with empty values"""
    with pytest.raises(ValueError):
        parse_query({
            "task": "",
            "keyword": ""
        })

def test_parse_query_special_characters():
    """Test parsing with special characters"""
    result = parse_query({
        "task": "Create API endpoint for /users/:id",
        "keyword": "REST API @decorator"
    })
    
    assert result is not None
    assert "parsed_task" in result

if __name__ == "__main__":
    pytest.main([__file__])