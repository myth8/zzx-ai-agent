"""
生产启动方式：
cd zzx-ai-agent-backend
gunicorn -c gunicorn.conf.py wsgi:app
当前默认配置为：
1 Worker
4 Threads
gthread Worker 类型
180 秒请求超时
暂时保持一个 Worker，是因为当前 RAG 在线索引、Embedding 和 Reranker 状态仍然属于进程内状态。贸然增加 Worker 会导致不同进程看到不同版本的索引。后续完成分布式重建锁和索引版本协调后，再增加 Worker 数量。
另外，APP_ENV=production 时通过 python run.py 启动会被明确拒绝，避免生产环境误用 Flask 开发服务器。Gunicorn baseline tuned for SSE and process-local RAG model state.
"""
import os


def _positive_int(name, default):
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be greater than zero")
    return value


bind = f"{os.getenv('APP_HOST', '127.0.0.1')}:{_positive_int('APP_PORT', 8123)}"

# gthread allows several SSE connections without introducing another process
# copy of Embedding/Reranker models. Keep one worker until RAG mutation and
# in-memory index publication are coordinated across processes.
worker_class = "gthread"
workers = _positive_int("GUNICORN_WORKERS", 1)
threads = _positive_int("GUNICORN_THREADS", 4)

# Agent execution currently has a 90-second internal ceiling. Leave enough
# room for streaming completion and persistence while still terminating stuck
# requests eventually.
timeout = _positive_int("GUNICORN_TIMEOUT", 180)
graceful_timeout = _positive_int("GUNICORN_GRACEFUL_TIMEOUT", 30)
keepalive = _positive_int("GUNICORN_KEEPALIVE", 5)

preload_app = False
accesslog = "-"
errorlog = "-"
capture_output = True
access_log_format = (
    '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s '
    'request_id="%({x-request-id}o)s" duration_us=%(D)s'
)

