# orchestrator/main.py
import os
import json
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
import uvicorn

from langgraph.graph import StateGraph, END

# --- 自作ノードの import ---
from agents.query_ddg import query_node
from agents.parser import parser_node
from agents.coder import handle_coder
from agents.evaluator import evaluator_node
from agents.reviewer import handle_reviewer
from agents.metric import metric_node
from agents.alert import alert_node
from agents.finops import FinOpsAgent

# ===============================================================
# FastAPI アプリケーション初期化
# ===============================================================
app = FastAPI(
    title="AI-Stack Orchestrator",
    description="AI Agent for automated code generation and testing",
    version="0.9.0"
)

# ===============================================================
# Pydantic モデル定義
# ===============================================================
class TriggerPayload(BaseModel):
    """Trigger endpoint payload validation"""
    task: str = Field(..., min_length=1, max_length=400, description="Task description")
    keyword: str = Field(..., min_length=1, max_length=200, description="Search keyword")
    
    @validator('task')
    def validate_task(cls, v):
        if not v.strip():
            raise ValueError("Task cannot be empty or whitespace only")
        return v.strip()
    
    @validator('keyword')
    def validate_keyword(cls, v):
        if not v.strip():
            raise ValueError("Keyword cannot be empty or whitespace only")
        return v.strip()

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
def create_graph():
    """LangGraph workflow creation"""
    graph = StateGraph(dict)

    # --- ノード登録 ---
    graph.add_node("query", query_node)
    graph.add_node("parser", parser_node)
    graph.add_node("coder", handle_coder)
    graph.add_node("evaluator", evaluator_node)
    graph.add_node("reviewer", handle_reviewer)
    graph.add_node("metric", metric_node)
    graph.add_node("alert", alert_node)

    # --- 直列エッジ ---
    graph.add_edge("query", "parser")
    graph.add_edge("parser", "coder")
    graph.add_edge("coder", "evaluator")
    graph.add_edge("metric", "alert")

    # --- 条件付きエッジ ---
    graph.add_conditional_edges("evaluator", route_from_evaluator)
    graph.add_conditional_edges("reviewer", route_from_reviewer)

    # --- エントリ / 終端 ---
    graph.set_entry_point("query")
    graph.set_finish_point("alert")

    return graph.compile()

# グラフインスタンスの作成
langgraph_app = create_graph()

# ===============================================================
# グローバル状態管理
# ===============================================================
job_status = {
    "current_job": None,
    "last_completed": None,
    "history": []
}

# ===============================================================
# FastAPI エンドポイント
# ===============================================================

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "AI-Stack",
        "version": "0.9.0",
        "endpoints": [
            "/health",
            "/status",
            "/trigger",
            "/cost",
            "/finops/daily-report"
        ]
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "ai-stack"
    }

