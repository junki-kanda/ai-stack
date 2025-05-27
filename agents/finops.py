#!/usr/bin/env python3
"""
FinOps Agent for AI-Stack
Tracks OpenAI usage, calculates costs, and generates daily reports
"""
import os
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import requests

logger = logging.getLogger(__name__)

# OpenAI Pricing (as of 2025)
OPENAI_PRICING = {
    "gpt-4o": {
        "input": 0.0025,   # per 1K tokens
        "output": 0.01     # per 1K tokens
    },
    "gpt-4o-mini": {
        "input": 0.00015,
        "output": 0.0006
    },
    "gpt-4-turbo": {
        "input": 0.01,
        "output": 0.03
    },
    "gpt-3.5-turbo": {
        "input": 0.0005,
        "output": 0.0015
    }
}

# Fly.io Pricing
FLY_PRICING = {
    "shared-cpu-1x": {
        "per_second": 0.0000022,  # ~$5.70/month for 24/7
        "memory_gb": 0.00000126   # per GB per second
    }
}

@dataclass
class UsageRecord:
    """Single usage record for cost tracking"""
    timestamp: str
    service: str  # 'openai' or 'fly'
    resource: str  # model name or machine type
    quantity: float  # tokens or seconds
    unit: str  # 'tokens' or 'seconds'
    cost: float  # calculated cost in USD
    metadata: Dict[str, Any]

@dataclass
class CostReport:
    """Daily cost report"""
    date: str
    total_cost: float
    openai_cost: float
    fly_cost: float
    usage_details: List[UsageRecord]
    alerts: List[str]
    recommendations: List[str]

