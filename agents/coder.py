# agents/coder.py
import os
import re
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYS_MSG = (
    "You are a senior Python engineer. "
    "Generate production-ready code **only** inside a fenced ```python``` block. "
    "Follow PEP8 and include docstrings. "
    "The code should be complete, tested, and ready for production use."
)

def handle_coder(state: dict) -> dict:
    """
    Generate code based on the task and context using OpenAI API
    """
    # ----------------- 1. 入力準備 -----------------
    # タスクを動的に取得（ハードコードしない）
    task = state.get("task", "")
    keyword = state.get("keyword", "")
    
    # タスクが空の場合はキーワードから生成
    if not task:
        task = f"Create a Python implementation for: {keyword}"
    
    # 検索結果やコンテキストを取得
    context = state.get("search_result", state.get("query", ""))
    
    # 前回のテスト失敗詳細
    test_details = ""
    if not state.get("test_passed", True):
        test_details = state.get("test_details", "")[:1000]  # 長すぎないよう切り詰め
    
    # 前回レビュー指摘
    review_fb = ""
    if state.get("review", "").startswith("REJECTED"):
        review_fb = state["review"]
    
    # プロンプトを構築
    prompt_parts = [
        f"Task: {task}",
        f"\nKeyword/Topic: {keyword}" if keyword else "",
        f"\n\nContext from web search:\n{context}" if context else "",
        f"\n\nPrevious test failures:\n{test_details}" if test_details else "",
        f"\n\nPrevious review feedback:\n{review_fb}" if review_fb else "",
        "\n\nRequirements:",
        "- Generate a complete, working Python implementation",
        "- Include proper error handling",
        "- Add docstrings and type hints where appropriate",
        "- Make sure the code is testable and follows best practices",
        "- If the task mentions a specific function name, use that exact name"
    ]
    
    user_prompt = "\n".join(prompt_parts).strip()
    
    # ----------------- 2. LLM 生成 -----------------
    resp = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": SYS_MSG},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,  # 少し創造性を持たせる
    )
    
    generated_content = resp.choices[0].message.content
    
    # ----------------- 3. コード抽出 -----------------
    # ```python``` ブロックからコードを抽出
    code_match = re.search(r'```python\n(.*?)\n```', generated_content, re.DOTALL)
    
    if code_match:
        code = code_match.group(1)
    else:
        # フェンスがない場合は全体をコードとして扱う
        code = generated_content
    
    # コードをstateに保存
    state["code"] = code
    state["generated_content"] = generated_content  # 完全な応答も保存
    
    return state