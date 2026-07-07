# rare-dx 罕见病诊断辅助系统 · 产品需求文档

| 项目代号 | 版本 | 日期 | 状态 |
|---------|------|------|------|
| rare-dx | v0.1.0 | 2026-03-12 | Draft for Hackathon |

---

## 第1章 系统定位与范围

### 1.1 一句话定位

面向遗传科/儿科/内科医师的罕见病诊断辅助系统——将临床诊断推理形式化为五层递进分析。

### 1.2 边界（做/不做）

| 维度 | 做 | 不做 |
|------|-----|------|
| 诊断责任 | 辅助医师推理、提供证据链 | 替代医师确诊、直接出具诊断报告 |
| 用户角色 | 执业医师（遗传科/儿科/内科） | 患者、家属、非医学背景人员 |
| 疾病范围 | Orphanet 收录的 ~7000 种罕见病 | 常见病、多发病、非罕见病 |
| 输出性质 | 鉴别诊断列表 + 证据强度 + 建议检查 | 确定性诊断结论 |
| 遗传咨询 | 提供遗传模式推理、家系分析辅助 | 替代遗传咨询师、提供生育建议 |
| 数据输入 | 医师手动录入表型、家系信息 | 自动对接 HIS/EMR 系统（MVP 不做） |
| 实时性 | 会话式交互、增量推理 | 持续监测患者状态变化 |

### 1.3 用户与场景

**唯一用户：执业医师**

- 遗传科医师：面对疑似遗传病患者，需要快速缩小鉴别诊断范围
- 儿科医师：儿童发育异常、多系统受累病例的病因排查
- 内科医师：成人罕见病（如代谢病、自身免疫病）的识别

**典型场景**

1. 医师接诊疑似罕见病患者，已收集部分临床信息
2. 启动 rare-dx 会话，输入表型描述（自由文本或结构化）
3. 系统五层推理引擎逐步分析，每层输出中间结论
4. 医师可补充信息、修正表型、质疑假设
5. 系统最终输出鉴别诊断列表 + 推荐检查路径

### 1.4 疾病范围

覆盖 Orphanet 收录的约 7000 种罕见病，核心数据来源：

- **Orphanet**: 疾病-表型关联、流行病学数据
- **OMIM**: 遗传模式、基因-疾病映射
- **HPO (Human Phenotype Ontology)**: 标准化表型术语

MVP 阶段优先覆盖：

- 线粒体病（~200 种）
- 遗传代谢病（~500 种）
- 神经发育障碍（~800 种）
- 罕见肾病（~150 种）

### 1.5 系统名

**rare-dx** (rare disease diagnosis)

---

## 第2章 第一原则·诊断辅助伦理约束（不可妥协）

> **本章优先级凌驾一切功能需求。任何实现若违反本章原则，视为 P0 缺陷，必须阻断发布。**

### 2.1 五条铁律

**原则 1：禁止确诊**

系统永远不得输出"该患者患有 X 病"等确定性诊断语句。唯一允许的输出形式：

- "X 病在鉴别诊断列表中，证据强度：[A/B/C/D/E]"
- "建议进行 Y 检查以验证/排除 X 假设"

**原则 2：医师为责任主体**

系统定位：认知辅助工具（cognitive aid），非决策主体。所有输出必须附带声明：

```
⚠️ 本系统输出仅供临床参考，不构成诊断意见。
最终诊断由接诊医师结合完整临床信息做出。
```

**原则 3：拒绝优于编造**

当证据不足、推理链断裂、或置信度低于阈值时，系统必须输出：

- "当前信息不足以支持可靠假设"
- "建议补充以下信息后再评估：[列表]"

**绝不**为了"看起来有用"而编造低质量假设。

**原则 4：全链路审计不可关闭**

每一轮推理的输入、中间状态、输出、证据引用必须完整记录，保留期 ≥ 5 年。审计日志不可由任何用户（包括管理员）删除或修改。

**原则 5：原则凌驾一切**

当性能优化、用户体验、开发效率与上述原则冲突时，原则优先。例如：

- 不得为了"响应更快"而跳过审计日志写入
- 不得为了"界面更简洁"而隐藏不确定性声明
- 不得为了"减少用户挫败感"而降低拒绝阈值

### 2.2 工程落点映射

| 原则 | 工程实现 | 验证方式 |
|------|---------|---------|
| 禁止确诊 | Prompt 模板硬编码禁止语句；输出后处理检测确定性措辞 | 单元测试：100 个病例输出不得包含"确诊""一定是"等词 |
| 医师为责任主体 | 所有输出页面强制渲染免责声明；API 响应包含 `disclaimer_required: true` 字段 | E2E 测试：检查每个输出页面是否包含声明 |
| 拒绝优于编造 | 置信度阈值硬编码（默认 0.3）；低于阈值触发拒绝逻辑 | 单元测试：构造低信息量输入，验证系统输出拒绝而非假设 |
| 全链路审计 | 每轮推理写入 `audit/{session_id}/round_{N}/` 目录；文件不可变（append-only） | 集成测试：验证审计文件存在且内容完整；渗透测试：验证无法删除 |
| 原则凌驾一切 | Code review checklist 包含伦理检查项；CI 包含伦理合规测试 | PR 模板包含伦理自检清单 |

