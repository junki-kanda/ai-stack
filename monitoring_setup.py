#!/usr/bin/env python3
"""
Monitoring and observability setup for ai-stack
"""
import os
import time
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import asyncio
from functools import wraps

# Prometheus metrics (optional)
try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

# Sentry for error tracking
try:
    import sentry_sdk
    from sentry_sdk.integrations.logging import LoggingIntegration
    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False


class MetricsCollector:
    """Collect and expose metrics for monitoring"""
    
    def __init__(self):
        if PROMETHEUS_AVAILABLE:
            # Define Prometheus metrics
            self.batch_runs = Counter('batch_runs_total', 'Total number of batch runs', ['status'])
            self.batch_duration = Histogram('batch_duration_seconds', 'Batch execution duration')
            self.active_batches = Gauge('active_batches', 'Number of currently running batches')
            self.last_success_time = Gauge('last_success_timestamp', 'Timestamp of last successful run')
            self.error_rate = Gauge('error_rate', 'Current error rate')
            
        self.metrics_data = {
            'total_runs': 0,
            'successful_runs': 0,
            'failed_runs': 0,
            'total_duration': 0,
            'last_run_duration': 0,
            'last_error': None,
            'error_history': []
        }
    
    def record_batch_start(self):
        """Record the start of a batch run"""
        if PROMETHEUS_AVAILABLE:
            self.active_batches.inc()
        return time.time()
    
    def record_batch_end(self, start_time: float, success: bool, error: Optional[str] = None):
        """Record the end of a batch run"""
        duration = time.time() - start_time
        
        # Update Prometheus metrics
        if PROMETHEUS_AVAILABLE:
            self.active_batches.dec()
            self.batch_duration.observe(duration)
            self.batch_runs.labels(status='success' if success else 'failed').inc()
            
            if success:
                self.last_success_time.set(time.time())
        
        # Update internal metrics
        self.metrics_data['total_runs'] += 1
        self.metrics_data['total_duration'] += duration
        self.metrics_data['last_run_duration'] = duration
        
        if success:
            self.metrics_data['successful_runs'] += 1
        else:
            self.metrics_data['failed_runs'] += 1
            self.metrics_data['last_error'] = error
            self.metrics_data['error_history'].append({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': error
            })
            # Keep only last 100 errors
            self.metrics_data['error_history'] = self.metrics_data['error_history'][-100:]
        
        # Calculate error rate
        if self.metrics_data['total_runs'] > 0:
            error_rate = self.metrics_data['failed_runs'] / self.metrics_data['total_runs']
            if PROMETHEUS_AVAILABLE:
                self.error_rate.set(error_rate)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics as dictionary"""
        metrics = self.metrics_data.copy()
        if self.metrics_data['total_runs'] > 0:
            metrics['average_duration'] = self.metrics_data['total_duration'] / self.metrics_data['total_runs']
            metrics['success_rate'] = self.metrics_data['successful_runs'] / self.metrics_data['total_runs']
            metrics['error_rate'] = self.metrics_data['failed_runs'] / self.metrics_data['total_runs']
        return metrics
    
    def get_prometheus_metrics(self) -> bytes:
        """Get metrics in Prometheus format"""
        if PROMETHEUS_AVAILABLE:
            return generate_latest()
        return b""


class ErrorTracker:
    """Enhanced error tracking with Sentry integration"""
    
    def __init__(self, dsn: Optional[str] = None):
        self.dsn = dsn or os.getenv('SENTRY_DSN')
        
        if SENTRY_AVAILABLE and self.dsn:
            sentry_logging = LoggingIntegration(
                level=logging.INFO,
                event_level=logging.ERROR
            )
            
            sentry_sdk.init(
                dsn=self.dsn,
                integrations=[sentry_logging],
                traces_sample_rate=0.1,
                environment=os.getenv('FLY_APP_NAME', 'development')
            )
            self.enabled = True
        else:
            self.enabled = False
    
    def capture_exception(self, error: Exception, context: Optional[Dict[str, Any]] = None):
        """Capture an exception with context"""
        if self.enabled:
            with sentry_sdk.push_scope() as scope:
                if context:
                    for key, value in context.items():
                        scope.set_extra(key, value)
                sentry_sdk.capture_exception(error)
        else:
            # Fallback to logging
            logging.error(f"Error captured: {error}", exc_info=True, extra=context)
    
    def capture_message(self, message: str, level: str = 'info', context: Optional[Dict[str, Any]] = None):
        """Capture a message with context"""
        if self.enabled:
            with sentry_sdk.push_scope() as scope:
                if context:
                    for key, value in context.items():
                        scope.set_extra(key, value)
                sentry_sdk.capture_message(message, level=level)
        else:
            # Fallback to logging
            log_level = getattr(logging, level.upper(), logging.INFO)
            logging.log(log_level, message, extra=context)


class StructuredLogger:
    """Structured logging for better observability"""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        
        # JSON formatter for structured logs
        handler = logging.StreamHandler()
        handler.setFormatter(self.JsonFormatter())
        self.logger.addHandler(handler)
    
    class JsonFormatter(logging.Formatter):
        """Format logs as JSON for better parsing"""
        
        def format(self, record):
            log_data = {
                'timestamp': datetime.utcnow().isoformat(),
                'level': record.levelname,
                'logger': record.name,
                'message': record.getMessage(),
                'module': record.module,
                'function': record.funcName,
                'line': record.lineno
            }
            
            # Add extra fields
            if hasattr(record, 'extra'):
                log_data.update(record.extra)
            
            # Add exception info if present
            if record.exc_info:
                log_data['exception'] = self.formatException(record.exc_info)
            
            return json.dumps(log_data)
    
    def log_event(self, event: str, level: str = 'info', **kwargs):
        """Log a structured event"""
        log_method = getattr(self.logger, level)
        log_method(event, extra=kwargs)


def monitor_performance(metrics_collector: MetricsCollector):
    """Decorator to monitor function performance"""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                metrics_collector.record_batch_end(start_time, True)
                return result
            except Exception as e:
                duration = time.time() - start_time
                metrics_collector.record_batch_end(start_time, False, str(e))
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                metrics_collector.record_batch_end(start_time, True)
                return result
            except Exception as e:
                duration = time.time() - start_time
                metrics_collector.record_batch_end(start_time, False, str(e))
                raise
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


# Example usage in your batch processor
class MonitoredBatchExecutor:
    """Enhanced batch executor with monitoring"""
    
    def __init__(self, original_executor):
        self.executor = original_executor
        self.metrics = MetricsCollector()
        self.error_tracker = ErrorTracker()
        self.logger = StructuredLogger(__name__)
    
    def run_batch(self) -> Dict[str, Any]:
        """Run batch with full monitoring"""
        start_time = self.metrics.record_batch_start()
        
        self.logger.log_event(
            'batch_started',
            level='info',
            start_time=start_time
        )
        
        try:
            # Run the original batch
            result = self.executor.run_batch()
            
            # Record success
            self.metrics.record_batch_end(start_time, True)
            
            self.logger.log_event(
                'batch_completed',
                level='info',
                duration=time.time() - start_time,
                status='success'
            )
            
            return result
            
        except Exception as e:
            # Record failure
            self.metrics.record_batch_end(start_time, False, str(e))
            
            # Track error
            self.error_tracker.capture_exception(e, {
                'batch_start_time': start_time,
                'duration': time.time() - start_time
            })
            
            self.logger.log_event(
                'batch_failed',
                level='error',
                duration=time.time() - start_time,
                error=str(e),
                error_type=type(e).__name__
            )
            
            raise


# Health check endpoint additions
def create_monitoring_endpoints(app):
    """Add monitoring endpoints to your web app"""
    
    # Metrics endpoint for Prometheus
    async def metrics_endpoint(request):
        metrics = request.app['metrics_collector']
        return web.Response(
            body=metrics.get_prometheus_metrics(),
            content_type='text/plain'
        )
    
    # Detailed metrics endpoint
    async def detailed_metrics(request):
        metrics = request.app['metrics_collector']
        return web.json_response(metrics.get_metrics())
    
    # Add routes
    app.router.add_get('/metrics', metrics_endpoint)
    app.router.add_get('/metrics/detailed', detailed_metrics)


# Configuration
MONITORING_CONFIG = {
    'sentry_dsn': os.getenv('SENTRY_DSN'),
    'enable_prometheus': os.getenv('ENABLE_PROMETHEUS', 'true').lower() == 'true',
    'log_level': os.getenv('LOG_LEVEL', 'INFO'),
    'metrics_port': int(os.getenv('METRICS_PORT', '9090'))
}