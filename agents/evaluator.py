# agents/evaluator.py
import re, tempfile, subprocess, sys
from pathlib import Path

# ---------- 1. 生成コードからフェンスを取り除く ----------
def strip_fence(code: str) -> str:
    """
    ```python ... ``` または ``` ... ``` で囲まれていれば中身だけ返す。
    そうでなければそのまま。
    """
    m = re.search(r"```(?:python)?\n(.*?)```", code, re.S | re.I)
    return m.group(1).strip() if m else code.strip()

# ---------- 2. Pytest を実行して pass / fail を返す ----------
TEST_SNIPPET = """
import importlib.util, sys, inspect,pytest

spec = importlib.util.spec_from_file_location("candidate", "{code_path}")
module = importlib.util.module_from_spec(spec)
sys.modules["candidate"] = module
spec.loader.exec_module(module)

def test_signature():
    assert hasattr(module, "solve_fizzbuzz"), "Function solve_fizzbuzz not found"

def test_behavior():
    out = module.solve_fizzbuzz(15)
    exp = [
        "1","2","Fizz","4","Buzz","Fizz","7","8","Fizz","Buzz",
        "11","Fizz","13","14","FizzBuzz"
    ]
    assert out == exp
"""

def run_pytest(code_str: str) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory() as tmp:
        code_path = Path(tmp) / "candidate.py"
        code_path.write_text(code_str, encoding="utf-8")

        test_path = Path(tmp) / "test_generated.py"
        test_path.write_text(TEST_SNIPPET.format(code_path=code_path), encoding="utf-8")

        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", str(test_path)],
            capture_output=True, text=True, timeout=15
        )
        return proc.returncode == 0, proc.stdout + proc.stderr

# ---------- 3. Evaluator ノード ----------
def evaluator_node(state: dict) -> dict:
    try:
        clean_code = strip_fence(state["code"])
        passed, details = run_pytest(clean_code)
    except Exception as e:
        passed, details = False, f"Evaluator Exception: {e}"

    state["test_passed"] = passed
    state["test_details"] = details

    # リトライ管理
    if not passed:
        state["retries"] = state.get("retries", 0) + 1
        if state["retries"] >= 3:
            state["review"] = "FORCE_MERGE"

    return state