---

## 第3章 五层推理引擎详细设计

### 3.1 Layer 1 - 临床表型深度分析

**职责**

从医师输入的自由文本或结构化数据中提取表型，构建多维表型向量（phenotype vector），而非简单的命名实体识别（NER）。

**输入**

- 医师输入的自由文本（如"患儿 3 月龄，进行性肌张力低下，乳酸性酸中毒"）
- 或结构化表型列表（HPO term + modifiers）

**输出**

```json
{
  "phenotype_vector": [
    {
      "hpo_id": "HP:0001252",
      "term": "Hypotonia",
      "modifiers": {
        "distribution": "generalized",
        "temporal_pattern": "progressive",
        "severity": "severe",
        "laterality": "bilateral",
        "progression_rate": "rapid"
      },
      "onset_age": "3 months"
    },
    {
      "hpo_id": "HP:0003128",
      "term": "Lactic acidosis",
      "modifiers": {
        "severity": "moderate",
        "temporal_pattern": "persistent"
      }
    }
  ]
}
```

**核心算法**

1. **表型提取**：基于 HPO 的 NER + 关系抽取（修饰符绑定）
2. **多维向量化**：每个表型附带 5 维修饰符（分布、时间模式、严重程度、侧别、进展速度）
3. **规范化**：映射到 HPO 标准术语，处理同义词

**临床意义**

表型修饰符是鉴别诊断的关键信号。例如：

- "肌张力低下" + "进行性" + "全身性" → 指向神经肌肉病或代谢病
- "肌张力低下" + "先天性" + "非进行性" → 指向先天性肌病

**KnowS 证据检索集成**

- **检索目标**：验证表型-HPO 映射的准确性；检索该表型组合的罕见病文献
- **检索源**：`paper_en` + `paper_cn` + `guide`
- **检索时机**：Layer 1 完成后，为 Layer 2 准备证据

---

### 3.2 Layer 2 - 贝叶斯假设生成

**职责**

基于表型向量，计算 P(disease | phenotype)，生成排序后的鉴别诊断列表。

**输入**

- Layer 1 输出的表型向量
- 疾病-表型频率表（来自 Orphanet/OMIM）
- 人口学先验（年龄、性别、地域）

**输出**

```json
{
  "hypotheses": [
    {
      "disease": "Leigh syndrome",
      "orphanet_id": "ORPHA:540",
      "posterior_prob": 0.42,
      "evidence_strength": "A",
      "supporting_phenotypes": ["HP:0001252", "HP:0003128"],
      "key_references": ["PMID:12345678"]
    },
    {
      "disease": "Pyruvate dehydrogenase deficiency",
      "orphanet_id": "ORPHA:289",
      "posterior_prob": 0.18,
      "evidence_strength": "B",
      "supporting_phenotypes": ["HP:0001252", "HP:0003128"],
      "key_references": ["PMID:23456789"]
    }
  ]
}
```

**核心算法**

贝叶斯定理：

```
P(disease | phenotype) ∝ P(phenotype | disease) × P(disease)
```

其中：

- `P(phenotype | disease)`：疾病-表型频率表（Orphanet 提供）
- `P(disease)`：人口学先验（罕见病患病率、年龄/性别分布）
- 多表型联合概率：假设条件独立（朴素贝叶斯简化）

**临床意义**

将"凭经验猜"转化为"基于证据的排序"，避免锚定偏差（anchoring bias）。

**KnowS 证据检索集成**

- **检索目标**：为 Top-5 假设检索支持/反对证据
- **检索源**：`paper_en` + `paper_cn` + `guide` + `package_insert`（药物说明书，排查禁忌）
- **检索时机**：Layer 2 完成后，为 Layer 3/4 准备

---

### 3.3 Layer 3 - 时序推理

**职责**

利用发病年龄、进展速度、症状序列作为诊断信号，匹配疾病特异性时序特征。

**输入**

- Layer 1 表型向量（含 `onset_age`, `progression_rate`）
- Layer 2 假设列表
- 疾病时序特征库（典型发病年龄、进展模式）

**输出**

```json
{
  "temporal_match": {
    "Leigh syndrome": {
      "match_score": 0.85,
      "typical_onset": "infancy (3-12 months)",
      "typical_progression": "rapid, episodic deterioration",
      "match_details": "发病年龄高度匹配；进展模式符合"
    },
    "Pyruvate dehydrogenase deficiency": {
      "match_score": 0.62,
      "typical_onset": "infancy or early childhood",
      "typical_progression": "variable, often progressive",
      "match_details": "发病年龄匹配；进展模式部分符合"
    }
  }
}
```

**核心算法**

1. **发病年龄匹配**：计算输入发病年龄与疾病典型发病年龄分布的相似度
2. **进展模式匹配**：比较输入进展速度与疾病典型进展模式
3. **症状序列匹配**：若输入包含症状出现顺序，与疾病典型序列比对

**临床意义**

时序是强鉴别信号。例如：

- Leigh 综合征：典型婴儿期起病，快速进展
- 肾上腺脑白质营养不良（X-ALD）：儿童期起病，逐步进展

