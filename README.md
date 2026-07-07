# rare-dx · 罕见病诊断辅助系统

> 医学 AI 极客松项目 — 五层临床推理引擎 + 循证证据池

## 定位

面向遗传科/儿科/内科执业医师的罕见病诊断辅助系统。不是"症状搜索"，而是将**临床诊断推理过程形式化**为五层递进分析：

```
表型深度分析 → 贝叶斯假设生成 → 时序推理 → 遗传推理 → 诊断路径规划
```

每层输出结构化推理结果 + KnowS 多源循证证据，全链路可审计。

## 核心特性

- **五层推理引擎**：模拟临床鉴别诊断的完整思维链
- **贝叶斯概率推理**：基于 Orphanet/OMIM 疾病-表型频率表的量化诊断
- **时序推理**：发病年龄、进展速度、症状序列作为诊断信号
- **遗传推理**：家系分析 + 孟德尔遗传模式推断
- **诊断路径规划**：基于 EVOI（信息期望值）推荐最优下一步检查
- **循证证据集成**：KnowS 6 源医学证据检索，每层推理均有文献支撑
- **证据弹窗系统**：每个推理节点右上角 `🅔 N` 徽标 → 点击弹出证据明细 → 有 DOI 的文献可跳转原文
- **安全机制**：4 类安全阀 + 3 档闸门（standard / relaxed / strict）+ 高风险升级 + 议题漂移检测

## 技术栈

| 层 | 技术 |
|---|------|
| 后端 | Python 3.12+ / FastAPI / LangGraph / Pydantic v2 |
| 前端 | Next.js 14 / TypeScript / Tailwind / shadcn/ui |
| LLM | DeepSeek-V3 / GPT-4o / Qwen / StepFun (`step-3.7-flash`) |
| 证据 | KnowS Evidence Search API（6 源：paper_en/paper_cn/guide/trial/meeting/package_insert） |
| 知识库 | HPO / Orphanet / OMIM / 扩展常见病库（34 疾病，201 频率条目）|
| 存储 | SQLite（诊断会话 + 审计日志持久化）|

## 架构概览

```
用户输入 (临床描述)
  │
  ├─ [Safety]    议题漂移检测 / 高风险关键词 / 跨层冲突
  │
  ├─ Layer 1: 表型分析器      → HPO 术语提取 + NLP 增强
  │    └─ KnowS: Orphanet + HPO 检索
  ├─ Layer 2: 假设生成器      → 贝叶斯后验排序 Top-3
  │    └─ KnowS: PubMed + 中文期刊检索
  ├─ Layer 3: 时序推理器      → 发病年龄/进展模式匹配
  │    └─ KnowS: PubMed + MedlinePlus 检索
  ├─ Layer 4: 遗传推理器      → 孟德尔模式推断
  │    └─ KnowS: Orphanet + 指南检索
  ├─ Layer 5: 路径规划器      → EVOI 排序推荐检查
  │    └─ KnowS: ClinicalTrials + PubMed 检索
  │
  ├─ Layer 6: 报告综合器      → 结构化报告 + LLM 临床印象
  │
  └─ [Persist]  SQLite 保存会话 + 审计日志
```

## 快速开始

### 前提

- Python 3.12+
- Node.js 18+
- API keys：
  - `STEPFUN_API_KEY`（必需，`step_plan` 套餐）
  - `KNOWS_API_KEY` + `KNOWS_BASE_URL`（必需，循证检索）
- Noto Sans CJK 字体（PDF 导出用）

### 安装

```bash
# 后端
cd rare-dx
pip install -e ".[dev]"
cp .env.example .env  # 编辑填入 API keys

# 前端
cd frontend
npm install
```

### 启动

```bash
# 后端（端口 8765）
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8765

# 前端（端口 3001）
cd frontend && npm run dev -- -p 3001

# SSH 远程开发（本地终端执行）
ssh -L 3001:127.0.0.1:3001 -L 8765:127.0.0.1:8765 root@你的服务器地址
```

浏览器打开 `http://127.0.0.1:3001`

### 测试