@app.get("/status")
async def get_status():
    """Get current job status"""
    return {
        "current_job": job_status["current_job"],
        "last_completed": job_status["last_completed"],
        "total_jobs": len(job_status["history"]),
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/trigger")
async def trigger_job(payload: TriggerPayload):
    """Trigger AI agent job with validation"""
    job_id = f"job_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    
    # 現在実行中のジョブがある場合
    if job_status["current_job"]:
        raise HTTPException(
            status_code=409,
            detail="Another job is currently running. Please wait."
        )
    
    try:
        # ジョブステータスを更新
        job_status["current_job"] = {
            "job_id": job_id,
            "task": payload.task,
            "keyword": payload.keyword,
            "started_at": datetime.utcnow().isoformat(),
            "status": "running"
        }
        
        # 非同期でLangGraphワークフローを実行
        asyncio.create_task(run_workflow_async(job_id, payload))
        
        return {
            "status": "triggered",
            "job_id": job_id,
            "task": payload.task,
            "keyword": payload.keyword,
            "message": "Job has been queued for processing"
        }
        
    except Exception as e:
        job_status["current_job"] = None
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/cost")
async def get_cost():
    """Get cost information"""
    finops = FinOpsAgent()
    
    # メトリクスの取得（実際の実装では、保存されたメトリクスから取得）
    metrics = {
        "daily_cost": 0.6,  # プレースホルダー
        "monthly_cost": 18.0,  # プレースホルダー
        "tokens_today": 12000,  # プレースホルダー
        "timestamp": datetime.utcnow().isoformat()
    }
    
    return {
        "metrics": metrics,
        "budget": {
            "daily": finops.daily_budget,
            "monthly": finops.monthly_budget
        }
    }

@app.post("/finops/daily-report")
async def trigger_daily_report():
    """Trigger daily FinOps report"""
    finops = FinOpsAgent()
    
    # 日次レポートを生成
    report = finops.generate_daily_report()
    
    # Slackに送信
    result = finops.send_daily_report(report)
    
    if result.get("success"):
        return {
            "status": "sent",
            "message": "Daily report sent to Slack",
            "report_summary": {
                "date": report.date,
                "total_cost": report.total_cost,
                "openai_cost": report.openai_cost,
                "fly_cost": report.fly_cost,
                "alerts": report.alerts
            }
        }
    else:
        raise HTTPException(status_code=500, detail=result.get("error"))

# ===============================================================
# 非同期ワークフロー実行
# ===============================================================
async def run_workflow_async(job_id: str, payload: TriggerPayload):
    """Run LangGraph workflow asynchronously"""
    try:
        # LangGraphワークフローの実行
        result = await asyncio.to_thread(
            langgraph_app.invoke,
            {
                "job_id": job_id,
                "task": payload.task,
                "keyword": payload.keyword,
                "retries": 0,
                "max_retries": 3,
                "started_at": datetime.utcnow().isoformat()
            }
        )
        
        # 成功時の処理
        job_status["last_completed"] = {
            "job_id": job_id,
            "task": payload.task,
            "completed_at": datetime.utcnow().isoformat(),
            "status": "success",
            "test_passed": result.get("test_passed", False),
            "code_generated": bool(result.get("code"))
        }
        
        # 履歴に追加（最新10件のみ保持）
        job_status["history"].append(job_status["last_completed"])
        if len(job_status["history"]) > 10:
            job_status["history"] = job_status["history"][-10:]
            
    except Exception as e:
        # エラー時の処理
        job_status["last_completed"] = {
            "job_id": job_id,
            "task": payload.task,
            "completed_at": datetime.utcnow().isoformat(),
            "status": "failed",
            "error": str(e)
        }
        
    finally:
        # 現在のジョブをクリア
        job_status["current_job"] = None

# ===============================================================
# エラーハンドラー
# ===============================================================
@app.exception_handler(422)
async def validation_exception_handler(request, exc):
    """Handle validation errors with user-friendly messages"""
    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation Error",
            "detail": exc.errors(),
            "example": {
                "task": "Create a Python function to calculate fibonacci",
                "keyword": "fibonacci algorithm python"
            }
        }
    )

@app.exception_handler(500)
async def internal_error_handler(request, exc):
    """Handle internal server errors"""
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "detail": "An unexpected error occurred. Please try again later.",
            "timestamp": datetime.utcnow().isoformat()
        }
    )

# ===============================================================
# 起動処理
# ===============================================================
@app.on_event("startup")
async def startup_event():
    """Startup tasks"""
    print("AI-Stack Orchestrator starting up...")
    
    # 環境変数チェック
    required_env = ["OPENAI_API_KEY", "SLACK_WEBHOOK_URL"]
    missing = [var for var in required_env if not os.getenv(var)]
    
    if missing:
        print(f"Warning: Missing environment variables: {missing}")
    
    # FinOps予算設定確認
    finops = FinOpsAgent()
    print(f"Daily Budget: ${finops.daily_budget}")
    print(f"Monthly Budget: ${finops.monthly_budget}")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup tasks"""
    print("AI-Stack Orchestrator shutting down...")

# ===============================================================
# メイン実行
# ===============================================================
if __name__ == "__main__":
    # 手動テスト実行（開発用）
    if os.getenv("RUN_TEST", "").lower() == "true":
        result = langgraph_app.invoke({
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
    else:
        # FastAPIサーバー起動
        uvicorn.run(
            "orchestrator.main:app",
            host="0.0.0.0",
            port=int(os.getenv("PORT", 8080)),
            reload=False
        )