**KnowS 证据检索集成**

- **检索目标**：检索疾病自然史（natural history）文献
- **检索源**：`paper_en` + `paper_cn` + `guide`
- **检索时机**：Layer 3 执行中

---

### 3.4 Layer 4 - 遗传推理

**职责**

基于家系信息推断遗传模式，作为强先验约束缩小鉴别诊断范围。

**输入**

- Layer 2 假设列表（含遗传模式标注）
- 家系信息（先证者、父母、兄弟姐妹患病情况）
- 或：无家系信息时，从表型推断可能的遗传模式

**输出**

```json
{
  "inheritance_inference": {
    "inferred_pattern": "mitochondrial",
    "confidence": 0.78,
    "evidence": [
      "母系遗传模式（先证者母亲携带相同突变）",
      "多系统受累（神经系统 + 代谢）"
    ],
    "constraint_on_hypotheses": {
      "Leigh syndrome": "compatible (mitochondrial inheritance)",
      "Pyruvate dehydrogenase deficiency": "less likely (X-linked, but no male bias in this case)"
    }
  }
}
```

**核心算法**

1. **家系模式识别**：根据家系患病模式推断遗传方式
   - 常染色体显性（AD）：垂直传递，男女均受累
   - 常染色体隐性（AR）：水平传递，同胞受累
   - X 连锁显性（XD）：女性患者传递给 50% 子女
   - X 连锁隐性（XR）：男性患者为主，女性携带者
   - 线粒体遗传：母系传递，所有子女可能受累
2. **遗传模式约束**：将推断的遗传模式作为先验，调整 Layer 2 假设的后验概率

**临床意义**

遗传模式是强约束信号。例如：

- 若推断为线粒体遗传 → Leigh 综合征概率上升
- 若推断为 XR → X-ALD 概率上升

**KnowS 证据检索集成**

- **检索目标**：验证疾病-遗传模式映射；检索新发现的遗传机制
- **检索源**：`paper_en` + `paper_cn` + `guide`
- **检索时机**：Layer 4 执行中

**回流机制**

若遗传推理结果与 Layer 2 假设冲突（如推断为 AR，但 Top-1 假设为 AD），触发回流：

- Layer 4 → Layer 2：重新计算后验概率，调整假设排序

---

### 3.5 Layer 5 - 诊断路径规划（EVOI）

**职责**

使用信息期望价值（Expected Value of Information, EVOI）推荐最优下一步检查。

**输入**

- Layer 2 假设列表（含后验概率）
- Layer 3/4 更新后的假设排序
- 检查项目库（基因检测、生化检测、影像学）的性能特征（灵敏度、特异度、成本、侵入性）

**输出**

```json
{
  "evoi_recommendation": {
    "recommended_test": "Mitochondrial genome sequencing (whole mtDNA)",
    "test_category": "genetic",
    "rationale": "最高 EVOI 评分：可区分 Leigh 综合征与其他线粒体病",
    "evoi_score": 0.82,
    "expected_cost": "moderate",
    "invasiveness": "low (blood sample)",
    "alternative_tests": [
      {
        "test": "Blood lactate and pyruvate ratio",
        "evoi_score": 0.45,
        "rationale": "辅助证据，但无法确诊"
      }
    ]
  }
}
```

**核心算法**

EVOI 计算：

```
EVOI(test) = Σ_d P(d) × [P(test_result | d) × U(correct_diagnosis) - U(current_best)]
```

其中：

- `P(d)`：疾病 d 的当前后验概率
- `P(test_result | d)`：疾病 d 下检查结果的条件概率
- `U(correct_diagnosis)`：正确诊断的效用（假设确诊后效用为 1）
- `U(current_best)`：当前最佳假设的效用

**临床意义**

避免"撒网式检查"，聚焦于信息量最大的检查，节省医疗资源、减少患者负担。

**KnowS 证据检索集成**

- **检索目标**：检索检查项目的诊断效能（灵敏度、特异度）文献
- **检索源**：`paper_en` + `paper_cn` + `guide` + `trial`（临床试验）
- **检索时机**：Layer 5 执行中

**回流机制**

若推荐的检查需要更详细的表型信息（如特定影像学特征），触发回流：

- Layer 5 → Layer 1：请求医师补充表型

---

## 第4章 KnowS 证据检索集成

### 4.1 证据在 5 层推理中的嵌入点

| 推理层 | 检索目标 | 检索源 | 为什么需要 |
|--------|---------|--------|-----------|
| Layer 1 | 表型-HPO 映射验证；表型组合的罕见病文献 | `paper_en`, `paper_cn`, `guide` | 确保表型提取准确；发现罕见表型组合的线索 |
| Layer 2 | Top-5 假设的支持/反对证据 | `paper_en`, `paper_cn`, `guide`, `package_insert` | 为贝叶斯计算提供先验；排查药物禁忌 |
| Layer 3 | 疾病自然史（natural history） | `paper_en`, `paper_cn`, `guide` | 验证时序匹配；发现亚型差异 |
| Layer 4 | 疾病-遗传模式映射；新发现的遗传机制 | `paper_en`, `paper_cn`, `guide` | 验证遗传推理；发现新遗传机制 |
| Layer 5 | 检查项目的诊断效能 | `paper_en`, `paper_cn`, `guide`, `trial` | 计算 EVOI；推荐最优检查 |

