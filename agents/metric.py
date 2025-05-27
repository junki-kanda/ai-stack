# agents/metric.py
import time, os

def metric_node(state: dict) -> dict:
    """
    - 直近の pass/fail・リトライ回数・モデル名・推定トークン数を state["metrics"] にまとめる
    - ここでは token を (=len(code)//4) の简易推定で代用
    """
    code_tokens = len(state.get("code", "")) // 4
    retries = state.get("retries", 0)
    passed = state.get("test_passed", None)
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    state["metrics"] = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "pass": passed,
        "retries": retries,
        "tokens": code_tokens,
        "model": model,
    }
    return state