class FinOpsAgent:
    """Financial Operations Agent for cost tracking and optimization"""
    
    def __init__(self, storage_path: str = "/app/data/finops"):
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)
        self.current_day_file = os.path.join(storage_path, "current_day.json")
        self.history_path = os.path.join(storage_path, "history")
        os.makedirs(self.history_path, exist_ok=True)
        
        # Budget settings
        self.daily_budget = float(os.getenv('DAILY_BUDGET', '10.0'))  # $10/day default
        self.monthly_budget = float(os.getenv('MONTHLY_BUDGET', '300.0'))  # $300/month
        
    def track_openai_usage(self, model: str, input_tokens: int, output_tokens: int, 
                          metadata: Optional[Dict] = None) -> UsageRecord:
        """Track OpenAI API usage"""
        if model not in OPENAI_PRICING:
            logger.warning(f"Unknown model {model}, using gpt-4o pricing")
            model = "gpt-4o"
        
        pricing = OPENAI_PRICING[model]
        input_cost = (input_tokens / 1000) * pricing["input"]
        output_cost = (output_tokens / 1000) * pricing["output"]
        total_cost = input_cost + output_cost
        
        record = UsageRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            service="openai",
            resource=model,
            quantity=input_tokens + output_tokens,
            unit="tokens",
            cost=total_cost,
            metadata={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "input_cost": input_cost,
                "output_cost": output_cost,
                **(metadata or {})
            }
        )
        
        self._save_usage_record(record)
        return record
    
    def track_fly_usage(self, machine_type: str, duration_seconds: float,
                       memory_gb: float = 0.512) -> UsageRecord:
        """Track Fly.io machine usage"""
        if machine_type not in FLY_PRICING:
            machine_type = "shared-cpu-1x"
        
        pricing = FLY_PRICING[machine_type]
        cpu_cost = duration_seconds * pricing["per_second"]
        memory_cost = duration_seconds * memory_gb * pricing["memory_gb"]
        total_cost = cpu_cost + memory_cost
        
        record = UsageRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            service="fly",
            resource=machine_type,
            quantity=duration_seconds,
            unit="seconds",
            cost=total_cost,
            metadata={
                "memory_gb": memory_gb,
                "cpu_cost": cpu_cost,
                "memory_cost": memory_cost,
                "duration_minutes": duration_seconds / 60
            }
        )
        
        self._save_usage_record(record)
        return record
    
    def generate_daily_report(self, date: Optional[str] = None) -> CostReport:
        """Generate cost report for a specific day"""
        if not date:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        # Load usage records for the day
        records = self._load_usage_records(date)
        
        # Calculate totals
        openai_cost = sum(r.cost for r in records if r.service == "openai")
        fly_cost = sum(r.cost for r in records if r.service == "fly")
        total_cost = openai_cost + fly_cost
        
        # Generate alerts
        alerts = []
        if total_cost > self.daily_budget:
            alerts.append(f"⚠️ Daily budget exceeded: ${total_cost:.2f} > ${self.daily_budget}")
        
        if total_cost > self.daily_budget * 0.8:
            alerts.append(f"⚠️ Approaching daily budget: ${total_cost:.2f} (80% of ${self.daily_budget})")
        
        # Monthly projection
        days_in_month = 30
        projected_monthly = total_cost * days_in_month
        if projected_monthly > self.monthly_budget:
            alerts.append(f"⚠️ Projected monthly cost ${projected_monthly:.2f} exceeds budget ${self.monthly_budget}")
        
        # Generate recommendations
        recommendations = self._generate_recommendations(records)
        
        report = CostReport(
            date=date,
            total_cost=total_cost,
            openai_cost=openai_cost,
            fly_cost=fly_cost,
            usage_details=records,
            alerts=alerts,
            recommendations=recommendations
        )
        
        # Save report
        self._save_report(report)
        
        return report
    
    def _generate_recommendations(self, records: List[UsageRecord]) -> List[str]:
        """Generate cost optimization recommendations"""
        recommendations = []
        
        # Analyze OpenAI usage
        openai_records = [r for r in records if r.service == "openai"]
        if openai_records:
            avg_tokens = sum(r.quantity for r in openai_records) / len(openai_records)
            if avg_tokens > 2000:
                recommendations.append("Consider using gpt-4o-mini for simpler tasks to reduce costs")
            
            # Check if using expensive models
            expensive_usage = sum(r.cost for r in openai_records if r.resource in ["gpt-4o", "gpt-4-turbo"])
            if expensive_usage > sum(r.cost for r in openai_records) * 0.8:
                recommendations.append("80%+ of costs from expensive models. Evaluate if gpt-3.5-turbo suffices")
        
        # Analyze Fly usage
        fly_records = [r for r in records if r.service == "fly"]
        if fly_records:
            total_runtime = sum(r.quantity for r in fly_records)
            if total_runtime > 3600:  # More than 1 hour per day
                recommendations.append(f"Fly.io ran for {total_runtime/60:.1f} minutes. Consider optimizing batch duration")
        
        if not recommendations:
            recommendations.append("✅ Usage patterns look optimal")
        
        return recommendations
    
    def _save_usage_record(self, record: UsageRecord):
        """Save usage record to current day file"""
        try:
            if os.path.exists(self.current_day_file):
                with open(self.current_day_file, 'r') as f:
                    data = json.load(f)
            else:
                data = {"date": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "records": []}
            
            data["records"].append(asdict(record))
            
            with open(self.current_day_file, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save usage record: {e}")
    
    def _load_usage_records(self, date: str) -> List[UsageRecord]:
        """Load usage records for a specific date"""
        records = []
        
        # Check current day file
        if os.path.exists(self.current_day_file):
            with open(self.current_day_file, 'r') as f:
                data = json.load(f)
                if data.get("date") == date:
                    records.extend([UsageRecord(**r) for r in data.get("records", [])])
        
        # Check history
        history_file = os.path.join(self.history_path, f"{date}.json")
        if os.path.exists(history_file):
            with open(history_file, 'r') as f:
                data = json.load(f)
                records.extend([UsageRecord(**r) for r in data.get("records", [])])
        
        return records
    
    def _save_report(self, report: CostReport):
        """Save daily report"""
        report_file = os.path.join(self.history_path, f"report_{report.date}.json")
        with open(report_file, 'w') as f:
            json.dump(asdict(report), f, indent=2)
    
    def send_cost_alert(self, report: CostReport):
        """Send cost report to Slack"""
        webhook_url = os.getenv('SLACK_WEBHOOK_URL')
        if not webhook_url:
            logger.warning("No Slack webhook configured for cost alerts")
            return
        
        # Format message
        emoji = "💰" if report.total_cost <= self.daily_budget else "🚨"
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} Daily Cost Report - {report.date}"
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Total Cost:*\n${report.total_cost:.2f}"},
                    {"type": "mrkdwn", "text": f"*Budget:*\n${self.daily_budget:.2f}/day"},
                    {"type": "mrkdwn", "text": f"*OpenAI:*\n${report.openai_cost:.2f}"},
                    {"type": "mrkdwn", "text": f"*Fly.io:*\n${report.fly_cost:.2f}"}
                ]
            }
        ]
        
        # Add alerts if any
        if report.alerts:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Alerts:*\n" + "\n".join(report.alerts)
                }
            })
        
        # Add recommendations
        if report.recommendations:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Recommendations:*\n• " + "\n• ".join(report.recommendations)
                }
            })
        
        # Send to Slack
        try:
            response = requests.post(webhook_url, json={"blocks": blocks})
            response.raise_for_status()
            logger.info("Cost report sent to Slack")
        except Exception as e:
            logger.error(f"Failed to send cost report to Slack: {e}")

# Integration with existing agents
def track_agent_costs(agent_name: str, model: str, estimated_tokens: int):
    """Helper function to track costs from other agents"""
    finops = FinOpsAgent()
    
    # Estimate input/output split (typically 30/70 for generation tasks)
    input_tokens = int(estimated_tokens * 0.3)
    output_tokens = int(estimated_tokens * 0.7)
    
    return finops.track_openai_usage(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        metadata={"agent": agent_name}
    )

# Daily report generation (to be called by scheduler)
def generate_and_send_daily_report():
    """Generate and send daily cost report"""
    finops = FinOpsAgent()
    report = finops.generate_daily_report()
    finops.send_cost_alert(report)
    
    return report

if __name__ == "__main__":
    # Test the FinOps agent
    agent = FinOpsAgent()
    
    # Track some sample usage
    agent.track_openai_usage("gpt-4o", 1000, 2000, {"task": "code_generation"})
    agent.track_fly_usage("shared-cpu-1x", 300, 0.512)  # 5 minutes
    
    # Generate report
    report = agent.generate_daily_report()
    print(json.dumps(asdict(report), indent=2))
    
    # Send alert
    agent.send_cost_alert(report)