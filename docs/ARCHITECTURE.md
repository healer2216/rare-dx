# Rare-DX 系统架构说明书

> 罕见病鉴别诊断推理辅助系统 — 形式化临床诊断推理，而非简单证据检索

---

## 一、项目定位

### 1.1 应用场景

Rare-DX 面向 **罕见病鉴别诊断辅助** 场景。罕见病患者平均确诊周期 5-7 年，核心瓶颈不在"缺少文献"，而在"临床推理过程缺乏形式化支撑"。本系统通过 AI 驱动的多层递进推理引擎，将隐式的诊断思维过程显式化、结构化、可审计化。

### 1.2 产品形态

**多轮对话交互** + **五层递进推理** + **实时证据锚定**

- 对话面板：主诉录入 → 追问应答 → 补充信息 → 家系信息
- 推理可视化面板：表型雷达图 / 假设概率条 / 时序时间线 / 家系图 / 路径决策树
- 诊断报告面板：候选疾病排名 / 推理链路追溯 / 检查路径推荐 / 证据等级标注

### 1.3 核心价值

| 维度 | 说明 |
|------|------|
| **形式化推理** | 将临床诊断思维拆解为 5 层可计算、可审计的推理步骤 |
| **概率化输出** | 每个候选疾病附带后验概率与推理链路，而非黑箱结论 |
| **动态收敛** | 多轮对话中根据补充信息实时修订表型、重评估假设 |
| **循证锚定** | 每层推理嵌入 KnowS 证据检索，确保推理有据可查 |
| **决策支持** | 基于 EVOI 推荐最优下一步检查，量化信息价值 |

### 1.4 与 eb-consult 的区别

| 维度 | eb-consult | rare-dx |
|------|-----------|---------|
| 定位 | 循证参考报告生成 | 诊断推理辅助 |
| 核心问题 | "证据怎么说？" | "可能是什么病？" |
| 输入 | 临床问题 (PICO) | 表型谱 + 家系 + 时序 |
| 输出 | 结构化证据报告 | 排序假设 + 推理链路 |
| 推理深度 | 单层检索→综合 | 五层递进推理 |
| 交互模式 | 单轮问答 | 多轮对话 + 动态收敛 |
| 决策导向 | 提供证据参考 | 推荐检查路径 (EVOI) |

**eb-consult 回答"证据是什么"，rare-dx 回答"怎么推理出诊断"。**

---

## 二、五层推理引擎

### 2.1 引擎总览

