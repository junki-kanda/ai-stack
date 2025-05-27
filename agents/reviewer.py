# agents/reviewer.py
import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYS_MSG = (
    "You are a strict senior code reviewer. "
    "If the code is acceptable, reply exactly 'APPROVED'. "
    "Otherwise reply 'REJECTED: <reason>' (one short sentence)."
)


def handle_reviewer(state: dict) -> dict:
    """
    - テストが通っていない場合は即 REJECTED を返す（想定外フローの保険）
    - そうでなければ LLM でコードレビューを実施
    - REJECTED なら retries をインクリメント。3 回目で強制マージ
    """
    # ----------------- 1. テスト結果チェック -----------------
    if not state.get("test_passed", False):
        state["review"] = "REJECTED: test_failed"
        state["retries"] = state.get("retries", 0) + 1
        if state["retries"] >= 3:
            state["review"] = "FORCE_MERGE"
        return state

    # ----------------- 2. LLM レビュー -----------------
    code = state["code"]
    prompt = f"Please review the following code:\n```python\n{code}\n```"

    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYS_MSG},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
    )
    review_result = res.choices[0].message.content.strip()

    state["review"] = review_result

    # ----------------- 3. リトライ管理 -----------------
    if review_result.startswith("REJECTED"):
        state["retries"] = state.get("retries", 0) + 1
        if state["retries"] >= 3:
            state["review"] = "FORCE_MERGE"
    else:
        state.pop("retries", None)  # pass ならカウンタをリセット

    return state