### 4.2 6 源检索策略

KnowS Evidence Search API 提供 6 个证据源：

| 源标识 | 内容 | 检索时机 | 优先级 |
|--------|------|---------|--------|
| `paper_en` | 英文论文（PubMed） | 所有层 | P0 |
| `paper_cn` | 中文论文（知网、万方） | 所有层 | P0 |
| `meeting` | 会议摘要 | Layer 2, 5 | P1 |
| `guide` | 临床指南 | 所有层 | P0 |
| `trial` | 临床试验 | Layer 5 | P1 |
| `package_insert` | 药物说明书 | Layer 2 | P1 |

**检索策略**

- **Layer 1**: `paper_en` + `paper_cn` + `guide`，关键词 = HPO terms
- **Layer 2**: `paper_en` + `paper_cn` + `guide` + `package_insert`，关键词 = 疾病名 + 表型
- **Layer 3**: `paper_en` + `paper_cn` + `guide`，关键词 = 疾病名 + "natural history"
- **Layer 4**: `paper_en` + `paper_cn` + `guide`，关键词 = 疾病名 + 遗传模式
- **Layer 5**: `paper_en` + `paper_cn` + `guide` + `trial`，关键词 = 检查项目名 + 疾病名

### 4.3 证据分级体系

| 等级 | 定义 | 来源 |
|------|------|------|
| A | 高质量指南或 Meta 分析 | `guide` |
| B | 原始研究（样本量 > 50） | `paper_en`, `paper_cn` |
| C | 病例系列或小样本研究 | `paper_en`, `paper_cn`, `meeting` |
| D | 专家意见或病例报告 | `paper_en`, `paper_cn`, `meeting` |
| E | 未经同行评审的预印本或会议摘要 | `meeting` |

**证据强度计算**

```
evidence_strength = weighted_sum(grade_i × count_i) / total_count
```

其中权重：A=5, B=4, C=3, D=2, E=1

### 4.4 证据-推理链溯源

每个假设必须附带证据链：

```json
{
  "hypothesis": "Leigh syndrome",
  "evidence_chain": [
    {
      "layer": 1,
      "phenotype": "HP:0001252 (Hypotonia)",
      "evidence": "PMID:12345678 (Grade A)"
    },
    {
      "layer": 2,
      "prior_probability": "1/40,000 (Orphanet)",
      "evidence": "ORPHA:540"
    },
    {
      "layer": 3,
      "temporal_match": "infancy onset, rapid progression",
      "evidence": "PMID:23456789 (Grade B)"
    },
    {
      "layer": 4,
      "inheritance_pattern": "mitochondrial",
      "evidence": "OMIM:256000"
    }
  ]
}
```

---

## 第5章 LangGraph 状态机

### 5.1 6 节点 StateGraph

```
┌─────────────┐
│  phenotype  │  Layer 1: 表型分析
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ hypothesis  │  Layer 2: 假设生成
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  temporal   │  Layer 3: 时序推理
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   genetic   │  Layer 4: 遗传推理
└──────┬──────┘
       │
       ├─────────────────────┐
       │                     │ (回流: genetic → hypothesis)
       │                     ▼
       │              ┌─────────────┐
       │              │ hypothesis  │  (重新排序)
       │              └──────┬──────┘
       │                     │
       │                     ▼
       │              ┌─────────────┐
       │              │  temporal   │  (重新匹配)
       │              └──────┬──────┘
       │                     │
       │                     └─────────────┐
       │                                   │
       ▼                                   │
┌─────────────┐                            │
│  pathway    │  Layer 5: 路径规划         │
└──────┬──────┘                            │
       │                                   │
       ├─────────────────────┐             │
       │                     │             │
       │ (回流: pathway → phenotype)       │
       ▼                     │             │
┌─────────────┐              │             │
│  phenotype  │  (补充表型)  │             │
└──────┬──────┘              │             │
       │                     │             │
       └─────────────────────┴─────────────┘
       │
       ▼
┌─────────────┐
│   report    │  生成最终报告
└─────────────┘
```

### 5.2 条件边与回流机制

**条件边定义**

```python
from langgraph.graph import StateGraph, END

workflow = StateGraph(DiagnosticSession)

# 主流程
workflow.add_edge("phenotype", "hypothesis")
workflow.add_edge("hypothesis", "temporal")
workflow.add_edge("temporal", "genetic")

# 条件边: genetic → hypothesis (回流)
workflow.add_conditional_edges(
    "genetic",
    should_return_to_hypothesis,
    {
        "return": "hypothesis",  # 遗传推理与假设冲突
        "continue": "pathway"
    }
)

# 条件边: pathway → phenotype (回流)
workflow.add_conditional_edges(
    "pathway",
    needs_additional_phenotype,
    {
        "return": "phenotype",  # 需要补充表型
        "continue": "report"
    }
)

workflow.add_edge("report", END)
```

**回流触发条件**

