#!/usr/bin/env python3
"""rare-dx ModelScope 创空间入口 — 同时启动 FastAPI 后端 + Next.js 前端。

监听 0.0.0.0:7860（创空间固定端口），通过子进程管理两个服务。
"""

import os
import subprocess
import sys
import signal
import time

PORT = 7860
BACKEND_PORT = 8765
FRONTEND_PORT = 3001

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BACKEND_DIR, "frontend")

processes = []


def start_backend():
    """启动 FastAPI 后端。"""
    print("[app.py] 启动后端 (uvicorn)...", flush=True)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "0.0.0.0", "--port", str(BACKEND_PORT)],
        cwd=BACKEND_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    processes.append(proc)
    return proc


def start_frontend():
    """启动 Next.js 前端（生产模式，用已构建的静态文件）。"""
    print("[app.py] 启动前端 (Next.js)...", flush=True)
    # 优先用已构建的产物（npm run build + npm start）
    build_dir = os.path.join(FRONTEND_DIR, ".next")
    if os.path.exists(build_dir):
        proc = subprocess.Popen(
            ["npx", "next", "start", "-p", str(FRONTEND_PORT)],
            cwd=FRONTEND_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        )
    else:
        # 没有构建产物就用 dev 模式（构建耗时较长）
        print("[app.py] 未检测到构建产物，使用 dev 模式启动...", flush=True)
        proc = subprocess.Popen(
            ["npx", "next", "dev", "-p", str(FRONTEND_PORT)],
            cwd=FRONTEND_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        )
    processes.append(proc)
    return proc


def start_caddy():
    """用简单的 Python 反向代理统一暴露 7860 端口。"""
    import http.server
    import urllib.request
    import urllib.error
    import json
    import threading

    class ProxyHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self._proxy()

        def do_POST(self):
            self._proxy()

        def _proxy(self):
            path = self.path
            # API 请求转发到后端
            if path.startswith("/api/"):
                target = f"http://127.0.0.1:{BACKEND_PORT}{path}"
            else:
                target = f"http://127.0.0.1:{FRONTEND_PORT}{path}"

            try:
                body = None
                if self.command == "POST":
                    content_length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(content_length)

                req = urllib.request.Request(
                    target,
                    data=body,
                    headers=dict(self.headers),
                    method=self.command,
                )
                with urllib.request.urlopen(req, timeout=300) as resp:
                    self.send_response(resp.status)
                    for key, value in resp.headers.items():
                        if key.lower() not in ("transfer-encoding", "content-encoding", "content-length"):
                            self.send_header(key, value)
                    self.end_headers()
                    self.wfile.write(resp.read())
            except urllib.error.HTTPError as e:
                self.send_response(e.code)
                self.end_headers()
                self.wfile.write(e.read())
            except Exception as e:
                self.send_response(502)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(f"Proxy error: {e}".encode())

    server = http.server.HTTPServer(("0.0.0.0", PORT), ProxyHandler)
    print(f"[app.py] 反向代理已启动 -> 0.0.0.0:{PORT}", flush=True)
    server.serve_forever()


def signal_handler(signum, frame):
    """优雅关闭所有子进程。"""
    print(f"\n[app.py] 收到信号 {signum}，关闭服务...", flush=True)
    for proc in processes:
        if proc.poll() is None:
            proc.terminate()
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # 启动后端
    backend = start_backend()
    time.sleep(3)

    # 启动前端
    start_frontend()
    time.sleep(2)

    # 启动反向代理（统一端口 7860）
    print(f"[app.py] rare-dx 已启动 -> http://0.0.0.0:{PORT}", flush=True)
    start_caddy()
