FROM python:3.12-slim

WORKDIR /home/user/app

# 安装系统依赖（含 Node.js 18+）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# 复制 Python 依赖文件并安装
COPY pyproject.toml README.md ./
COPY app/ ./app/
COPY config/ ./config/
COPY data/ ./data/

# 安装 Python 依赖
RUN pip install --no-cache-dir -e ".[dev]"

# 复制前端依赖文件并安装（不构建，运行时 dev 模式启动）
COPY frontend/package*.json ./frontend/
RUN cd frontend && npm install

# 复制前端源码
COPY frontend/ ./frontend/

# 复制入口文件
COPY modelscope_app.py ./

# 暴露端口（创空间固定）
EXPOSE 7860

# 启动
ENTRYPOINT ["python", "-u", "modelscope_app.py"]