1. **genetic → hypothesis**: 遗传模式推断与 Top-1 假设不兼容（如推断为 AR，但 Top-1 为 AD）
2. **pathway → phenotype**: EVOI 推荐的检查需要更详细的表型信息（如特定影像学特征）

**回流次数限制**

- 单次会话最多 2 次回流（防止无限循环）
- 超过限制后强制进入 `report` 节点

### 5.3 Checkpoint 持久化

使用 `SqliteSaver` 持久化状态，支持会话恢复：

```python
from langgraph.checkpoint.sqlite import SqliteSaver

checkpoint = SqliteSaver.from_conn_string("checkpoints.db")
app = workflow.compile(checkpointer=checkpoint)
```

**持久化内容**

- 每层输入/输出
- 回流决策日志
- 医师交互记录
- 审计日志引用

---

## 第6章 诊断会话记忆结构

### 6.1 DiagnosticSession 顶层状态

```python
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime

class DiagnosticSession(BaseModel):
    session_id: str
    physician_id: str
    created_at: datetime
    updated_at: datetime
    
    # Layer 1 输出
    phenotype_vector: List[Phenotype] = Field(default_factory=list)
    
    # Layer 2 输出
    hypotheses: List[Hypothesis] = Field(default_factory=list)
    
    # Layer 3 输出
    temporal_match: Dict[str, TemporalMatch] = Field(default_factory=dict)
    
    # Layer 4 输出
    inheritance_inference: Optional[InheritanceInference] = None
    
    # Layer 5 输出
    evoi_recommendation: Optional[EvOIRecommendation] = None
    
    # 会话控制
    current_layer: int = 1
    return_count: int = 0  # 回流次数
    max_returns: int = 2
    
    # 医师交互
    physician_inputs: List[PhysicianInput] = Field(default_factory=list)
    physician_questions: List[str] = Field(default_factory=list)
    
    # 审计
    audit_log_path: str
    
    class Config:
        arbitrary_types_allowed = True
```

### 6.2 各 Agent 读写权限矩阵

| 状态字段 | phenotype agent | hypothesis agent | temporal agent | genetic agent | pathway agent | report agent |
|---------|----------------|------------------|----------------|---------------|---------------|--------------|
| `phenotype_vector` | R/W | R | R | R | R | R |
| `hypotheses` | - | R/W | R | R | R | R |
| `temporal_match` | - | - | R/W | R | R | R |
| `inheritance_inference` | - | - | - | R/W | R | R |
| `evoi_recommendation` | - | - | - | - | R/W | R |
| `current_layer` | R/W | R/W | R/W | R/W | R/W | R |
| `return_count` | R | R | R | R/W | R/W | R |
| `physician_inputs` | R | R | R | R | R | R |

### 6.3 多轮增量规则

**规则 1：表型增量**

医师可在任意轮次补充表型，系统重新执行 Layer 1 → Layer 5。

**规则 2：假设修订**

医师可质疑某个假设，系统降低其优先级或移除。

**规则 3：信息修订**

医师可修正先前输入的表型（如"进行性"改为"非进行性"），系统重新推理。

### 6.4 表型修订规则

**修订触发**

- 医师显式修正（"我之前说的 X 不对，应该是 Y"）
- 新检查结果推翻先前表型（如基因检测否定某表型）

**修订处理**

1. 记录修订历史（`phenotype_revision_log`）
2. 重新执行 Layer 1（更新表型向量）
3. 重新执行 Layer 2-5（增量推理）
4. 审计日志记录修订原因

---

## 第7章 安全机制

### 7.1 4 类安全阀

**安全阀 1：信息修订（Information Revision）**

- **触发**：医师修正先前输入的表型
- **处理**：重新推理 + 审计记录
- **输出**：明确告知"由于 X 信息修订，假设 Y 的优先级已调整"

**安全阀 2：议题漂移（Topic Drift）**

- **触发**：医师输入与罕见病诊断无关的内容（如"今天天气如何"）
- **处理**：拒绝响应 + 引导回诊断主题
- **输出**："本系统仅支持罕见病诊断辅助，请提供相关临床信息。"

**安全阀 3：跨层冲突（Cross-Layer Conflict）**

- **触发**：Layer N 输出与 Layer M (M < N) 输出矛盾
- **处理**：触发回流机制（见第 5 章）
- **输出**：明确告知冲突原因 + 调整后的假设排序

**安全阀 4：状态压缩（State Compression）**

- **触发**：会话轮次超过阈值（默认 10 轮）
- **处理**：压缩历史状态，保留关键信息
- **输出**：明确告知"由于会话过长，部分历史信息已压缩"

### 7.2 保守降级

**触发条件**

- 证据不足（Top-1 假设置信度 < 0.3）
- 推理链断裂（某层无法输出有效结果）
- 跨层冲突无法解决

**降级行为**

- 拒绝输出假设列表
- 输出"当前信息不足以支持可靠诊断，建议补充以下信息：[列表]"
- 审计日志记录降级原因

### 7.3 高风险场景

**场景识别**

- 遗传咨询（涉及生育决策）
- 产前诊断（涉及胎儿健康）
- 儿童患者（涉及未成年人）

**额外约束**

