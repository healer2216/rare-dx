# rare-dx · 罕见病诊断辅助系统

> 医学 AI 极客松项目 — 五层临床推理引擎 + 循证证据池 + 全量表型词典

---

## 1. 项目简介与医疗场景

- **一句话描述**：面向遗传科/儿科/内科执业医师的罕见病诊断辅助系统，将临床诊断推理过程形式化为五层递进分析。
- **解决的痛点**：
  - 罕见病文献检索效率低，医生难以快速获取多源循证证据
  - 表型-疾病映射复杂，依赖医生记忆和经验
  - 诊断过程缺乏结构化记录和可审计性
  - 鉴别诊断推理链不透明，难以复现和教学
- **目标受众**：遗传科/儿科/内科执业医师、医学研究员、罕见病诊疗中心

---

## 2. 功能特性

- **五层推理引擎**：模拟临床鉴别诊断的完整思维链（表型分析 → 贝叶斯假设 → 时序推理 → 遗传推理 → 诊断路径规划）
- **全量表型词典**：11,606 个 HPO 术语（频率表加载）+ LLM 语义匹配自动学习缓存
- **贝叶斯概率推理**：基于 Orphanet/OMIM 疾病-表型频率表的量化诊断，支持人口学先验修正
- **时序推理**：发病年龄、进展速度、症状序列作为诊断信号
- **遗传推理**：家系分析 + 孟德尔遗传模式推断 + 回流验证
- **诊断路径规划**：基于 EVOI（信息期望值）推荐最优下一步检查
- **循证证据集成**：KnowS 6 源医学证据检索（PubMed 英文/中文、指南、临床试验、药品说明书），每层推理均有文献支撑
- **证据弹窗系统**：每个推理节点右上角 `🅔 N` 徽标 → 点击弹出证据明细 → 有 DOI 的文献可跳转原文
- **安全机制**：4 类安全阀 + 3 档闸门（standard / relaxed / strict）+ 高风险升级 + 议题漂移检测
- **LLM 假设生成兜底**：Bayesian 无命中/低置信度时自动触发 LLM 生成候选疾病
- **词典学习缓存**：LLM 语义匹配的 term_name→hpo_id 自动持久化，逐步提升词典命中率
- **持久化存储**：SQLite 保存诊断会话 + 审计日志，支持历史回溯和报告导出

---

## 3. 魔搭社区运行/部署指南

### 魔搭展示链接

