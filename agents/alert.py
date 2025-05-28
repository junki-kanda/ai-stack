# agents/alert.py
import json
import os
import requests
from typing import Dict, Any

def alert_slack(message: Dict[str, Any]) -> Dict[str, Any]:
    """Send alert to Slack with formatted message for both success and failure"""
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    
    if not webhook_url:
        return {"error": "SLACK_WEBHOOK_URL not set"}
    
    # 成功時の通知
    if message.get("pass") is True and message.get("retries", 0) == 0:
        icon = ":white_check_mark:"
        color = "good"
        title = "AI-Stack Job Success"
        text = f"{icon} Job completed successfully\n```{json.dumps(message, indent=2)}```"
    # リトライ後の成功
    elif message.get("pass") is True and message.get("retries", 0) > 0:
        icon = ":warning:"
        color = "warning"
        title = "AI-Stack Job Success (with retries)"
        text = f"{icon} Job succeeded after {message['retries']} retries\n```{json.dumps(message, indent=2)}```"
    # 失敗時の通知
    else:
        icon = ":x:"
        color = "danger"
        title = "AI-Stack Job Failed"
        text = f"{icon} Job failed after {message.get('retries', 0)} retries\n```{json.dumps(message, indent=2)}```"
    
    # Slack Block Kit形式でリッチなメッセージ
    slack_message = {
        "attachments": [{
            "color": color,
            "title": title,
            "text": text,
            "footer": "AI-Stack",
            "ts": int(os.environ.get('CURRENT_TIME', 0))
        }]
    }
    
    try:
        response = requests.post(webhook_url, json=slack_message)
        response.raise_for_status()
        return {"success": True, "status_code": response.status_code}
    except Exception as e:
        return {"error": str(e)}

def alert_node(state: dict) -> dict:
    """LangGraph node wrapper for alert_slack"""
    # Extract relevant information from state
    message = {
        "task": state.get("task", "Unknown task"),
        "pass": state.get("test_passed", False),
        "retries": state.get("retries", 0),
        "code": state.get("code", ""),
        "test_results": state.get("test_results", {}),
        "review": state.get("review", ""),
        "metrics": state.get("metrics", {}),
        "job_id": state.get("job_id", "unknown")
    }
    
    # Send alert
    result = alert_slack(message)
    
    # Update state with alert result
    state["alert_sent"] = result.get("success", False)
    state["alert_result"] = result
    
    return state