- 强制渲染免责声明（加大字号）
- 建议医师转诊遗传咨询师
- 审计日志标记为"高风险"

### 7.4 3 档安全闸门

| 档位 | 适用场景 | 置信度阈值 | 拒绝率 |
|------|---------|-----------|--------|
| `strict` | 产前诊断、儿童患者 | 0.5 | 高 |
| `standard` | 常规诊断（默认） | 0.3 | 中 |
| `relaxed` | 研究用途、教学演示 | 0.1 | 低 |

**档位切换**

- 默认 `standard`
- 医师可显式切换（需二次确认）
- 高风险场景强制 `strict`

---

## 第8章 SSE 协议与前端方案

### 8.1 SSE 事件类型

| 事件类型 | 描述 | 数据格式 |
|---------|------|---------|
| `round_start` | 新一轮推理开始 | `{"round": N}` |
| `agent_start` | Agent 开始执行 | `{"agent": "phenotype", "layer": 1}` |
| `agent_delta` | Agent 流式输出 | `{"delta": "..."}` |
| `agent_done` | Agent 执行完成 | `{"agent": "phenotype", "output": {...}}` |
| `phenotype_vector` | Layer 1 输出 | `{"phenotypes": [...]}` |
| `hypothesis_ranking` | Layer 2 输出 | `{"hypotheses": [...]}` |
| `temporal_match` | Layer 3 输出 | `{"matches": {...}}` |
| `inheritance_pattern` | Layer 4 输出 | `{"pattern": "...", "confidence": 0.78}` |
| `evoi_recommendation` | Layer 5 输出 | `{"test": "...", "evoi_score": 0.82}` |
| `evidence` | KnowS 检索结果 | `{"source": "paper_en", "references": [...]}` |
| `report_delta` | 最终报告流式输出 | `{"delta": "..."}` |
| `safety_valve` | 安全阀触发 | `{"type": "revision", "message": "..."}` |
| `heartbeat` | 心跳（每 15 秒） | `{}` |
| `round_end` | 一轮推理结束 | `{"round": N}` |
| `error` | 错误 | `{"code": "...", "message": "..."}` |

### 8.2 前端组件清单

**P0（MVP 必须）**

| 组件 | 描述 |
|------|------|
| `DiagnosticConsole` | 诊断控制台（主界面） |
| `PhenotypeInput` | 表型输入（自由文本 + 结构化） |
| `PhenotypeVectorDisplay` | 表型向量展示（含修饰符） |
| `HypothesisRanking` | 假设排序列表（含证据强度） |
| `EvidencePanel` | 证据面板（KnowS 检索结果） |
| `ReportView` | 最终报告视图 |
| `DisclaimerBanner` | 免责声明横幅（强制渲染） |

**P1（Hackathon 演示）**

| 组件 | 描述 |
|------|------|
| `TemporalMatchVisualization` | 时序匹配可视化 |
| `InheritancePatternDiagram` | 遗传模式图示 |
| `EvOIRecommendationCard` | EVOI 推荐卡片 |
| `SessionHistory` | 会话历史（多轮增量） |
| `AuditLogViewer` | 审计日志查看器（仅演示） |

### 8.3 设计取向

**主题：基因/医学质感深色主题**

