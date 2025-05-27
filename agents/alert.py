# agents/alert.py
import os, json
from slack_sdk.webhook import WebhookClient

WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

def alert_node(state: dict) -> dict:
    """
    - 条件: ① テスト失敗 or ② retries>=3 or ③ token>2k
    - 条件を満たしたら Slack に JSON を投げる
    """
    m = state.get("metrics", {})
    if not m or WEBHOOK_URL is None:
        return state

    alert = (
        (m.get("pass") is False)
        or (m.get("retries", 0) >= 3)
        or (m.get("tokens", 0) > 2_000)
    )
    if alert:
        text = f":rotating_light: *AI-stack Alert* ```{json.dumps(m, indent=2)}```"
        try:
            WebhookClient(WEBHOOK_URL).send(text=text)
        except Exception as e:
            print("Slack send error:", e)
    return state
