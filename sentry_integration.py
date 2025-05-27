#!/usr/bin/env python3
"""
Sentry integration for AI-Stack error tracking
"""
import os
import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration
from typing import Dict, Any, Optional
from functools import wraps
import logging

# Configuration
SENTRY_DSN = os.getenv('SENTRY_DSN')
ENVIRONMENT = os.getenv('FLY_APP_NAME', 'development')
RELEASE = os.getenv('FLY_IMAGE_REF', 'unknown')

def initialize_sentry():
    """Initialize Sentry SDK with AI-Stack specific configuration"""
    if not SENTRY_DSN:
        logging.warning("SENTRY_DSN not set, error tracking disabled")
        return False
    
    sentry_logging = LoggingIntegration(
        level=logging.INFO,        # Capture info and above as breadcrumbs
        event_level=logging.ERROR  # Send errors as events
    )
    
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[sentry_logging],
        
        # Performance monitoring
        traces_sample_rate=0.1,  # 10% of transactions
        profiles_sample_rate=0.1,  # 10% of sampled transactions
        
        # Release tracking
        release=RELEASE,
        environment=ENVIRONMENT,
        
        # Additional options
        attach_stacktrace=True,
        send_default_pii=False,  # Don't send personally identifiable information
        
        # Custom tags
        before_send=before_send_filter
    )
    
    # Set user context
    sentry_sdk.set_tag("app", "ai-stack")
    sentry_sdk.set_tag("region", os.getenv('FLY_REGION', 'unknown'))
    
    return True

def before_send_filter(event, hint):
    """Filter sensitive data before sending to Sentry"""
    # Remove API keys from event data
    if 'extra' in event:
        for key in list(event['extra'].keys()):
            if 'api_key' in key.lower() or 'token' in key.lower():
                event['extra'][key] = '[REDACTED]'
    
    # Filter out health check noise
    if 'logger' in event and event['logger'] == 'aiohttp.access':
        if '/health' in str(event.get('message', '')):
            return None  # Don't send health checks to Sentry
    
    return event

def track_agent_error(agent_name: str):
    """Decorator to track errors in specific agents"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            with sentry_sdk.push_scope() as scope:
                scope.set_tag("agent", agent_name)
                scope.set_context("agent_context", {
                    "name": agent_name,
                    "function": func.__name__,
                    "args_count": len(args),
                    "kwargs": list(kwargs.keys())
                })
                
                try:
                    result = func(*args, **kwargs)
                    
                    # Track successful execution metrics
                    if agent_name == "evaluator" and result.get('test_passed'):
                        sentry_sdk.set_measurement("tests_passed", 1)
                    
                    return result
                    
                except Exception as e:
                    # Add agent-specific context
                    scope.set_extra("agent_input", str(args[:2]) if args else None)
                    scope.set_extra("error_type", type(e).__name__)
                    
                    # Special handling for different agent types
                    if agent_name == "coder":
                        scope.set_extra("generation_failed", True)
                    elif agent_name == "evaluator":
                        scope.set_extra("test_execution_failed", True)
                    
                    # Capture the exception
                    sentry_sdk.capture_exception(e)
                    raise
        
        return wrapper
    return decorator

class SentryMetrics:
    """Custom metrics collection for Sentry"""
    
    @staticmethod
    def track_batch_execution(state: Dict[str, Any]):
        """Track complete batch execution metrics"""
        with sentry_sdk.push_scope() as scope:
            scope.set_tag("batch_status", "success" if state.get('pass') else "failed")
            scope.set_context("batch_metrics", {
                "retries": state.get('retries', 0),
                "tokens_used": state.get('tokens', 0),
                "test_passed": state.get('test_passed', False),
                "model": state.get('model', 'unknown')
            })
            
            # Performance tracking
            transaction = sentry_sdk.start_transaction(
                op="batch",
                name="ai_stack_batch_execution"
            )
            
            with transaction:
                # Add spans for each agent
                for agent in ['parser', 'coder', 'evaluator', 'reviewer', 'metric', 'alert']:
                    with transaction.start_child(op=f"agent.{agent}"):
                        pass  # Actual agent execution would happen here
                
                # Record measurements
                sentry_sdk.set_measurement("batch.tokens", state.get('tokens', 0))
                sentry_sdk.set_measurement("batch.retries", state.get('retries', 0))
                sentry_sdk.set_measurement("batch.duration", state.get('duration', 0))
    
    @staticmethod
    def track_api_usage(endpoint: str, duration: float, status_code: int):
        """Track API endpoint usage"""
        transaction = sentry_sdk.get_current_transaction()
        if transaction:
            transaction.set_tag("http.status_code", status_code)
            transaction.set_tag("endpoint", endpoint)
            sentry_sdk.set_measurement(f"api.{endpoint}.duration", duration)

# Integration with existing agents
def enhance_agents_with_sentry():
    """Add Sentry tracking to existing agents"""
    
    # Import existing agents
    from agents import coder, evaluator, reviewer, metric, alert
    
    # Wrap agent functions with error tracking
    coder.generate_code = track_agent_error("coder")(coder.generate_code)
    evaluator.run_tests = track_agent_error("evaluator")(evaluator.run_tests)
    reviewer.review_code = track_agent_error("reviewer")(reviewer.review_code)
    metric.calculate_metrics = track_agent_error("metric")(metric.calculate_metrics)
    alert.send_alert = track_agent_error("alert")(alert.send_alert)

# Health check integration
def create_sentry_health_endpoint():
    """Create endpoint to verify Sentry integration"""
    def sentry_health():
        try:
            # Test Sentry connection
            sentry_sdk.capture_message("Sentry health check", level="info")
            return {
                "status": "healthy",
                "sentry_enabled": bool(SENTRY_DSN),
                "environment": ENVIRONMENT,
                "release": RELEASE
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    return sentry_health

# Usage in main application
if __name__ == "__main__":
    # Initialize on startup
    if initialize_sentry():
        print("✅ Sentry initialized successfully")
        enhance_agents_with_sentry()
    else:
        print("⚠️ Sentry not initialized (no DSN)")
    
    # Example: Manual error capture
    try:
        raise ValueError("Test error for Sentry")
    except Exception as e:
        sentry_sdk.capture_exception(e)