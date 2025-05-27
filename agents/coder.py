# agents/coder.py
import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYS_MSG = (
    "You are a senior Python engineer. "
    "Generate production-ready code **only** inside a fenced ```python``` block. "
    "Follow PEP8 and include no extra commentary."
)

def handle_coder(state: dict) -> dict:
    """
    - task / keyword / context / 前回レビュー or テスト失敗の詳細をまとめてプロンプト化
    - GPT-4o でコードを生成し、```python``` ブロックをそのまま code として保存
    """
    # ----------------- 1. 入力準備 -----------------
    # task = state.get("task", state.get("keyword", ""))
    # ★ 生成コードに必須要件をはっきり書く
    task = (
    "Write a production-ready Python function `solve_fizzbuzz(n)` **that returns** "
    "a list of strings following the classic FizzBuzz rules.\n"
    "It must **return**, not print, so that pytest can assert the value."
    )

    context = state.get("context", "")

    # 前回のテスト失敗詳細
    test_details = ""
    if not state.get("test_passed", True):
        test_details = state.get("test_details", "")[:1_000]  # 長過ぎないよう切り詰め

    # 前回レビュー指摘
    review_fb = ""
    if state.get("review", "").startswith("REJECTED"):
        review_fb = state["review"]

    # まとめて 1 つの prompt へ
    prompt_parts = [
        task,
        f"\n\nContext:\n{context}" if context else "",
        f"\n\nPrevious test details:\n{test_details}" if test_details else "",
        f"\n\nPrevious review feedback:\n{review_fb}" if review_fb else "",
    ]
    user_prompt = "".join(prompt_parts).strip()

    # ----------------- 2. LLM 生成 -----------------
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYS_MSG},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
    )

    state["code"] = resp.choices[0].message.content
    return state