```
┌─────────────────────────────────────────────────────────┐
│              五层推理引擎 (Reasoning Engine)              │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │ L5: 诊断路径规划 (Diagnostic Pathway Planning)    │  │
│  │ → EVOI 计算 → 最优检查序列推荐                    │  │
│  └──────────────────────┬────────────────────────────┘  │
│                         ↑↓ (回流)                        │
│  ┌──────────────────────┴────────────────────────────┐  │
│  │ L4: 遗传推理 (Genetic Inheritance Reasoning)      │  │
│  │ → 家系分析 → 遗传模式推断 → 疾病兼容性判定        │  │
│  └──────────────────────┬────────────────────────────┘  │
│                         ↑↓ (回流)                        │
│  ┌──────────────────────┴────────────────────────────┐  │
│  │ L3: 时序推理 (Temporal Reasoning)                 │  │
│  │ → 发病年龄 → 进展速度 → 症状序列匹配              │  │
│  └──────────────────────┬────────────────────────────┘  │
│                         ↑                                │
│  ┌──────────────────────┴────────────────────────────┐  │
│  │ L2: 假设生成 (Bayesian Hypothesis Generation)     │  │
│  │ → P(disease|phenotype) → 排序候选列表             │  │
│  └──────────────────────┬────────────────────────────┘  │
│                         ↑                                │
│  ┌──────────────────────┴────────────────────────────┐  │
│  │ L1: 表型分析 (Clinical Phenotype Deep Analysis)   │  │
│  │ → 多维表型向量 → HPO 注释 → PhenotypeProfile      │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 2.2 各层详细规格

| 层 | 名称 | 职责 | 输入 | 输出 |
|:--:|------|------|------|------|
| L1 | 表型深度分析 | 从自然语言提取结构化表型，构建多维表型向量（HPO 术语 + 修饰词 + 严重程度 + 时间特征） | 患者主诉 + 对话历史 + 补充检查 | `PhenotypeProfile`（多维表型向量 + HPO 注释集） |
| L2 | 贝叶斯假设生成 | 基于表型谱查询 Orphanet/OMIM 频率表，计算 P(disease\|phenotype)，生成排序候选列表 | `PhenotypeProfile` | `DiseaseHypothesis[]`（排序候选 + 后验概率 + 支持/反对证据） |
| L3 | 时序推理 | 评估假设与患者时序特征的匹配度：发病年龄、进展速度、症状出现顺序 | `PhenotypeProfile` + `DiseaseHypothesis[]` | `TemporalMatch[]`（时序一致性评分 + 自然史偏差分析） |
| L4 | 遗传推理 | 基于家系信息进行孟德尔遗传模式推断，评估各假设与遗传约束的兼容性 | `DiseaseHypothesis[]` + 家系数据 | `GeneticConstraint`（遗传模式 + 兼容/不兼容疾病列表） |
| L5 | 路径规划 (EVOI) | 计算每个候选检查的期望信息价值，推荐最优鉴别诊断路径 | 全部上游输出 | `DiagnosticPathway`（最优检查序列 + EVOI 评分 + 预期鉴别增益） |

---

## 三、整体架构图

```
┌═════════════════════════════════════════════════════════════════════┐
║                      展示层 (Next.js 14)                           ║
║  表型面板 │ 假设排名 │ 时序时间线 │ 家系图 │ 路径推荐 │ 证据卡 │ 报告 ║
╠═════════════════════════════════════════════════════════════════════╣
║                    API 路由层 (FastAPI + SSE)                       ║
║  /api/diagnostic/stream (核心SSE)  /api/diagnostic/start           ║
║  /api/diagnostic/round   /api/diagnostic/report  /api/session/*    ║
║  /api/evidence/search    /api/hpo/lookup         /api/health       ║
╠═════════════════════════════════════════════════════════════════════╣
║               推理引擎层 (5 Agents + Report Synthesizer)            ║
║  phenotype_analyzer → hypothesis_generator → temporal_reasoner     ║
║  → genetic_reasoner → pathway_planner → report_synthesizer         ║
╠═════════════════════════════════════════════════════════════════════╣
║                      推理计算层 (Computation)                       ║
║  bayesian.py │ temporal_logic.py │ inheritance.py │ evoi.py        ║
╠═════════════════════════════════════════════════════════════════════╣
║                      工具封装层 (Tool Adapters)                     ║
║  KnowSClient │ LLMGateway │ HPOClient │ DiseaseKB                  ║
╠═════════════════════════════════════════════════════════════════════╣
║                      外部依赖层 (External)                          ║
║  KnowS API │ LLM Providers │ HPO Ontology │ Orphanet/OMIM          ║
║  SqliteSaver (checkpoint) + JSON (audit)                           ║
╚═════════════════════════════════════════════════════════════════════╝
```

### 模块职责矩阵

| 模块 | 所属层 | 核心职责 | 关键依赖 |
|------|--------|----------|----------|
| phenotype_analyzer | 引擎层 | L1：表型提取与 HPO 注释 | LLMGateway, HPOClient |
| hypothesis_generator | 引擎层 | L2：贝叶斯后验计算 | DiseaseKB, KnowSClient |
| temporal_reasoner | 引擎层 | L3：时序一致性评估 | DiseaseKB, KnowSClient |
| genetic_reasoner | 引擎层 | L4：遗传模式推断 | LLMGateway, KnowSClient |
| pathway_planner | 引擎层 | L5：EVOI 检查路径规划 | KnowSClient, evoi.py |
| report_synthesizer | 引擎层 | 汇总推理 → 诊断报告 | 全部上游输出 |
| bayesian / temporal / inheritance / evoi | 计算层 | 贝叶斯·时序·孟德尔·EVOI 算法 | 静态频率表 + 家系数据 |
| KnowSClient / LLMGateway / HPOClient / DiseaseKB | 工具层 | 证据检索·LLM路由·HPO查询·疾病KB | 外部 API |

---

## 四、数据流图

### 4.1 链路 A：单次诊断

```
患者输入 (主诉 + 现病史 + 家系)
  │
  ▼
① 表型分析 (L1)
  自然语言 → HPO 注释 → 修饰词提取
  → KnowS(paper_en, paper_cn) 验证表型-疾病关联
  → PhenotypeProfile {hpo_terms[], modifiers[], severity[], onset_age}
  │
  ▼
② 假设生成 (L2)
  PhenotypeProfile → 频率表查表 → 贝叶斯后验
  → KnowS(paper) 检索流行病学数据校准频率
  → DiseaseHypothesis[] (按 P(disease|phenotype) 排序)
  │
  ▼
③ 时序推理 (L3)
  患者时序特征 × 各假设疾病自然史 → 匹配评分
  → KnowS(paper) 验证时序模式
  → TemporalMatch[] (时序一致性评分 + 偏差说明)
  │
  ▼
④ 遗传推理 (L4)
  家系数据 → 遗传模式推断 → 各假设兼容性判定
  → KnowS(paper) 确认遗传模式
  → GeneticConstraint {inferred_mode, compatible[], incompatible[]}
  │
  ▼
⑤ 路径规划 (L5)
  候选疾病集 × 可用检查 → EVOI 计算 → 最优序列
  → KnowS(guide + trial) 检查方法学证据
  → DiagnosticPathway {recommended_tests[], evoi_scores[]}
  │
  ▼
⑥ 报告合成 → 诊断报告 (候选排名 + 推理链路 + 检查建议 + 证据引用)
```

### 4.2 链路 B：多轮追问

```
补充信息 (新症状 / 检查结果 / 家系补充 / 修正)
  │
  ▼
① 信息解析与分类 → [新表型 | 检查结果 | 家系补充 | 修正]
  │
  ▼
② 表型修订 (L1 增量更新)
  PhenotypeProfile(prev) + 新信息 → PhenotypeProfile(new)
  → 修订标记: delta_phenotypes[]
  │
  ▼
③ 假设重评估 (L2 增量更新)
  PhenotypeProfile(new) → 重算后验 → 排名可能变化
  → 变化标记: rank_delta[]
  │
  ▼
④ 下游层联级更新: 时序重评估 → 遗传兼容性重评估 → 路径重新规划
  │
  ▼
⑤ 更新报告，标注本轮变化点
```

---

## 五、推理回流与边界

### 5.1 回流路径

```
┌──────┐     ┌──────┐     ┌──────┐     ┌──────┐     ┌──────┐
│  L1  │ ──→ │  L2  │ ──→ │  L3  │ ──→ │  L4  │ ──→ │  L5  │
│表型  │     │假设  │     │时序  │     │遗传  │     │路径  │
│分析  │ ←─────────────────────────────│推理  │     │规划  │
└──────┘  ↑  └──────┘     └──────┘     └──┬───┘     └──┬───┘
  ↑       │     回流 ①                      │            │
  │       └────────────────────────────────┘            │
  │       L4→L2: 遗传推理推翻假设                        │
  │                                                      │
  │       回流 ②                                         │
  └──────────────────────────────────────────────────────┘
          L5→L1: 检查结果显示新表型
  约束: 回流上限 2 轮，防止无限循环
```

### 5.2 回流规则

| 回流路径 | 触发条件 | 回流动作 | 终止条件 |
|----------|----------|----------|----------|
| **回流 ①** L4→L2 | 遗传推理推断 XR 模式，但 top-3 假设含 AD 疾病 | 不兼容疾病降级/移除，L2 重算后验 | 遗传模式与候选一致，或达 2 轮上限 |
| **回流 ②** L5→L1 | 推荐检查结果回报，揭示新表型 | 新表型注入 PhenotypeProfile，触发 L1→L5 链级更新 | 无新表型，或达 2 轮上限 |

```python
class ReflowController:
    max_reflow_rounds: int = 2
    current_reflow: int = 0

    def should_reflow(self, source: int, target: int) -> bool:
        if self.current_reflow >= self.max_reflow_rounds:
            return False
        if source == 4 and target == 2:
            return self._has_genetic_conflict()
        if source == 5 and target == 1:
            return self._has_new_phenotype_from_results()
        return False
```

---

## 六、诊断会话结构

### 6.1 DiagnosticSession 数据模型

```
DiagnosticSession
├── 会话标识: session_id, round, safety_gate
├── 患者画像: patient_profile {age, sex, ethnicity, family_history}
├── 五层推理持久状态
│   ├── phenotype_profile: PhenotypeProfile        # L1 输出
│   ├── hypotheses: List[DiseaseHypothesis]        # L2 输出
│   ├── temporal_matches: List[TemporalMatch]      # L3 输出
│   ├── genetic_constraint: GeneticConstraint       # L4 输出
│   └── diagnostic_pathway: DiagnosticPathway       # L5 输出
├── 证据池: evidence_pool {per_layer_evidence, evidence_stats}
├── 报告: report (DiagnosticReport)
├── 对话: dialog_history: List[DialogMessage]
├── 本轮临时工作区 (current_* fields)
│   ├── current_user_input: Optional[str]           # 本轮用户输入
│   ├── current_delta_phenotypes: List[PhenotypeDelta]  # 表型增量
│   ├── current_reflow_count: int = 0               # 回流计数
│   └── current_layer_status: Dict[str, str]        # 各层状态
└── 控制流: needs_reflow, reflow_source/target, safety_gate
```

### 6.2 LangGraph StateGraph 节点与边

```
START → intake_node → safety_check ─[拒绝]→ rejection_node → END
                              │[通过]
                              ▼
                    L1: phenotype_analyzer_node
                              ▼
                    L2: hypothesis_generator_node
                              ▼
                    L3: temporal_reasoner_node
                              ▼
                    L4: genetic_reasoner_node
                         ┌────┴──────┐
                    [无冲突]    [有冲突]→ reflow_42_node →(回 L2)
                         ▼
                    L5: pathway_planner_node
                         ┌────┴──────┐
                   [无新表型]  [有新表型]→ reflow_51_node →(回 L1)
                         ▼
                 report_synthesizer_node → END
```

---

## 七、安全机制

### 7.1 四道安全阀

| 安全阀 | 名称 | 触发条件 | 动作 |
|--------|------|----------|------|
| **阀 1** | 信息修订 | 用户提供修正信息 | 表型修订 → 假设重评估 → 报告更新 |
| **阀 2** | 议题漂移 | 用户输入与罕见病诊断无关 | 拒绝回答 + 引导回诊断话题 |
| **阀 3** | 跨层冲突 | 遗传推理结果与表型假设矛盾 | 触发回流机制，强制重评估冲突假设 |
| **阀 4** | 状态压缩 | 多轮对话历史超过 token 预算 | 历史摘要化，保留关键推理结论 |

### 7.2 保守降级策略

```
证据充足？
  ├── 是 → 正常输出假设排名 + 检查建议
  └── 否 → 降级模式
            ├── 证据极少 → "信息不足，建议补充以下表型/检查后再评估"
            └── 存在矛盾 → "当前信息存在矛盾，建议进一步澄清"

核心原则: 宁可不说，不可说错
```

### 7.3 三档安全闸门

| 闸门级别 | 适用场景 | 行为 |
|----------|----------|------|
| **strict** | 儿童/新生儿、多系统受累、危重表型 | 仅输出强证据假设；证据不足时拒绝输出；强制遗传咨询 |
| **standard** | 常规罕见病鉴别诊断 | 正常五层推理；中等证据即可输出；保守降级 |
| **relaxed** | 教学演示、科研探索、Hackathon Demo | 允许推测性假设；降低证据门槛；展示完整推理链路 |

---

## 八、证据等级体系

### 8.1 KnowS 六源 × 推理层嵌入矩阵

| 推理层 | paper_en | paper_cn | meeting | guide | trial | package_insert |
|--------|:--------:|:--------:|:-------:|:-----:|:-----:|:--------------:|
| L1 表型分析 | ★★★ | ★★ | — | — | — | — |
| L2 假设生成 | ★★★ | ★★ | — | — | — | — |
| L3 时序推理 | ★★ | ★ | — | — | — | — |
| L4 遗传推理 | ★★★ | ★ | — | — | — | — |
| L5 路径规划 | — | — | — | ★★★ | ★★ | ★ |

### 8.2 各层证据使用详情

| 推理层 | KnowS 源 | 检索目的 | 典型查询 |
|--------|----------|----------|----------|
| L1 | paper_en, paper_cn | 验证表型-疾病关联 | `{HPO_term} AND {disease_category}` |
| L2 | paper_en, paper_cn | 检索流行病学数据校准频率 | `{disease} prevalence OR incidence` |
| L3 | paper_en, paper_cn | 验证疾病自然史时序模式 | `{disease} natural history onset` |
| L4 | paper_en, paper_cn | 确认遗传模式、外显率 | `{disease} inheritance pattern` |
| L5 | guide, trial, package_insert | 检查方法学、诊断标准 | `{test} diagnostic sensitivity` |

### 8.3 证据分级标准

```
┌────────────────────────────────────────────────────────────┐
│  A 级 — 临床指南 (guide)              权重: 最高           │
│  B 级 — RCT / Meta 分析 (paper)       权重: 高             │
│  C 级 — 观察性研究 (paper)            权重: 中             │
│  D 级 — 会议摘要 / 在研试验 (meeting/trial)  权重: 低      │
│  E 级 — 药品说明书 (package_insert)   权重: 参考           │
│                                                            │
│  优先级: A > B > C > D > E                                 │
│  原则: 高等级证据可覆盖低等级；同等级按相关性排序          │
└────────────────────────────────────────────────────────────┘
```

---

## 九、技术栈

```
┌═════════════════════════════════════════════════════════════════════┐
║  前端:  Next.js 14 │ TypeScript │ Tailwind │ shadcn/ui │ Zustand  ║
║  后端:  Python 3.12+ │ FastAPI │ LangGraph │ Pydantic v2 │ Uvicorn║
║  LLM:   DeepSeek-V3 (默认) │ GPT-4o (critic) │ Qwen/StepFun (降) ║
║  证据:  KnowS API (api.nullht.com/v1) — 6 源                      ║
║  知识:  HPO Ontology (hp.obo) │ Orphanet 频率表 │ OMIM 数据库     ║
║  存储:  SqliteSaver (checkpoint) │ JSON (审计日志)                 ║
╚═════════════════════════════════════════════════════════════════════╝
```

### 技术选型说明

| 组件 | 选型 | 理由 |
|------|------|------|
| 推理编排 | LangGraph | 原生 StateGraph、条件边、checkpoint，适合多层推理 + 回流 |
| API 框架 | FastAPI | 原生 async/SSE、Pydantic v2 集成、自动 OpenAPI 文档 |
| 前端框架 | Next.js 14 | App Router、SSR/SSG 灵活切换 |
| UI 组件 | shadcn/ui | 可定制、基于 Radix + Tailwind |
| 状态管理 | Zustand | 轻量、无 boilerplate |
| 检查点 | SqliteSaver | LangGraph 原生支持、零配置、适合 Hackathon |
| 审计存储 | JSON 文件 | 简单直接、便于人工审查推理链路 |

### LLM 调用策略

| 推理层 | 默认模型 | 角色 | 备注 |
|--------|----------|------|------|
| L1-L5 + 报告 | DeepSeek-V3 | 结构化推理 | JSON Mode |
| 评审 (critic) | GPT-4o | 质量审核 | 可选 |
| Fallback | Qwen-Max → StepFun | 降级备用 | 主模型不可用时 |

降级链: **DeepSeek-V3 → Qwen-Max → StepFun → 拒绝服务**

---

## 十、关键架构决策 (ADR)

### ADR-001: 静态频率表 vs LLM 记忆

**决策**: 使用 Orphanet/OMIM 静态频率表进行贝叶斯计算，而非依赖 LLM 内部知识。
**原因**: LLM 对罕见病流行病学数据的记忆不可靠、不可审计、不可溯源。静态频率表确保每个概率数字都有据可查。覆盖范围有限（~7000 种罕见病）可通过定期更新弥补。
**否决**: 纯 LLM 记忆 — 不可审计、不可量化、幻觉风险高。

### ADR-002: EVOI 检查路径规划 vs 简单排序

**决策**: 使用 Expected Value of Information (EVOI) 框架推荐检查路径。
**原因**: EVOI 形式化了临床"下一步做什么"的决策 — 不仅考虑检查鉴别能力，还考虑当前不确定性分布、检查成本/风险、以及信息对决策的实际影响。
**否决**: 简单按鉴别力排序 — 忽略了检查之间的互补性和当前概率分布。

### ADR-003: HPO 作为通用表型语言

**决策**: 以 Human Phenotype Ontology (HPO) 作为全系统的通用表型表示语言。
**原因**: HPO 是跨数据库交叉引用的标准术语体系 — Orphanet、OMIM、DECIPHER 均使用 HPO 注释，支持结构化推理（is_a 关系等）。
**否决**: 自由文本表型描述 — 无法进行结构化推理和跨库查询。

### ADR-004: 五层串行 + 选择性回流

**决策**: 五层推理串行执行 + 两条选择性回流路径。
**原因**: 串行模拟临床推理的递进收敛过程（表型→假设→验证→决策），回流模拟专家发现矛盾时的回溯修正。回流上限 2 轮防止无限循环。
**否决**: 全并行（丢失层间依赖）/ 全迭代（每轮重跑 5 层，计算成本不可控）。

### ADR-005: KnowS 分层嵌入 vs 统一检索

**决策**: KnowS 证据检索在每层推理中按需嵌入，而非推理前统一检索。
**原因**: 每层需要不同类型的证据（L1/L2 需论文验证关联，L3 需自然史，L4 需遗传模式，L5 需指南/试验），分层嵌入使查询更精准。
**否决**: 统一检索 — 查询难以同时覆盖所有层需求，证据噪声大。

---

## 附录

### 术语表

| 术语 | 英文 | 说明 |
|------|------|------|
| HPO | Human Phenotype Ontology | 人类表型本体论，标准化表型术语体系 |
| EVOI | Expected Value of Information | 期望信息价值，量化检查对诊断决策的贡献 |
| KnowS | Knowledge Search | 医学循证检索 API (api.nullht.com) |
| Orphanet | — | 欧洲罕见病数据库 |
| OMIM | Online Mendelian Inheritance in Man | 人类孟德尔遗传数据库 |
| SSE | Server-Sent Events | 服务端推送事件 |

---

**文档版本**: v1.0
**最后更新**: 2025-07-02
**维护者**: Rare-DX 开发团队
