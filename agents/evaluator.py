# agents/evaluator.py
import subprocess
import tempfile
import re
import ast
import logging

logger = logging.getLogger(__name__)

def extract_function_name(code: str) -> str:
    """コードから関数名を抽出"""
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                return node.name
    except:
        pass
    
    # 正規表現でのフォールバック
    match = re.search(r'def\s+(\w+)\s*\(', code)
    if match:
        return match.group(1)
    
    return "unknown_function"

def generate_tests(code: str, task: str) -> str:
    """タスクとコードに基づいて動的にテストを生成"""
    func_name = extract_function_name(code)
    
    # タスクからヒントを得る
    task_lower = task.lower()
    
    if "factorial" in task_lower:
        return f"""
import pytest
from candidate import {func_name}

def test_{func_name}_basic():
    assert {func_name}(0) == 1
    assert {func_name}(1) == 1
    assert {func_name}(5) == 120
    assert {func_name}(6) == 720

def test_{func_name}_edge_cases():
    with pytest.raises((ValueError, RecursionError)):
        {func_name}(-1)
"""
    
    elif "fibonacci" in task_lower:
        return f"""
import pytest
from candidate import {func_name}

def test_{func_name}_basic():
    assert {func_name}(1) == [0]
    assert {func_name}(2) == [0, 1]
    assert {func_name}(5) == [0, 1, 1, 2, 3]
    assert {func_name}(10) == [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]

def test_{func_name}_edge_cases():
    with pytest.raises(ValueError):
        {func_name}(0)
    with pytest.raises(ValueError):
        {func_name}(-1)
"""
    
    elif "fizzbuzz" in task_lower:
        return f"""
import pytest
from candidate import {func_name}

def test_{func_name}_basic():
    result = {func_name}(15)
    assert result[2] == "Fizz"  # 3
    assert result[4] == "Buzz"  # 5
    assert result[14] == "FizzBuzz"  # 15

def test_{func_name}_behavior():
    result = {func_name}(15)
    assert len(result) == 15
    assert result[0] == "1"
    assert result[1] == "2"
"""
    
    else:
        # 汎用的なテスト
        return f"""
import pytest
from candidate import {func_name}

def test_{func_name}_exists():
    assert callable({func_name})

def test_{func_name}_basic():
    # 基本的な動作確認
    try:
        result = {func_name}()
        assert result is not None
    except TypeError:
        # 引数が必要な場合
        pass
"""

def evaluator_node(state: dict) -> dict:
    """
    生成されたコードに対してpytestを実行
    """
    code = state.get("code", "")
    task = state.get("task", "")
    
    if not code:
        state["test_passed"] = False
        state["test_details"] = "No code to test"
        return state
    
    # 一時ディレクトリでテストを実行
    with tempfile.TemporaryDirectory() as tmpdir:
        # コードを保存
        code_file = f"{tmpdir}/candidate.py"
        with open(code_file, "w", encoding="utf-8") as f:
            f.write(code)
        
        # 動的にテストを生成
        test_code = generate_tests(code, task)
        test_file = f"{tmpdir}/test_generated.py"
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(test_code)
        
        # pytest実行
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", test_file, "-v"],
                capture_output=True,
                text=True,
                cwd=tmpdir,
                timeout=30
            )
            
            # 結果を解析
            test_passed = result.returncode == 0
            test_details = result.stdout + result.stderr
            
            # 失敗したテストを抽出
            failed_tests = []
            if not test_passed:
                for line in test_details.split('\n'):
                    if 'FAILED' in line:
                        failed_tests.append(line.strip())
            
            state["test_passed"] = test_passed
            state["test_details"] = test_details
            state["test_results"] = {
                "all_passed": test_passed,
                "failed_tests": failed_tests,
                "return_code": result.returncode
            }
            
            logger.info(f"Test result: {'PASSED' if test_passed else 'FAILED'}")
            
        except subprocess.TimeoutExpired:
            state["test_passed"] = False
            state["test_details"] = "Test execution timed out"
            state["test_results"] = {"error": "timeout"}
        except Exception as e:
            state["test_passed"] = False
            state["test_details"] = f"Test execution error: {str(e)}"
            state["test_results"] = {"error": str(e)}
    
    return state