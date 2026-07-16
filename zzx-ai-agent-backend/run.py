"""Startup entry. python run.py  |  $env:LLM_MODE='agent'; python run.py"""
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
    mode = os.getenv("LLM_MODE", "chain")
    print(f"ZZX-AI API  |  Mode: {mode}  |  http://localhost:8123")
    app.run(host="0.0.0.0", port=8123, debug=True, threaded=True)