- **主色调**：深蓝 (#0A1929) + 荧光青 (#00D9FF)
- **辅助色**：DNA 双螺旋渐变（紫 #8B5CF6 → 青 #00D9FF）
- **字体**：等宽字体（代码/数据） + 无衬线字体（正文）
- **视觉元素**：
  - 表型向量：节点图（node graph）
  - 假设排序：条形图（bar chart） + 证据链连线
  - 遗传模式：家系图（pedigree chart）
  - EVOI 推荐：决策树（decision tree）

---

## 第9章 演示剧本

### 9.1 D1（主剧本）：Leigh 综合征

**病例信息**

- 患者：男婴，3 月龄
- 主诉：进行性肌张力低下，喂养困难
- 现病史：出生后 2 月发现肌张力低下，逐渐加重；近期出现喂养困难、呕吐
- 查体：全身性肌张力低下，眼球震颤
- 辅助检查：血乳酸升高（5.2 mmol/L，正常 < 2.0）

**4 轮演示节奏**

**Round 1：表型分析（Layer 1）**

- 医师输入：自由文本（上述病例信息）
- 系统输出：表型向量
  - HP:0001252 (Hypotonia) + modifiers: generalized, progressive, severe
  - HP:0003128 (Lactic acidosis) + modifiers: moderate, persistent
  - HP:0001276 (Feeding difficulty) + modifiers: onset 2 months
  - HP:0000639 (Nystagmus) + modifiers: bilateral
- KnowS 检索：展示 2-3 篇相关文献

**Round 2：假设生成 + 时序推理（Layer 2 + 3）**

- 系统输出：Top-3 假设
  1. Leigh syndrome (posterior: 0.42, evidence: A)
  2. Pyruvate dehydrogenase deficiency (posterior: 0.18, evidence: B)
  3. Mitochondrial DNA depletion syndrome (posterior: 0.12, evidence: B)
- 时序匹配：Leigh 综合征发病年龄高度匹配（3 月龄 vs 典型 3-12 月）
- KnowS 检索：展示 Leigh 综合征自然史文献

**Round 3：遗传推理（Layer 4）**

- 医师补充：母亲健康，无家族史
- 系统输出：推断遗传模式为线粒体遗传（置信度 0.78）
  - 证据：多系统受累（神经 + 代谢）
  - 约束：Leigh 综合征兼容（线粒体遗传）
- 回流：无（遗传模式与 Top-1 假设兼容）

**Round 4：路径规划 + 报告（Layer 5 + Report）**

- 系统输出：EVOI 推荐
  - 推荐检查：线粒体基因组测序（whole mtDNA）
  - EVOI 评分：0.82
  - 理由：可区分 Leigh 综合征与其他线粒体病
- 最终报告：鉴别诊断列表 + 证据链 + 推荐检查

**答辩要点**

1. 五层推理的递进逻辑
2. 贝叶斯假设生成 vs 传统鉴别诊断
3. EVOI 的临床价值（避免撒网式检查）
4. 伦理约束（禁止确诊、医师为责任主体）

### 9.2 D2（备选）：Gitelman 综合征

**病例信息**

- 患者：女，12 岁
- 主诉：反复四肢无力，发作性低钾
- 现病史：近 1 年反复出现四肢无力，发作时血钾低（2.8 mmol/L）
- 辅助检查：代谢性碱中毒，尿钾升高，肾小管酸中毒

**演示重点**

- Layer 3 时序推理：儿童期起病，发作性
- Layer 5 EVOI：推荐基因检测（SLC12A3 基因）

### 9.3 D3（备选）：X-ALD

**病例信息**

- 患者：男，5 岁
- 主诉：发育倒退，行为异常
- 现病史：近 6 月出现学习能力下降，行为异常，步态不稳
- 查体：皮肤色素减退

**演示重点**

- Layer 4 遗传推理：XR 遗传模式（男性患者）
- Layer 5 EVOI：推荐 VLCFA（极长链脂肪酸）检测

---

## 第10章 审计日志规范

### 10.1 目录结构

```
audit/
└── {session_id}/
    ├── session_metadata.json      # 会话元数据
    ├── round_1/
    │   ├── input.json             # 医师输入
    │   ├── layer_1_output.json    # Layer 1 输出
    │   ├── layer_2_output.json    # Layer 2 输出
    │   ├── layer_3_output.json    # Layer 3 输出
    │   ├── layer_4_output.json    # Layer 4 输出
    │   ├── layer_5_output.json    # Layer 5 输出
    │   ├── knows_queries.json     # KnowS 检索记录
    │   ├── knows_results.json     # KnowS 检索结果
    │   └── safety_valves.json     # 安全阀触发记录
    ├── round_2/
    │   └── ...
    └── final_report.json          # 最终报告
```

### 10.2 写入规则

- **写入时机**：每层执行完成后立即写入
- **写入方式**：append-only（不可修改已写入内容）
- **写入内容**：完整输入/输出（不压缩、不省略）
- **写入失败处理**：重试 3 次；失败后阻断推理流程（原则 4）

### 10.3 保留期

- **保留期**：≥ 5 年（符合医疗记录法规）
- **存储介质**：持久化存储（非临时文件）
- **访问控制**：仅审计系统可读；医师可查看自己的会话；管理员不可删除

---

## 第11章 错误处理与降级

### 11.1 错误分类矩阵

| 错误类型 | 示例 | 处理策略 | 用户可见性 |
|---------|------|---------|-----------|
| 输入错误 | 表型格式错误 | 提示医师修正 | 可见 |
| 检索失败 | KnowS API 超时 | 重试 3 次；失败后跳过该源 | 可见（警告） |
| 推理失败 | 某层无法输出有效结果 | 保守降级（拒绝输出假设） | 可见 |
| 系统错误 | 数据库连接失败 | 阻断流程 + 记录审计日志 | 可见（错误） |
| 回流超限 | 回流次数 > 2 | 强制进入 report 节点 | 可见（警告） |

### 11.2 关键原则

1. **失败优于编造**：宁可拒绝输出，不可输出低质量结果
2. **透明优于隐藏**：错误信息对医师可见（不隐藏）
3. **审计优于性能**：审计日志写入失败时阻断流程（不跳过）

---

## 第12章 测试策略

### 12.1 测试金字塔

```
        ┌─────────────┐
        │   E2E 测试   │  10 个端到端场景
        ├─────────────┤
        │  集成测试     │  50 个集成场景
        ├─────────────┤
        │  单元测试     │  200 个单元测试
        └─────────────┘
```

**单元测试（200 个）**

- 表型提取准确率（HPO 映射）
- 贝叶斯计算正确性
- 时序匹配算法
- 遗传模式推断
- EVOI 计算

**集成测试（50 个）**

- 5 层推理端到端流程
- 回流机制触发与处理
- KnowS 检索集成
- 审计日志写入

**E2E 测试（10 个）**

- D1/D2/D3 演示剧本
- 多轮增量推理
- 表型修订
- 安全阀触发

### 12.2 诊断准确率回归集

**黄金标准集**

- 100 个已确诊罕见病病例（来自 Orphanet 案例库）
- 每个病例包含：表型、最终诊断、证据链

**回归测试**

- 每次代码变更后运行
- 指标：Top-3 命中率（最终诊断在 Top-3 假设中的比例）
- 阈值：Top-3 命中率 ≥ 70%

### 12.3 推理一致性测试

**测试目标**

验证相同输入产生相同输出（确定性推理）。

**测试方法**

- 固定随机种子
- 相同输入运行 10 次
- 验证输出一致性（假设排序、EVOI 评分）

---

## 第13章 里程碑与开发顺序

### 13.1 里程碑表

| 里程碑 | 描述 | 工作量 | 交付物 |
|--------|------|--------|--------|
| M0 | 项目初始化 | 0.5 天 | 代码仓库、CI/CD、基础架构 |
| M1 | Layer 1 表型分析 | 1.5 天 | 表型提取 + HPO 映射 + 多维向量化 |
| M2 | Layer 2 假设生成 | 2 天 | 贝叶斯计算 + 疾病-表型频率表 |
| M3 | Layer 3 时序推理 | 1 天 | 时序匹配算法 |
| M4 | Layer 4 遗传推理 | 1.5 天 | 遗传模式推断 + 回流机制 |
| M5 | Layer 5 路径规划 | 1.5 天 | EVOI 计算 + 检查推荐 |
| M6 | KnowS 集成 | 1.5 天 | 6 源检索 + 证据分级 |
| M7 | 前端开发 | 2 天 | P0 组件 + SSE 协议 |
| M8 | 集成测试 + 演示准备 | 2 天 | E2E 测试 + D1/D2/D3 剧本 |
| **总计** | | **14 天** | |

### 13.2 开发顺序

```
Week 1:
  Day 1: M0 (项目初始化)
  Day 2-3: M1 (Layer 1)
  Day 4-5: M2 (Layer 2)

Week 2:
  Day 6: M3 (Layer 3)
  Day 7-8: M4 (Layer 4)
  Day 9-10: M5 (Layer 5)

Week 3:
  Day 11-12: M6 (KnowS 集成)
  Day 13-14: M7 (前端开发)

Week 4:
  Day 15-16: M8 (集成测试 + 演示准备)
```

---

## 附录 A：关键术语表

| 术语 | 全称 | 定义 |
|------|------|------|
| HPO | Human Phenotype Ontology | 人类表型标准化术语本体 |
| Orphanet | 罕见病数据库 | 欧洲罕见病参考数据库 |
| OMIM | Online Mendelian Inheritance in Man | 人类孟德尔遗传在线数据库 |
| EVOI | Expected Value of Information | 信息期望价值 |
| Bayes | Bayesian inference | 贝叶斯推断 |
| SSE | Server-Sent Events | 服务器推送事件 |
| NER | Named Entity Recognition | 命名实体识别 |
| AD | Autosomal Dominant | 常染色体显性遗传 |
| AR | Autosomal Recessive | 常染色体隐性遗传 |
| XD | X-linked Dominant | X 连锁显性遗传 |
| XR | X-linked Recessive | X 连锁隐性遗传 |
| VLCFA | Very Long Chain Fatty Acids | 极长链脂肪酸 |
| X-ALD | X-linked Adrenoleukodystrophy | X 连锁肾上腺脑白质营养不良 |

---

## 附录 B：LLM 多供应商配置

```yaml
# config/llm_providers.yaml
providers:
  - name: openai
    model: gpt-4-turbo
    api_key: ${OPENAI_API_KEY}
    temperature: 0.3
    max_tokens: 2000
    
  - name: anthropic
    model: claude-3-opus
    api_key: ${ANTHROPIC_API_KEY}
    temperature: 0.3
    max_tokens: 2000
    
  - name: local
    model: llama-3-70b
    base_url: http://localhost:8080
    temperature: 0.3
    max_tokens: 2000

routing:
  layer_1: openai      # 表型分析需要强 NER 能力
  layer_2: openai      # 贝叶斯计算需要强推理能力
  layer_3: anthropic   # 时序推理
  layer_4: openai      # 遗传推理
  layer_5: openai      # EVOI 计算
  report: anthropic    # 报告生成需要强语言能力
```

---

## 附录 C：疾病-表型频率表数据来源

**数据来源**

1. **Orphanet**: 疾病-表型关联（频率标注：非常常见、常见、偶见、罕见）
2. **OMIM**: 基因-疾病-表型映射
3. **文献挖掘**: 从 PubMed 摘要中提取表型频率

**频率量化**

| Orphanet 标注 | 量化频率 | 用途 |
|--------------|---------|------|
| 非常常见 (Very frequent) | 0.9 | P(phenotype \| disease) |
| 常见 (Frequent) | 0.5 | P(phenotype \| disease) |
| 偶见 (Occasional) | 0.1 | P(phenotype \| disease) |
| 罕见 (Rare) | 0.01 | P(phenotype \| disease) |

**数据更新**

- 频率表每季度更新一次
- 更新来源：Orphanet/OMIM 官方发布 + 新文献挖掘

---

**文档结束**

*本 PRD 为 rare-dx 项目的完整技术规范，适用于 Hackathon 开发参考。*
