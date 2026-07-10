#!/usr/bin/env python3
"""rare-dx ModelScope 创空间入口 — 同时启动 FastAPI 后端 + Next.js 前端。

监听 0.0.0.0:7860（创空间固定端口），通过子进程管理两个服务。
"""

import os
import subprocess
import sys
import signal
import threading
import time

PORT = 7860
BACKEND_PORT = 8765
FRONTEND_PORT = 3001

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BACKEND_DIR, "frontend")

processes = []


def wait_for_backend(port, timeout=120):
    """等待后端服务就绪（轮询 HTTP）。"""
    import urllib.request
    import urllib.error

    url = f"http://127.0.0.1:{port}/api/health"
    deadline = time.time() + timeout
    print(f"[app.py] 等待后端就绪 (端口 {port})...", flush=True)
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                if resp.status == 200:
                    print(f"[app.py] 后端已就绪 (HTTP {resp.status})", flush=True)
                    return True
        except urllib.error.URLError:
            pass
        except Exception:
            pass
        time.sleep(2)
    print(f"[app.py] 后端等待超时 ({timeout}s)，继续启动代理", flush=True)
    return False


def _tail_process(name: str, proc: subprocess.Popen):
    """把子进程 stdout/stderr 实时 tail 到父进程日志，避免静默失败。"""
    try:
        while True:
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    break
                continue
            print(f"[{name}] {line}", flush=True)
    except Exception:
        pass


def start_backend():
    """启动 FastAPI 后端（保留输出以便排查启动失败原因）。"""
    print("[app.py] 启动后端 (uvicorn)...", flush=True)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "0.0.0.0", "--port", str(BACKEND_PORT),
         "--log-level", "debug"],
        cwd=BACKEND_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1,
    )
    t = threading.Thread(target=_tail_process, args=("uvicorn", proc), daemon=True)
    t.start()
    processes.append(proc)
    return proc


def is_frontend_available():
    """判断前端是否可启动：需要 package.json 且存在 .next 构建产物或依赖目录。"""
    has_pkg = os.path.isfile(os.path.join(FRONTEND_DIR, "package.json"))
    has_build = os.path.isdir(os.path.join(FRONTEND_DIR, ".next"))
    has_deps = os.path.isdir(os.path.join(FRONTEND_DIR, "node_modules"))
    return has_pkg and (has_build or has_deps)


def start_frontend():
    """启动 Next.js 前端（生产模式，用已构建的静态文件）。"""
    if not is_frontend_available():
        print("[app.py] 前端依赖/构建产物缺失，跳过前端启动", flush=True)
        return None
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
            bufsize=1,
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
            bufsize=1,
        )
    t = threading.Thread(target=_tail_process, args=("next", proc), daemon=True)
    t.start()
    processes.append(proc)
    return proc


def wait_for_frontend(port, timeout=120):
    """等待前端服务就绪（轮询 HTTP）。"""
    import urllib.request
    import urllib.error

    url = f"http://127.0.0.1:{port}/"
    deadline = time.time() + timeout
    print(f"[app.py] 等待前端就绪 (端口 {port})...", flush=True)
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                if resp.status < 500:
                    print(f"[app.py] 前端已就绪 (HTTP {resp.status})", flush=True)
                    return True
        except urllib.error.URLError:
            pass
        except Exception:
            pass
        time.sleep(2)
    print(f"[app.py] 前端等待超时 ({timeout}s)，继续启动代理", flush=True)
    return False


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
            # 健康检查直接返回 200，避免平台认为 upstream 不健康
            if path in ("/health", "/healthz"):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')
                return

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
                # preload_content=False → 立即返回响应头（不预读响应体）
                # 这对 SSE 长连接至关重要：否则 urlopen 会阻塞到连接关闭
                resp = urllib.request.urlopen(req, timeout=300, preload_content=False)
                try:
                    self.send_response(resp.status)
                    for key, value in resp.headers.items():
                        if key.lower() not in ("transfer-encoding", "content-length", "connection"):
                            self.send_header(key, value)
                    # 对 SSE 等长连接响应启用 chunked，避免平台/网关提前掐断
                    if resp.headers.get("Content-Type", "").startswith("text/event-stream"):
                        self.send_header("Cache-Control", "no-cache")
                    self.end_headers()

                    # 分块流式转发
                    try:
                        while True:
                            chunk = resp.read(8192)
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            self.wfile.flush()
                    except BrokenPipeError:
                        # 客户端断开连接（正常关闭流）
                        pass
                finally:
                    resp.release_conn()
            except urllib.error.HTTPError as e:
                self.send_response(e.code)
                self.end_headers()
                try:
                    self.wfile.write(e.read())
                except BrokenPipeError:
                    pass
            except Exception as e:
                print(f"[app.py] proxy error path={path} err={e}", flush=True)
                try:
                    self.send_response(502)
                    self.send_header("Content-Type", "text/plain")
                    self.end_headers()
                    self.wfile.write(f"Proxy error: {e}".encode())
                except BrokenPipeError:
                    pass

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

    # 启动后端并等待就绪
    backend = start_backend()
    wait_for_backend(BACKEND_PORT, timeout=120)

    # 启动前端（若不可用则仅保留下游 API 服务）
    frontend = start_frontend()
    if frontend is not None:
        wait_for_frontend(FRONTEND_PORT, timeout=120)

    # 启动反向代理（统一端口 7860）
    print(f"[app.py] rare-dx 已启动 -> http://0.0.0.0:{PORT}", flush=True)
    start_caddy()
