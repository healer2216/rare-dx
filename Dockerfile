FROM python:3.12-slim

WORKDIR /home/user/app

# 安装系统依赖（Node.js 用预编译二进制，避免 apt 安装 OOM）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    xz-utils \
    fonts-noto-cjk \
    fonts-wqy-microhei \
    && rm -rf /var/lib/apt/lists/*

# 下载预编译 Node.js 18（轻量，避免 NodeSource 脚本 OOM）
RUN curl -fsSL https://nodejs.org/dist/v18.20.0/node-v18.20.0-linux-x64.tar.xz \
    | tar -xJ -C /usr/local --strip-components=1 \
    && node --version && npm --version

# 复制依赖文件并安装 Python 依赖
COPY pyproject.toml README.md ./
COPY app/ ./app/
COPY config/ ./config/
COPY data/ ./data/
RUN pip install --no-cache-dir -e ".[dev]"

# 复制前端并安装依赖、构建（可选前端；有 package.json 才构建）
COPY frontend/ ./frontend/
RUN if [ -f frontend/package.json ]; then \
      cd frontend && \
      npm install && \
      npm run build; \
    fi

# 复制入口文件
COPY modelscope_app.py ./

EXPOSE 7860
ENTRYPOINT ["python", "-u", "modelscope_app.py"]
