# rare-dx · 部署文档

> 罕见病诊断辅助系统 — 五层临床推理引擎 + 全量表型词典

---

## 目录

1. [环境要求](#一环境要求)
2. [快速部署（一键脚本）](#二快速部署一键脚本)
3. [手动部署](#三手动部署)
4. [配置 API 密钥](#四配置-api-密钥)
5. [启动与停止](#五启动与停止)
6. [Nginx 反向代理（生产推荐）](#六nginx-反向代理生产推荐)
7. [HTTPS 配置](#七https-配置)
8. [守护进程（systemd）](#八守护进程systemd)
9. [维护与更新](#九维护与更新)
10. [故障排除](#十故障排除)

---

## 一、环境要求

### 硬件最低配置

| 组件 | 配置 |
|------|------|
| CPU | 2 核 |
| 内存 | 4 GB |
| 磁盘 | 10 GB 可用空间 |
| 网络 | 可访问 GitHub（克隆代码）、可调用 LLM API（DeepSeek/OpenAI） |

### 推荐配置

| 组件 | 配置 |
|------|------|
| CPU | 4 核 |
| 内存 | 8 GB |
| 磁盘 | 20 GB SSD |
| 网络 | 低延迟访问 LLM API（< 200ms）|

### 软件依赖

| 软件 | 版本要求 | 用途 |
|------|---------|------|
| Python | ≥ 3.12 | 后端运行环境 |
| Node.js | ≥ 18 | 前端构建与运行 |
| npm | ≥ 9 | 前端依赖管理 |
| Git | ≥ 2.0 | 代码拉取与版本管理 |
| Nginx | ≥ 1.20（生产推荐） | 反向代理与 HTTPS 终止 |

---

## 二、快速部署（一键脚本）

> 适用于 **Ubuntu 22.04 / 24.04** 或 **Debian 12** 系统。

```bash
# 下载一键部署脚本
curl -fsSL -o deploy-rare-dx.sh https://raw.githubusercontent.com/healer2216/rare-dx/main/scripts/deploy.sh

# 赋予执行权限
chmod +x deploy-rare-dx.sh

# 执行部署（会提示输入 API keys）
bash deploy-rare-dx.sh
```

脚本会自动完成：
1. 安装系统依赖（Python3.12 / Node.js 18+）
2. 克隆仓库
3. 安装 Python 依赖（pip install）
4. 安装前端依赖（npm install）
5. 引导配置 API 密钥
6. 启动后端（uvicorn）和前端（next dev）
7. 可选：配置 Nginx 反向代理 + systemd 服务

---

## 三、手动部署

### 3.1 克隆仓库

```bash
git clone https://github.com/healer2216/rare-dx.git
cd rare-dx
```

### 3.2 后端依赖安装

```bash
# 推荐使用虚拟环境
python3 -m venv .venv
source .venv/bin/activate  # Linux/Mac
# 或 .venv\Scripts\activate  # Windows

# 安装依赖
pip install -e ".[dev]"
```

### 3.3 前端依赖安装

```bash
cd frontend
npm install
cd ..
```

### 3.4 配置 API 密钥

```bash
cp .env.example .env
```

编辑 `.env` 文件填入真实 API keys（见[第四节](#四配置-api-密钥)）。

### 3.5 启动服务

```bash
# 终端1：启动后端（端口 8765）
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8765 --reload

# 终端2：启动前端（端口 3001）
cd frontend && npm run dev -- -p 3001
```

浏览器访问 `http://127.0.0.1:3001`

---

## 四、配置 API 密钥

### 4.1 必需密钥

| 环境变量 | 说明 | 获取方式 |
|---------|------|---------|
| `STEPFUN_API_KEY` | LLM 推理（必需，用于表型提取/假设生成/报告） | [stepfun.com](https://platform.stepfun.com) |
| `KNOWS_API_KEY` | 循证医学证据检索（必需） | 联系 KnowS 团队获取 |
| `KNOWS_BASE_URL` | KnowS API 地址 | 默认 `https://api.nullht.com/v1` |

### 4.2 可选密钥

| 环境变量 | 说明 | 获取方式 |
|---------|------|---------|
| `DEEPSEEK_API_KEY` | LLM 主力模型（如 STEPFUN 不可用时自动切换） | [platform.deepseek.com](https://platform.deepseek.com) |
| `OPENAI_API_KEY` | 备选 LLM（如 DeepSeek 不可用时切换） | [platform.openai.com](https://platform.openai.com) |
| `QWEN_API_KEY` | 备选 LLM | [aliyun.com](https://www.aliyun.com/product/dashscope) |

### 4.3 配置优先级

LLM 调用顺序（按 `config/llm.yaml` 的 `fallback_chain`）：
```
deepseek → openai → qwen → stepfun
```

当前 `agent_model_map` 默认使用 `deepseek`。如果不配置 DeepSeek，系统会自动切换到下一个可用的 Provider。

### 4.4 验证配置

```bash
# 验证环境变量已加载
python3 -c "from dotenv import load_dotenv; load_dotenv(); import os; print('STEPFUN:', '✅' if os.getenv('STEPFUN_API_KEY') else '❌'); print('KNOWS:', '✅' if os.getenv('KNOWS_API_KEY') else '❌')"

# 验证后端启动
curl -s http://127.0.0.1:8765/api/health
# → {"status":"ok","version":"0.1.0"}

# 验证 SSE 诊断流
curl -sN "http://127.0.0.1:8765/api/diagnostic/stream?user_message=test&session_id=check"
# → 返回事件序列（round_start → ... → round_end）
```

---

## 五、启动与停止

### 5.1 开发模式

```bash
# 后端（--reload 自动热重载代码变更）
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8765 --reload

# 前端（next dev 自动热重载）
cd frontend && npm run dev -- -p 3001
```

### 5.2 生产模式

```bash
# 后端（关闭 reload，使用 gunicorn 或多 worker）
pip install gunicorn
gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.main:app --bind 127.0.0.1:8765

# 前端（构建静态文件，用 Nginx 托管）
cd frontend
npm run build
npm start -p 3001
# 或：使用 PM2
npm install -g pm2
pm2 start npm --name "rare-dx-frontend" -- start -- -p 3001
```

### 5.3 停止服务

```bash
# 查找并停止进程
ps aux | grep uvicorn | grep -v grep
kill <PID>

ps aux | grep "next dev" | grep -v grep
kill <PID>
```

---

## 六、Nginx 反向代理（生产推荐）

### 6.1 安装 Nginx

```bash
sudo apt update && sudo apt install nginx -y
```

### 6.2 配置站点

创建 `/etc/nginx/sites-available/rare-dx`：

```nginx
server {
    listen 80;
    server_name your-domain.com;  # 替换为你的域名或 IP

    client_max_body_size 10M;
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;

    # 前端静态文件（npm run build 后）
    root /path/to/rare-dx/frontend/out;
    index index.html;

    # API 代理到后端
    location /api/ {
        proxy_pass http://127.0.0.1:8765;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;          # SSE 必需
        proxy_cache off;             # SSE 不缓存
        chunked_transfer_encoding on;
    }

    # 前端页面（使用 Next.js 代理时，转发到 3001）
    location / {
        proxy_pass http://127.0.0.1:3001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 6.3 启用站点

```bash
sudo ln -s /etc/nginx/sites-available/rare-dx /etc/nginx/sites-enabled/
sudo nginx -t          # 测试配置
sudo systemctl reload nginx
```

---

## 七、HTTPS 配置

### 7.1 使用 Let's Encrypt（免费）

```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d your-domain.com
```

证书自动续期（certbot 会创建 systemd timer）：

```bash
# 手动测试续期
sudo certbot renew --dry-run
```

### 7.2 完整 HTTPS 配置示例

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # ...（其余配置同上）
}

server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$host$request_uri;
}
```

---

## 八、守护进程（systemd）

### 8.1 后端服务

创建 `/etc/systemd/system/rare-dx-backend.service`：

```ini
[Unit]
Description=rare-dx Backend
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/rare-dx
EnvironmentFile=/path/to/rare-dx/.env
ExecStart=/path/to/rare-dx/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8765
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 8.2 前端服务

创建 `/etc/systemd/system/rare-dx-frontend.service`：

```ini
[Unit]
Description=rare-dx Frontend
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/rare-dx/frontend
ExecStart=/usr/bin/npm run dev -- -p 3001
Restart=always
RestartSec=5
Environment=NODE_ENV=production

[Install]
WantedBy=multi-user.target
```

### 8.3 启动与启用

```bash
sudo systemctl daemon-reload
sudo systemctl enable rare-dx-backend rare-dx-frontend
sudo systemctl start rare-dx-backend rare-dx-frontend

# 查看状态
sudo systemctl status rare-dx-backend
sudo systemctl status rare-dx-frontend

# 查看日志
sudo journalctl -u rare-dx-backend -f
sudo journalctl -u rare-dx-frontend -f
```

---

## 九、维护与更新

### 9.1 代码更新

```bash
cd /path/to/rare-dx
git pull origin main

# 更新后端依赖
source .venv/bin/activate
pip install -e ".[dev]"

# 更新前端依赖
cd frontend
npm install
cd ..

# 重启服务
sudo systemctl restart rare-dx-backend rare-dx-frontend
```

### 9.2 数据文件维护

| 文件 | 说明 | 维护方式 |
|------|------|---------|
| `data/hpo_dictionary.json` | 全量表型词典（11,606 HPO） | 从 `orphanet_freq.json` 自动生成，无需手动维护 |
| `data/hpo_learned_keywords.json` | LLM 学习缓存 | 自动积累，可安全清空（清空后重新从 LLM 学习） |
| `data/hpo_frequency/orphanet_freq.json` | Orphanet 频率表 | 按需更新（从 HPO 官网下载最新版） |
| `data/disease_meta.json` | 疾病元数据 | 随频率表同步更新 |
| `checkpoints.db` | 会话检查点 | 按需清理旧会话 |

### 9.3 日志轮转

使用 `logrotate` 管理日志：

```bash
sudo tee /etc/logrotate.d/rare-dx << 'EOF'
/path/to/rare-dx/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
EOF
```

### 9.4 监控检查

```bash
# 健康检查端点
curl -s http://127.0.0.1:8765/api/health | grep -q '"status":"ok"' && echo "健康" || echo "异常"

# 可集成到 Prometheus + Alertmanager 或 Uptime Kuma
```

---

## 十、故障排除

### 10.1 前端页面白屏 / 按钮无响应

```
可能原因 → 解决方法
────────── ──────────
next.config.js 缺失   → 检查 frontend/next.config.js 是否存在
tsconfig.json 缺少    → 确保有 baseUrl + paths 配置
@/ 路径别名未配置     → 检查 tsconfig.json 的 paths 配置
API 代理未生效        → curl http://localhost:3001/api/health 测试
```

### 10.2 SSE 连接无响应

```
可能原因 → 解决方法
────────── ──────────
后端未运行            → python3 -m uvicorn app.main:app --port 8765
端口占用              → lsof -i:8765，kill 旧进程
Nginx proxy_buffering → 确保 proxy_buffering off（SSE 必需）
CORS 配置错误         → 检查 main.py 的 CORSMiddleware 配置
```

### 10.3 LLM 调用失败

```
可能原因 → 解决方法
────────── ──────────
API Key 未配置        → 检查 .env 文件，确保变量已填
API Key 过期          → 登录对应平台检查额度
网络不通              → curl https://api.deepseek.com/v1 测试
模型不可用            → 在 config/llm.yaml 更换模型名
所有 Provider 失败     → 检查至少配置了 2 个 Provider 用于 failover
```

### 10.4 Layer 2-5 级联空

```
可能原因 → 解决方法
────────── ──────────
Bayesian 无匹配       → LLM 兜底路径应自动触发，检查 hypothesis_generator.py
conservative_downgrade → 切换到 relaxed 模式暂时绕过，或提高置信度阈值
安全闸门拦截          → 检查 `safety_valve` SSE 事件内容
```

### 10.5 数据文件问题

```bash
# 重建全量词典（如果 hpo_dictionary.json 损坏）
python3 -c "
import json
# 从频率表重建（耗时约 30 秒）
from collections import OrderedDict
with open('data/hpo_frequency/orphanet_freq.json') as f:
    data = json.load(f)
hpos = OrderedDict()
for e in data['entries']:
    hid = e['hpo_id']
    if hid not in hpos:
        hpos[hid] = {'hpo_id': hid, 'term_name': e.get('hpo_name','') or hid, 'keywords': [], 'default_modifiers': {}}
    hname = e.get('hpo_name','')
    if hname and hname not in hpos[hid]['keywords']:
        hpos[hid]['keywords'].append(hname)
with open('data/hpo_dictionary.json','w',encoding='utf-8') as f:
    json.dump(list(hpos.values()), f, ensure_ascii=False, indent=2)
print(f'重建完成: {len(hpos)} 个 HPO')
"

# 清空学习缓存（从头积累）
rm data/hpo_learned_keywords.json && touch data/hpo_learned_keywords.json && echo '[]' > data/hpo_learned_keywords.json
```

---

## 附录

### 端口参考

| 端口 | 服务 | 说明 |
|------|------|------|
| 8765 | 后端 (FastAPI) | LLM + KnowS 推理引擎 |
| 3001 | 前端 (Next.js) | Web UI，含 `/api` 代理 |
| 80 | Nginx | HTTP 反向代理（生产） |
| 443 | Nginx | HTTPS 反向代理（生产） |

### 目录结构

```
rare-dx/
├── app/              # 后端 Python 源码
├── frontend/         # 前端 Next.js 源码
├── data/             # 数据文件（词典/频率表/学习缓存）
├── config/           # 配置文件（llm.yaml）
├── docs/             # 文档
├── tests/            # 测试用例
├── .env.example      # 配置模板（去敏）
├── .env              # ⚠️ 真实密钥（.gitignore 保护）
├── .mcp.json         # MCP 服务配置
└── .atomcode/        # AtomCode 自动化配置
```
