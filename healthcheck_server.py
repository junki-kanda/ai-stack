#!/usr/bin/env python3
"""
Production-ready health check server for batch applications.
Provides HTTP endpoints for container orchestration while running batch jobs.
"""
import asyncio
import os
import signal
import sys
import time
import logging
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor
import subprocess
from pathlib import Path

# FastAPIの代わりに標準ライブラリのみ使用する場合
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# より高機能な実装にはaiohttp使用
try:
    from aiohttp import web
    USE_AIOHTTP = True
except ImportError:
    USE_AIOHTTP = False

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BatchExecutor:
    """バッチ処理を管理するクラス"""
    
    def __init__(self):
        self.is_running = False
        self.last_run: Optional[datetime] = None
        self.last_status: Optional[str] = None
        self.last_error: Optional[str] = None
        self.run_count = 0
        self.error_count = 0
        self.consecutive_errors = 0
        
    def run_batch(self) -> Dict[str, Any]:
        """バッチ処理を実行"""
        self.is_running = True
        start_time = time.time()
        
        try:
            logger.info("Starting batch process...")
            
            # 環境変数のチェック
            required_env = ['OPENAI_API_KEY']
            missing_env = [env for env in required_env if not os.getenv(env)]
            if missing_env:
                raise ValueError(f"Missing required environment variables: {missing_env}")
            
            # バッチプロセスの実行
            result = subprocess.run(
                [sys.executable, '-m', 'orchestrator.main'],
                capture_output=True,
                text=True,
                timeout=300  # 5分のタイムアウト
            )
            
            # 実行結果の処理
            duration = time.time() - start_time
            self.last_run = datetime.now(timezone.utc)
            self.run_count += 1
            
            if result.returncode == 0:
                self.last_status = 'success'
                self.last_error = None
                self.consecutive_errors = 0
                logger.info(f"Batch completed successfully in {duration:.2f}s")
                
                return {
                    'status': 'success',
                    'duration': duration,
                    'output': result.stdout[-1000:] if result.stdout else None  # 最後の1000文字
                }
            else:
                self.last_status = 'failed'
                self.last_error = result.stderr or f"Exit code: {result.returncode}"
                self.error_count += 1
                self.consecutive_errors += 1
                logger.error(f"Batch failed with code {result.returncode}: {self.last_error}")
                
                return {
                    'status': 'failed',
                    'duration': duration,
                    'error': self.last_error,
                    'exit_code': result.returncode
                }
                
        except subprocess.TimeoutExpired:
            self.last_status = 'timeout'
            self.last_error = 'Process timeout after 300 seconds'
            self.error_count += 1
            self.consecutive_errors += 1
            logger.error("Batch process timeout")
            
            return {
                'status': 'timeout',
                'duration': time.time() - start_time,
                'error': self.last_error
            }
            
        except Exception as e:
            self.last_status = 'error'
            self.last_error = str(e)
            self.error_count += 1
            self.consecutive_errors += 1
            logger.exception("Batch process error")
            
            return {
                'status': 'error',
                'duration': time.time() - start_time,
                'error': self.last_error
            }
            
        finally:
            self.is_running = False
    
    def get_status(self) -> Dict[str, Any]:
        """現在のステータスを取得"""
        return {
            'is_running': self.is_running,
            'last_run': self.last_run.isoformat() if self.last_run else None,
            'last_status': self.last_status,
            'last_error': self.last_error,
            'run_count': self.run_count,
            'error_count': self.error_count,
            'consecutive_errors': self.consecutive_errors,
            'health_score': self._calculate_health_score()
        }
    
    def _calculate_health_score(self) -> float:
        """ヘルススコアを計算 (0.0-1.0)"""
        if self.run_count == 0:
            return 1.0  # まだ実行されていない場合は健全とみなす
        
        # エラー率と連続エラーを考慮
        error_rate = self.error_count / self.run_count
        consecutive_penalty = min(self.consecutive_errors * 0.2, 0.8)
        
        return max(0.0, 1.0 - error_rate - consecutive_penalty)