```bash
# 全套
pytest tests/ --asyncio-mode=auto -q

# 单用例
pytest tests/test_d1_smoke.py -v
pytest tests/test_golden.py -v
```

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/diagnostic/stream` | SSE 流式诊断（6 层推理 + 证据推送） |
| GET | `/api/report/download` | 下载 DOCX/PDF 报告 |
| GET | `/api/sessions` | 历史会话列表（SQLite 持久化） |
| GET | `/api/sessions/{id}` | 某会话完整状态 |
| GET | `/api/sessions/{id}/audit` | 某会话审计日志 |
| DELETE | `/api/sessions/{id}` | 删除会话 |

## SSE 事件类型（12 种）

| 事件 | 说明 |
|------|------|
| `round_start` | 推理回合开始 |
| `agent_start` / `agent_delta` / `agent_done` | Agent 生命周期 |
| `phenotype_vector` | Layer 1 表型向量 |
| `hypothesis_ranking` | Layer 2 贝叶斯排序 |
| `temporal_match` | Layer 3 时序匹配 |
| `inheritance_pattern` | Layer 4 遗传模式 |
| `evoi_recommendation` | Layer 5 EVOI 路径 |
| `report_delta` | Layer 6 综合报告 |
| `evidence` | 逐层循证证据（含 DOI 跳转 URL）|
| `safety_valve` | 安全阈值触发事件 |
| `round_end` | 推理回合结束 |
| `error` | pipeline 异常 |

## 项目结构

```
rare-dx/
├── app/
│   ├── agents/           # 6 个推理 Agent（phenotype → report）
│   ├── reasoning/        # 算法层（bayesian / temporal / inheritance / evoi）
│   ├── tools/            # KnowS 客户端 / LLM 网关 / 证据分级 / 报告导出
│   ├── storage/          # SQLite 持久化存储（session + audit）
│   ├── models/           # Pydantic 数据模型
│   ├── api/              # FastAPI 路由 + SSE 端点 + 会话管理
│   ├── safety/           # 4 类安全阀 + 3 档闸门
│   └── audit/            # 审计日志
├── frontend/             # Next.js 14 + TypeScript
│   └── src/components/   # 9 组件 + EvidenceModal 证据弹窗
├── config/               # YAML 配置（LLM providers / 路径等）
├── data/                 # disease_meta.json / orphanet_freq.json / demo_cases/
│   ├── disease_meta.json    34 疾病元数据（罕见+常见）
│   └── hpo_frequency/
│       └── orphanet_freq.json  201 条 HPO 频率条目
├── docs/                 # PRD / ARCHITECTURE / API 文档
└── tests/                # 57+ 测试（含 golden 回归基线）
    ├── golden/           # D1/D2/D3 回归基线 expected.json
    └── test_golden.py    # 8 个 golden 回归测试
```

## 文档

- [PRD 需求文档](docs/PRD.md)
- [系统架构设计](docs/ARCHITECTURE.md)
- [技术设计书](docs/TECHNICAL_DESIGN.md)
- [API 接口文档](docs/API.md)

## 测试覆盖

```
57 passed, 2 skipped  in 13.86s

├── test_reasoning.py    15  算法层
├── test_agents.py        10  Agent 层
├── test_safety.py        12  安全机制
├── test_tools.py         8   工具层
├── test_graph.py         5   状态机
├── test_api_routes.py    9   API 集成
├── test_d1_smoke.py      3   D1/D2/D3 冒烟
└── test_golden.py        8   D1/D2/D3 回归基线
```

## 伦理安全

本系统遵循五铁律：
1. **禁止确诊**：不输出确诊结论，仅提供辅助推理
2. **医师为责任主体**：一切临床决策由签字执业医师做出
3. **拒绝优于编造**：无证据时明确告知，不虚构推理结果
4. **全链路审计不可关闭**：每一步推理均有日志记录
5. **原则凌驾一切**：安全机制优先级高于任何推理结果

## 免责声明

本系统仅供辅助参考，不构成临床诊断指令。一切临床决策的唯一责任主体是签字执业医师。
