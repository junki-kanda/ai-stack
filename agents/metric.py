# agents/metric.py
import time
import os
import logging
from agents.finops import track_agent_costs, FinOpsAgent

logger = logging.getLogger(__name__)

def metric_node(state: dict) -> dict:
    """
    メトリクスの計算とコスト追跡を行う
    - 直近の pass/fail・リトライ回数・モデル名・推定トークン数を state["metrics"] にまとめる
    - FinOpsAgentでコストを追跡
    - 実行時間の計測も追加
    """
    # 実行時間の計算（state に start_time があれば使用）
    start_time = state.get("start_time", time.time())
    execution_time = time.time() - start_time
    
    # トークン数の推定（より正確な推定）
    # コード生成の場合、入力プロンプト + 出力コードを考慮
    query_tokens = len(state.get("query", "")) // 4
    code_tokens = len(state.get("code", "")) // 4
    
    # 各エージェントでの推定トークン使用量
    # Parser: クエリ解析（短い）
    parser_tokens = query_tokens + 100  # プロンプト含む
    
    # Coder: コード生成（最も多い）
    coder_input_tokens = query_tokens + 500  # システムプロンプト含む
    coder_output_tokens = code_tokens
    
    # Evaluator: テスト実行（LLMは使わないが、ログ生成）
    evaluator_tokens = 0  # pytestのみ
    
    # Reviewer: コードレビュー
    reviewer_tokens = code_tokens + 300  # レビューコメント含む
    
    # 合計トークン数
    total_input_tokens = parser_tokens + coder_input_tokens + reviewer_tokens
    total_output_tokens = coder_output_tokens + 200  # レビューコメント等
    total_tokens = total_input_tokens + total_output_tokens
    
    # メトリクスの収集
    retries = state.get("retries", 0)
    passed = state.get("test_passed", None)
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    
    # メトリクス辞書の作成
    state["metrics"] = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "pass": passed,
        "retries": retries,
        "tokens": total_tokens,
        "model": model,
        "execution_time": execution_time,
        "breakdown": {
            "parser_tokens": parser_tokens,
            "coder_tokens": coder_input_tokens + coder_output_tokens,
            "reviewer_tokens": reviewer_tokens,
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens
        }
    }
    
    # FinOpsエージェントでコストを追跡
    try:
        # OpenAIコストの追跡
        finops = FinOpsAgent()
        
        # 各エージェントのコストを個別に追跡
        # Parser
        finops.track_openai_usage(
            model=model,
            input_tokens=parser_tokens,
            output_tokens=50,  # パース結果
            metadata={"agent": "parser", "query": state.get("query", "")}
        )
        
        # Coder
        finops.track_openai_usage(
            model=model,
            input_tokens=coder_input_tokens,
            output_tokens=coder_output_tokens,
            metadata={
                "agent": "coder",
                "retries": retries,
                "test_passed": passed
            }
        )
        
        # Reviewer
        if retries > 0 or not passed:
            finops.track_openai_usage(
                model=model,
                input_tokens=code_tokens + 200,
                output_tokens=100,
                metadata={
                    "agent": "reviewer",
                    "review_reason": "retry" if retries > 0 else "failure"
                }
            )
        
        # Fly.ioの使用時間を追跡（バッチ全体の実行時間）
        finops.track_fly_usage(
            machine_type="shared-cpu-1x",
            duration_seconds=execution_time,
            memory_gb=0.512
        )
        
        # コスト情報をメトリクスに追加
        today_report = finops.generate_daily_report()
        state["metrics"]["cost_summary"] = {
            "total_cost_today": today_report.total_cost,
            "openai_cost_today": today_report.openai_cost,
            "fly_cost_today": today_report.fly_cost,
            "budget_remaining": finops.daily_budget - today_report.total_cost
        }
        
        # 予算超過の場合は警告
        if today_report.total_cost > finops.daily_budget * 0.8:
            logger.warning(f"Daily budget warning: ${today_report.total_cost:.2f} of ${finops.daily_budget:.2f}")
            state["metrics"]["budget_alert"] = True
        
    except Exception as e:
        # FinOpsエラーがあってもメトリクス処理は継続
        logger.error(f"FinOps tracking error: {e}")
        state["metrics"]["finops_error"] = str(e)
    
    # デバッグ用ログ
    logger.info(f"Metrics collected: {state['metrics']}")
    
    return state

def get_cost_summary() -> dict:
    """
    現在のコストサマリーを取得する（APIエンドポイント用）
    """
    try:
        finops = FinOpsAgent()
        report = finops.generate_daily_report()
        
        return {
            "date": report.date,
            "total_cost": report.total_cost,
            "openai_cost": report.openai_cost,
            "fly_cost": report.fly_cost,
            "daily_budget": finops.daily_budget,
            "monthly_budget": finops.monthly_budget,
            "alerts": report.alerts,
            "recommendations": report.recommendations
        }
    except Exception as e:
        logger.error(f"Failed to get cost summary: {e}")
        return {"error": str(e)}