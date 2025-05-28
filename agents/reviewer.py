# agents/reviewer.py
import os
import json
from typing import Dict, Any, List
from openai import OpenAI
import requests

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
    - 最大リトライ回数に達した場合、PRにラベルを付与してSlack通知
    """
    # ----------------- 1. テスト結果チェック -----------------
    if not state.get("test_passed", False):
        state["review"] = "REJECTED: test_failed"
        state["retries"] = state.get("retries", 0) + 1
        
        if state["retries"] >= 3:
            # 最大リトライ回数に達した場合の処理
            state["review"] = "FORCE_MERGE"
            _handle_max_retries_reached(state)
        
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
            # 最大リトライ回数に達した場合
            state["review"] = "FORCE_MERGE"
            _handle_max_retries_reached(state)
    else:
        # APPROVED の場合
        state.pop("retries", None)  # pass ならカウンタをリセット
        state["pr_labels"] = ["ready-to-merge", "ai-approved"]
        state["merge_allowed"] = True

    return state


def _handle_max_retries_reached(state: Dict[str, Any]) -> None:
    """
    最大リトライ回数に達した場合の処理
    - PRにラベルを付与
    - Slack通知を送信
    """
    # PRラベルの設定
    state["pr_labels"] = ["do-not-merge", "needs-manual-review", "max-retries-exceeded"]
    state["merge_allowed"] = False
    
    # 失敗の詳細情報を追加
    state["review_details"] = {
        "status": "force_merge_blocked",
        "reason": "Maximum retries exceeded with failing tests or review",
        "retries": state.get("retries", 0),
        "test_passed": state.get("test_passed", False),
        "test_details": state.get("test_details", "No test details available"),
        "code_snippet": state.get("code", "")[:500] + "..." if len(state.get("code", "")) > 500 else state.get("code", "")
    }
    
    # Slack通知を送信
    _send_failure_notification(state)


def _send_failure_notification(state: Dict[str, Any]) -> None:
    """
    失敗時のSlack通知を送信
    """
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        print("Warning: SLACK_WEBHOOK_URL not set, skipping notification")
        return
    
    # Slack Block Kit形式のリッチなメッセージ
    slack_message = {
        "text": "🚨 AI-Stack Review Failed - Manual intervention required",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🚨 Code Review Failed - PR Blocked"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "<!channel> The AI-Stack agent failed to produce acceptable code after maximum retries."
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Task:*\n{state.get('task', 'Unknown')}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Job ID:*\n{state.get('job_id', 'Unknown')}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Retries:*\n{state.get('retries', 0)}/3"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Test Status:*\n{'✅ Passed' if state.get('test_passed') else '❌ Failed'}"
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Review Result:*\n```{state.get('review', 'No review result')}```"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*🏷️ PR Labels Applied:*\n• `do-not-merge`\n• `needs-manual-review`\n• `max-retries-exceeded`"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "View PR"
                        },
                        "url": state.get("pr_url", "https://github.com/junki-kanda/ai-stack"),
                        "style": "primary"
                    }
                ]
            }
        ],
        "attachments": [
            {
                "color": "danger",
                "footer": "AI-Stack Reviewer",
                "ts": int(os.environ.get('CURRENT_TIME', 0))
            }
        ]
    }
    
    try:
        response = requests.post(webhook_url, json=slack_message)
        response.raise_for_status()
        print(f"Slack notification sent: {response.status_code}")
    except Exception as e:
        print(f"Failed to send Slack notification: {str(e)}")


def apply_github_labels(pr_url: str, labels: List[str], github_token: str = None) -> bool:
    """
    GitHub PRにラベルを適用する
    
    Args:
        pr_url: PR のURL (例: https://github.com/owner/repo/pull/123)
        labels: 適用するラベルのリスト
        github_token: GitHub APIトークン
    
    Returns:
        bool: 成功した場合True
    """
    if not github_token:
        github_token = os.getenv("GITHUB_TOKEN")
    
    if not github_token:
        print("Warning: GITHUB_TOKEN not set, cannot apply PR labels")
        return False
    
    # PR URLからowner, repo, pr_numberを抽出
    try:
        parts = pr_url.split("/")
        owner = parts[3]
        repo = parts[4]
        pr_number = parts[6]
    except (IndexError, ValueError):
        print(f"Invalid PR URL format: {pr_url}")
        return False
    
    # GitHub API エンドポイント
    api_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/labels"
    
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    try:
        response = requests.post(api_url, json=labels, headers=headers)
        response.raise_for_status()
        print(f"Successfully applied labels {labels} to PR {pr_url}")
        return True
    except Exception as e:
        print(f"Failed to apply labels to PR: {str(e)}")
        return False


# オプション: PRラベルを実際に適用する場合は、handle_reviewer内で以下を呼び出す
# if state.get("pr_url") and state.get("pr_labels"):
#     apply_github_labels(state["pr_url"], state["pr_labels"])