class HealthCheckServer:
    """ヘルスチェックサーバー"""
    
    def __init__(self, port: int = 8080, run_batch_on_start: bool = True):
        self.port = port
        self.batch_executor = BatchExecutor()
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.run_batch_on_start = run_batch_on_start
        self.server_start_time = datetime.now(timezone.utc)
        self.shutdown_event = asyncio.Event()
        
    async def health_check(self, request=None) -> Dict[str, Any]:
        """基本的なヘルスチェックエンドポイント"""
        health_score = self.batch_executor._calculate_health_score()
        
        # ヘルススコアが0.3未満の場合は不健全とみなす
        is_healthy = health_score >= 0.3
        
        return {
            'status': 'healthy' if is_healthy else 'unhealthy',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'service': 'ai-stack-batch',
            'version': os.getenv('APP_VERSION', 'unknown'),
            'health_score': health_score
        }
    
    async def detailed_status(self, request=None) -> Dict[str, Any]:
        """詳細なステータスエンドポイント"""
        return {
            'server': {
                'status': 'running',
                'uptime_seconds': (datetime.now(timezone.utc) - self.server_start_time).total_seconds(),
                'pid': os.getpid(),
                'memory_mb': self._get_memory_usage()
            },
            'batch': self.batch_executor.get_status(),
            'environment': {
                'fly_region': os.getenv('FLY_REGION', 'unknown'),
                'fly_app_name': os.getenv('FLY_APP_NAME', 'unknown'),
                'has_openai_key': bool(os.getenv('OPENAI_API_KEY')),
                'has_slack_webhook': bool(os.getenv('SLACK_WEBHOOK_URL'))
            }
        }
    
    async def trigger_batch(self, request=None) -> Dict[str, Any]:
        """手動でバッチを実行するエンドポイント"""
        if self.batch_executor.is_running:
            return {
                'status': 'already_running',
                'message': 'Batch is already running'
            }
        
        # 非同期でバッチを実行
        loop = asyncio.get_event_loop()
        future = loop.run_in_executor(self.executor, self.batch_executor.run_batch)
        
        return {
            'status': 'started',
            'message': 'Batch execution started',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    def _get_memory_usage(self) -> float:
        """メモリ使用量を取得 (MB)"""
        try:
            import psutil
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / 1024 / 1024
        except ImportError:
            return -1
    
    async def run_server_aiohttp(self):
        """aiohttpを使用したサーバー実装"""
        app = web.Application()
        
        # ルーティング設定
        app.router.add_get('/health', self._wrap_handler(self.health_check))
        app.router.add_get('/status', self._wrap_handler(self.detailed_status))
        app.router.add_post('/trigger', self._wrap_handler(self.trigger_batch))
        app.router.add_get('/', self._wrap_handler(self.health_check))
        
        # サーバー起動
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', self.port)
        await site.start()
        
        logger.info(f"Health check server started on port {self.port}")
        
        # 初回バッチ実行
        if self.run_batch_on_start:
            await self.trigger_batch()
        
        # シャットダウンまで待機
        await self.shutdown_event.wait()
        await runner.cleanup()
    
    def _wrap_handler(self, handler):
        """ハンドラーをラップしてJSONレスポンスを返す"""
        async def wrapped(request):
            result = await handler(request)
            return web.json_response(result)
        return wrapped
    
    async def run(self):
        """サーバーを起動"""
        if USE_AIOHTTP:
            await self.run_server_aiohttp()
        else:
            await self.run_server_simple()
    
    async def run_server_simple(self):
        """標準ライブラリのみを使用したサーバー実装"""
        # シンプルなHTTPサーバーの実装
        class HealthHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/health':
                    response = asyncio.run(self.server.health_check())
                elif self.path == '/status':
                    response = asyncio.run(self.server.detailed_status())
                else:
                    response = {'error': 'Not found'}
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(response).encode())
            
            def log_message(self, format, *args):
                # アクセスログを抑制
                pass
        
        HealthHandler.server = self
        
        server = HTTPServer(('0.0.0.0', self.port), HealthHandler)
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        
        logger.info(f"Simple health check server started on port {self.port}")
        
        if self.run_batch_on_start:
            await self.trigger_batch()
        
        await self.shutdown_event.wait()
        server.shutdown()
    
    def shutdown(self):
        """サーバーをシャットダウン"""
        logger.info("Shutting down health check server...")
        self.shutdown_event.set()


async def main():
    """メインエントリーポイント"""
    # 環境変数から設定を読み込み
    port = int(os.getenv('HEALTH_CHECK_PORT', '8080'))
    run_on_start = os.getenv('RUN_BATCH_ON_START', 'true').lower() == 'true'
    
    # サーバーインスタンスを作成
    server = HealthCheckServer(port=port, run_batch_on_start=run_on_start)
    
    # シグナルハンドラーの設定
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}")
        server.shutdown()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # サーバー起動
    try:
        await server.run()
    except Exception as e:
        logger.exception(f"Server error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    # Python 3.7+ が必要
    if sys.version_info < (3, 7):
        logger.error("Python 3.7+ is required")
        sys.exit(1)
    
    # 非同期イベントループを起動
    asyncio.run(main())