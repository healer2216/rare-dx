FROM python:3.12-slim

WORKDIR /home/user/app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 Node.js 18+（前端构建需要）
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY pyproject.toml README.md ./
COPY app/ ./app/
COPY config/ ./config/
COPY data/hpo_dictionary.json ./data/
COPY data/disease_meta.json ./data/
COPY data/hpo_frequency/orphanet_freq.json ./data/hpo_frequency/
COPY data/hpo_learned_keywords.json ./data/ || true

# 安装 Python 依赖
RUN pip install --no-cache-dir -e ".[dev]"

# 复制并构建前端
COPY frontend/package*.json ./frontend/
RUN cd frontend && npm install
COPY frontend/ ./frontend/
RUN cd frontend && npm run build

# 复制入口文件
COPY app/main.py ./app/
COPY modelscope_app.py ./

# 暴露端口（创空间固定）
EXPOSE 7860

# 启动
ENTRYPOINT ["python", "-u", "modelscope_app.py"]
