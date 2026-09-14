"""Startup entry. python run.py"""
import os
import sys
import ssl

# Windows SSL workaround — patch BOTH names since aiohttp calls create_default_context directly
if sys.platform == "win32" and sys.version_info < (3, 10):
    ssl._create_default_https_context = ssl._create_unverified_context
    ssl.create_default_context = ssl._create_unverified_context

from app import create_app

app = create_app()

if __name__ == "__main__":
    host = os.getenv("APP_HOST", "127.0.0.1")
    port = int(os.getenv("APP_PORT", "8123"))
    print(f"ZZX-AI API | http://{host}:{port}")
    app.run(
        host=host,
        port=port,
        debug=app.config["DEBUG"],
        threaded=True,
    )
