# orchestrator/main.py
from langgraph.graph import StateGraph, END   # END = グラフを終了させる特別値

# --- 自作ノードの import ---
from agents.query_ddg import query_node
from agents.parser    import parser_node
from agents.coder     import handle_coder
from agents.evaluator import evaluator_node
from agents.reviewer  import handle_reviewer
from agents.metric    import metric_node
from agents.alert     import alert_node

# ===============================================================
# 1. 条件分岐ロジック
# ===============================================================

def route_from_evaluator(state: dict) -> str:
    """テスト結果に応じて遷移先を返す"""
    if not state.get("test_passed", False):
        # テスト失敗
        return "coder" if state.get("retries", 0) < 3 else "reviewer"
    # テスト合格
    return "reviewer"

def route_from_reviewer(state: dict) -> str:
    """REJECTED なら coder へ、APPROVED/FORCE_MERGE なら metric へ"""
    return "coder" if state.get("review", "").startswith("REJECTED") else "metric"

# ===============================================================
# 2. グラフ定義
# ===============================================================

graph = StateGraph(dict)

# --- ノード登録 ---
graph.add_node("query",     query_node)
graph.add_node("parser",    parser_node)
graph.add_node("coder",     handle_coder)
graph.add_node("evaluator", evaluator_node)
graph.add_node("reviewer",  handle_reviewer)
graph.add_node("metric",    metric_node)
graph.add_node("alert",     alert_node)

# --- 直列エッジ ---
graph.add_edge("query",  "parser")
graph.add_edge("parser", "coder")
graph.add_edge("coder",  "evaluator")
graph.add_edge("metric", "alert")        # metric → alert は固定

# --- 条件付きエッジ ---
graph.add_conditional_edges("evaluator", route_from_evaluator)
graph.add_conditional_edges("reviewer",  route_from_reviewer)

# --- エントリ / 終端 ---
graph.set_entry_point("query")
graph.set_finish_point("alert")          # alert で必ず終わる

app = graph.compile()

# ===============================================================
# 3. 手動テスト実行
# ===============================================================
if __name__ == "__main__":
    result = app.invoke({
        "keyword": "fizz buzz problem python",
        "task": (
            "Read the context and write a Python function solve_fizzbuzz(n) "
            "that prints FizzBuzz rules."
        ),
    })

    print("--- CODE ---\n", result.get("code", "<no code>"))
    print("--- TEST PASSED ---", result.get("test_passed"))
    print("--- REVIEW ---\n", result.get("review", "<no review>"))
    print("--- TEST DETAILS ---\n", result.get("test_details", "")[:500])
    print("--- METRICS ---\n", result.get("metrics", {}))