- [rare-dx · 罕见病诊断辅助系统](https://www.modelscope.cn/studios/zhangsan0226/rare-dx)

### 本地运行步骤

```bash
# 1. 克隆仓库
git clone https://www.modelscope.cn/studios/zhangsan0226/rare-dx.git
cd rare-dx

# 2. 安装依赖
pip install -e ".[dev]"

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，填入以下必需配置：
# - STEPFUN_API_KEY 或 DEEPSEEK_API_KEY（LLM 推理）
# - KNOWS_API_KEY + KNOWS_BASE_URL（循证检索）

# 4. 启动后端
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8765

# 5. 启动前端（新终端）
cd frontend && npm install && npm run dev -- -p 3001
```

### 访问应用

浏览器打开 `http://localhost:3001`

### 环境变量说明

| 变量 | 说明 | 必需 |
|------|------|------|
| `STEPFUN_API_KEY` | StepFun LLM API Key | 是 |
| `DEEPSEEK_API_KEY` | DeepSeek LLM API Key | 否（作为 fallback） |
| `KNOWS_API_KEY` | KnowS 循证检索 API Key | 是 |
| `KNOWS_BASE_URL` | KnowS 服务地址 | 否（默认 `https://api.nullht.com/v1`） |
| `OPENAI_API_KEY` | OpenAI API Key | 否（作为 fallback） |
| `QWEN_API_KEY` | 通义千问 API Key | 否（作为 fallback） |

---

## 4. 演示与输入输出示例

### 输入示例

```
男，3月龄，进行性肌张力低下，喂养困难，乳酸性酸中毒（血乳酸 5.2 mmol/L），眼球震颤
```

### 预期输出

系统将自动执行五层推理：

1. **Layer 1 · 表型分析**：提取 HPO 术语（如 `HP:0001324` 肌张力低下、`HP:0001945` 发热、`HP:0003251` 感觉异常等）
2. **Layer 2 · 假设生成**：基于贝叶斯推理生成 Top-5 候选疾病（如 Leigh 综合征 `ORPHA:520` 等）
3. **Layer 3 · 时序推理**：评估疾病自然史与患者发病年龄/进展模式的匹配度
4. **Layer 4 · 遗传推理**：推断孟德尔遗传模式，检查与候选疾病的兼容性
5. **Layer 5 · 路径规划**：基于 EVOI 推荐下一步检查（如线粒体基因组测序、血乳酸/丙酮酸比值等）
6. **Layer 6 · 报告综合**：生成结构化诊断辅助报告，包含证据引用和安全提示

### 运行结果截图

> **建议在此处附上 1-2 张运行结果截图，或演示视频链接**

---

## 5. 局限性与未来规划

### 目前版本存在的不足

1. **LLM 依赖外部 API**：推理质量依赖 StepFun/DeepSeek 等 LLM 服务，需要网络连接和 API Key
2. **知识库覆盖有限**：当前基于 Orphanet/OMIM 预置数据，对超罕见病或新发病种的覆盖不足
3. **证据源依赖第三方**：KnowS 循证检索依赖外部服务，可能存在限流或服务不可用情况
4. **无图像/影像分析**：当前仅支持文本输入，不支持医学影像（如 MRI、CT）的自动分析
5. **演示模式降级**：无 LLM 或低置信度时可能触发 conservative_downgrade，导致假设被清空
6. **家系分析简化**：当前遗传推理仅基于文本描述的家系信息，未支持标准 pedigree 图表输入

### 未来拟加入的新功能

1. **多模态输入**：支持上传医学影像、实验室报告、基因检测结果
2. **本地 LLM 支持**：集成 Ollama/llama.cpp 等本地模型，降低对外部 API 的依赖
3. **知识图谱增强**：与 Orphanet/OMIM/HGNC 等官方知识图谱直接对接，实时更新
4. **协作诊断**：支持多医生会诊模式，共享推理链和证据
5. **个性化患者画像**：整合患者历史诊疗数据，提供长期随访的疾病轨迹分析
6. **教育模式**：面向医学生的交互式教学模块，展示诊断推理过程

---

## 6. 团队与致谢

### 成员介绍及分工

| 成员 | 分工 |
|------|------|
| zhangsan0226 | 项目架构设计、五层推理引擎、贝叶斯概率计算、安全机制、全栈开发 |

### 致谢

感谢以下开源项目和数据集的贡献：

- [LangGraph](https://github.com/langchain-ai/langgraph) — 状态机工作流框架
- [FastAPI](https://fastapi.tiangolo.com/) — 高性能 Web 框架
- [Next.js](https://nextjs.org/) — React 全栈框架
- [Orphanet](https://www.orpha.net/) — 罕见病知识库（疾病-表型频率数据）
- [HPO](https://hpo.jax.org/) — 人类表型本体论
- [KnowS Evidence Search](https://api.nullht.com/v1) — 多源医学证据检索服务
- [shadcn/ui](https://ui.shadcn.com/) — UI 组件库

---

## 技术栈

| 层 | 技术 |
|---|------|
| 后端 | Python 3.12+ / FastAPI / LangGraph / Pydantic v2 |
| 前端 | Next.js 14 / TypeScript / Tailwind / shadcn/ui |
| LLM | DeepSeek-V3 / GPT-4o / Qwen / StepFun (`step-3.7-flash`) |
| 证据 | KnowS Evidence Search API（6 源：paper_en/paper_cn/guide/trial/meeting/package_insert） |
| 知识库 | HPO / Orphanet / OMIM（11,586 个 HPO 频率条目，12,958 疾病）|
| 存储 | SQLite（诊断会话 + 审计日志持久化）|

---

## 架构概览

```
用户输入 (临床描述)
  │
  ├─ [Safety]    议题漂移检测 / 高风险关键词 / 跨层冲突 / 保守降级
  │
  ├─ Layer 1: 表型分析器      → LLM NER(主力) + 全量词典(11,606 HPO) 兜底
  │    ├─ LLM≥5项: LLM为底座，词典补充遗漏
  │    └─ LLM<5项: 词典为底座，LLM补充
  │    └─ KnowS: Orphanet + HPO 检索
  │    └─ [学习缓存]  LLM提取的 term_name 自动持久化，逐步提升命中率
  ├─ Layer 2: 假设生成器      → 贝叶斯后验排序 Top-5
  │    ├─ 贝叶斯命中：LLM 鉴别诊断解释 + KnowS 检索
  │    └─ 贝叶斯无命中/低置信度：LLM 直接生成候选疾病假设
  │    └─ KnowS: PubMed + 中文期刊检索
  ├─ Layer 3: 时序推理器      → 发病年龄/进展模式匹配（兼容 LLM 假设）
  │    └─ KnowS: PubMed + MedlinePlus 检索
  ├─ Layer 4: 遗传推理器      → 孟德尔模式推断（兼容 LLM 假设）
  │    └─ KnowS: Orphanet + 指南检索
  ├─ Layer 5: 路径规划器      → EVOI 排序推荐检查（兼容 LLM 假设）
  │    └─ KnowS: ClinicalTrials + PubMed 检索
  │
  ├─ Layer 6: 报告综合器      → 结构化报告 + LLM 临床印象
  │
  └─ [Persist]  SQLite 保存会话 + 审计日志
```

---

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

---

## SSE 事件类型（14 种）

| 事件 | 说明 |
|------|------|
| `round_start` | 推理回合开始 |
| `agent_start` / `agent_delta` / `agent_done` | Agent 生命周期 |
| `phenotype_vector` | Layer 1 表型向量（含 metrics：LLM/词典/合并数量） |
| `hypothesis_ranking` | Layer 2 贝叶斯排序（含 LLM 兜底标注） |
| `temporal_match` | Layer 3 时序匹配 |
| `inheritance_pattern` | Layer 4 遗传模式 |
| `evoi_recommendation` | Layer 5 EVOI 路径 |
| `report_delta` | Layer 6 综合报告 |
| `evidence` | 逐层循证证据（含 DOI 跳转 URL）|
| `safety_valve` | 安全阈值触发事件 |
| `round_end` | 推理回合结束 |
| `error` | pipeline 异常 |

---

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
│   └── src/components/   # 11 组件 + EvidenceModal 证据弹窗
├── config/               # YAML 配置（LLM providers / 路径等）
├── data/                 # 全量表型词典 + 频率表 + 疾病元数据
│   ├── disease_meta.json          12,958 疾病元数据
│   ├── hpo_frequency/
│   │   └── orphanet_freq.json     267,633 条 HPO 频率条目
│   ├── hpo_dictionary.json         11,606 个 HPO 全量词典
│   └── hpo_learned_keywords.json   LLM 学习缓存（自动积累）
├── docs/                 # PRD / ARCHITECTURE / API 文档
├── .atomcode/
│   └── skills/           # AtomCode 子代理（安全审查/API文档/测试生成）
├── .env.example          # 配置模板（去敏）
├── .mcp.json             # MCP 服务（context7 + Playwright）
└── tests/                # 65+ 测试（含 golden 回归基线）
    ├── golden/           # D1/D2/D3 回归基线 expected.json
    └── test_golden.py    # 8 个 golden 回归测试
```

---

## 文档

- [PRD 需求文档](docs/PRD.md)
- [系统架构设计](docs/ARCHITECTURE.md)
- [技术设计书](docs/TECHNICAL_DESIGN.md)
- [API 接口文档](docs/API.md)

---

## 测试覆盖

```
65 passed, 0 failed, 2 skipped  in 102s

├── test_reasoning.py    15  算法层（含 min_posterior 阈值测试）
├── test_agents.py        10  Agent 层
├── test_safety.py        12  安全机制
├── test_tools.py         8   工具层
├── test_graph.py         5   状态机
├── test_api_routes.py    9   API 集成
├── test_d1_smoke.py      3   D1/D2/D3 冒烟
└── test_golden.py        8   D1/D2/D3 回归基线
```

---

## 伦理安全

本系统遵循五铁律：

1. **禁止确诊**：不输出确诊结论，仅提供辅助推理
2. **医师为责任主体**：一切临床决策由签字执业医师做出
3. **拒绝优于编造**：无证据时明确告知，不虚构推理结果
4. **全链路审计不可关闭**：每一步推理均有日志记录
5. **原则凌驾一切**：安全机制优先级高于任何推理结果

---

## 免责声明

本系统仅供辅助参考，不构成临床诊断指令。一切临床决策的唯一责任主体是签字执业医师。
