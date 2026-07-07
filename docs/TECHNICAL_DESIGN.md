# rare-dx 技术设计书

> 罕见病诊断辅助系统 · Technical Design Document
> 版本: v0.1.0 · 最后更新: 2025-07-15

---

## 目录

1. [系统架构总览](#1-系统架构总览)
2. [数据模型设计](#2-数据模型设计)
3. [推理引擎模块设计](#3-推理引擎模块设计)
4. [Agent 详细设计](#4-agent-详细设计)
5. [LangGraph 状态机](#5-langgraph-状态机)
6. [KnowS 证据检索集成](#6-knows-证据检索集成)
7. [LLM Gateway](#7-llm-gateway)
8. [安全机制](#8-安全机制)
9. [前端组件设计](#9-前端组件设计)
10. [配置管理](#10-配置管理)

---

## 1. 系统架构总览

### 1.1 分层架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                     展示层 (Next.js 14)                         │
│  PhenotypePanel │ HypothesisRanking │ TemporalTimeline │ ...    │
│  PedigreeViewer │ PathwayRecommendation │ DiagnosticReport      │
│  DiagnosticStream (SSE 实时渲染)                                │
├─────────────────────────────────────────────────────────────────┤
│                  API 路由层 (FastAPI + SSE)                      │
│  POST /api/chat          ─ 用户消息入口                          │
│  GET  /api/chat/stream   ─ SSE 事件流 (text/event-stream)       │
│  POST /api/session       ─ 会话管理                             │
├─────────────────────────────────────────────────────────────────┤
│              推理引擎层 (LangGraph StateGraph)                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │Phenotype │→│Hypothesis│→│ Temporal │→│ Genetic  │          │
│  │ Analyzer │ │Generator │ │ Reasoner │ │ Reasoner │          │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
│  ┌──────────┐ ┌──────────────┐                                │
│  │ Pathway  │→│   Report     │  ← 回溯边 (max 2 iterations)   │
│  │ Planner  │ │  Synthesizer │                                │
│  └──────────┘ └──────────────┘                                │
├─────────────────────────────────────────────────────────────────┤
│                   推理计算层 (Pure Python)                       │
│  bayesian.py │ temporal_logic.py │ inheritance.py │ evoi.py     │
├─────────────────────────────────────────────────────────────────┤
│                   工具封装层 (Tool Wrappers)                     │
│  KnowsClient │ LLMGateway │ HPOService │ DiseaseKBClient       │
├─────────────────────────────────────────────────────────────────┤
│                   外部依赖层                                     │
│  KnowS API │ DeepSeek/OpenAI/Qwen │ Orphanet │ OMIM │ HPO DB   │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 两条核心链路

**链路 A: 单次诊断 (Single-pass Diagnosis)**

```
user_message
  → PhenotypeAnalyzer (Layer 1: 表型提取 → PhenotypeProfile)
  → HypothesisGenerator (Layer 2: 贝叶斯评分 → DiseaseHypothesis[])
  → TemporalReasoner (Layer 3: 时序匹配 → TemporalMatch[])
  → GeneticReasoner (Layer 4: 遗传约束 → GeneticConstraint)
  → PathwayPlanner (Layer 5: EVOI 排序 → DiagnosticPathway)
  → ReportSynthesizer (最终报告 → Report)
```

**链路 B: 多轮追问 (Follow-up Refinement)**

```
supplement_info
  → PhenotypeAnalyzer (表型修订 → PhenotypeProfile_rev)
  → HypothesisGenerator (假设重评估 → DiseaseHypothesis[]_rev)
  → [条件] 新增表型 → 重新走 Layer 3-5
  → [条件] 信息修正 → 仅更新受影响的 hypothesis
  → ReportSynthesizer (增量更新 → Report_rev)
```

**请求流程序列图:**

```
用户          前端            FastAPI         LangGraph        KnowS API
 │            │               │               │               │
 │─ 输入症状 ─→│               │               │               │
 │            │── POST /chat ─→│               │               │
 │            │               │── invoke ─────→│               │
 │            │               │               │── search ─────→│
 │            │               │               │←── results ────│
 │            │               │               │── compute ──→  │
 │            │←── SSE event ─│←── yield ─────│               │
 │←─ 实时渲染 ─│               │               │               │
 │            │               │               │── compute ──→  │
 │            │←── SSE event ─│←── yield ─────│               │
 │←─ 假设列表 ─│               │               │               │
 │            │               │               │── ... ──→      │
 │            │←── SSE event ─│←── yield ─────│               │
 │←─ 诊断报告 ─│               │               │               │
```

---

## 2. 数据模型设计（完整 Pydantic 定义）

### 2.1 枚举类型

```python
from enum import Enum

class EvidenceSource(str, Enum):
    PAPER_EN = "paper_en"           # 英文论文
    PAPER_CN = "paper_cn"           # 中文论文
    MEETING = "meeting"             # 会议摘要
    GUIDE = "guide"                 # 临床指南
    TRIAL = "trial"                 # 临床试验
    PACKAGE_INSERT = "package_insert"  # 药品说明书

class EvidenceGrade(str, Enum):
    A = "A"   # 高质量 RCT / Meta-analysis
    B = "B"   # 队列研究 / 病例对照
    C = "C"   # 病例报告 / 病例系列
    D = "D"   # 专家意见
    E = "E"   # 经验性证据

class HPODomain(str, Enum):
    HP = "HP"   # Human Phenotype Ontology
    MP = "MP"   # Mammalian Phenotype
    UP = "UP"   # Upper-level ontology category

class InheritanceMode(str, Enum):
    AD = "AD"                 # 常染色体显性
    AR = "AR"                 # 常染色体隐性
    XD = "XD"                 # X-连锁显性
    XR = "XR"                 # X-连锁隐性
    MITOCHONDRIAL = "MITOCHONDRIAL"  # 线粒体遗传
    DE_NOVO = "DE_NOVO"       # 新发突变
    UNKNOWN = "UNKNOWN"

class TemporalPattern(str, Enum):
    ACUTE = "acute"                     # 急性
    SUBACUTE = "subacute"               # 亚急性
    CHRONIC_PROGRESSIVE = "chronic_progressive"  # 慢性进展
    CHRONIC_STATIC = "chronic_static"   # 慢性稳定
    FLUCTUATING = "fluctuating"         # 波动性
    RELAPSING = "relapsing"             # 复发性

class SeverityLevel(str, Enum):
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"
    LIFE_THREATENING = "life_threatening"

class DiagnosticIntent(str, Enum):
    NEW_DIAGNOSIS = "new_diagnosis"     # 首次诊断
    FOLLOWUP = "followup"               # 随访补充
    INFO_REVISE = "info_revise"         # 信息修正
    TOPIC_DRIFT = "topic_drift"         # 话题偏移（非诊断相关）

class PresenceStatus(str, Enum):
    PRESENT = "present"
    ABSENT = "absent"
    UNKNOWN = "unknown"

class Laterality(str, Enum):
    BILATERAL = "bilateral"
    UNILATERAL = "unilateral"
    LEFT = "left"
    RIGHT = "right"

class TestCategory(str, Enum):
    GENETIC = "genetic"
    BIOCHEMICAL = "biochemical"
    IMAGING = "imaging"
    FUNCTIONAL = "functional"
    HISTOPATHOLOGICAL = "histopathological"

class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class AffectedStatus(str, Enum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"
```

### 2.2 Layer 1 模型 — 临床表型深度分析

```python
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class PhenotypeModifier(BaseModel):
    """表型修饰符 — 描述单一表型的多维特征"""
    distribution: Optional[str] = Field(
        None, description="分布模式: proximal/distal/systemic")
    temporal_pattern: Optional[TemporalPattern] = None
    severity: Optional[SeverityLevel] = None
    laterality: Optional[Laterality] = None
    progression_rate: Optional[str] = Field(
        None, description="进展速度描述: rapid/slow/stable")
    aggravating_factors: list[str] = Field(
        default_factory=list, description="加重因素")
    relieving_factors: list[str] = Field(
        default_factory=list, description="缓解因素")

class PhenotypeVector(BaseModel):
    """表型向量 — 单个表型的完整结构化表示"""
    hpo_id: str = Field(..., pattern=r"^HP:\d{7}$",
                        description="HPO 标准术语 ID")
    term_name: str = Field(..., description="HPO 术语名称")
    modifiers: list[PhenotypeModifier] = Field(default_factory=list)
    presence: PresenceStatus = PresenceStatus.PRESENT
    onset_age: Optional[float] = Field(None, description="发病年龄数值")
    onset_age_unit: Optional[str] = Field(
        None, description="年龄单位: years/months/days/weeks")
    severity_level: Optional[SeverityLevel] = None
    raw_description: Optional[str] = Field(
        None, description="原始文本描述")

class Demographic(BaseModel):
    """患者人口统计学信息"""
    age: Optional[float] = None
    age_unit: str = "years"
    sex: Optional[str] = Field(None, pattern=r"^(male|female|unknown)$")
    ethnicity: Optional[str] = None
    region: Optional[str] = None

class PhenotypeProfile(BaseModel):
    """表型档案 — Layer 1 的完整输出"""
    patient_id: str
    vectors: list[PhenotypeVector] = Field(default_factory=list)
    raw_text: str = Field(..., description="原始主诉文本")
    parsed_at: datetime = Field(default_factory=datetime.utcnow)
    demographic: Demographic = Field(default_factory=Demographic)
```

### 2.3 Layer 2 模型 — 贝叶斯假设生成

```python
class DiseaseFrequency(BaseModel):
    """疾病-表型频率表条目 (来自 Orphanet / OMIM)"""
    disease_id: str
    disease_name: str
    phenotype_hpo_id: str
    frequency: float = Field(..., ge=0.0, le=1.0,
                             description="该表型在该疾病中的出现频率")
    source: str = Field(..., description="数据来源: Orphanet / OMIM")

class DemographicPrior(BaseModel):
    """人口学先验修正"""
    age_group: Optional[str] = None     # pediatric / adult / elderly
    sex: Optional[str] = None
    ethnicity: Optional[str] = None
    region: Optional[str] = None
    prevalence_modifier: float = Field(
        1.0, ge=0.01, le=100.0,
        description="患病率修正系数")

class BayesianScore(BaseModel):
    """单疾病贝叶斯评分"""
    disease_id: str
    prior_probability: float = Field(..., ge=0.0, le=1.0)
    likelihood: float = Field(..., ge=0.0)
    posterior_probability: float = Field(..., ge=0.0, le=1.0)
    log_odds: float = Field(..., description="log2(posterior / (1-posterior))")
    supporting_phenotype_ids: list[str] = Field(default_factory=list)
    contradicting_phenotype_ids: list[str] = Field(default_factory=list)

class DiseaseHypothesis(BaseModel):
    """疾病假设 — Layer 2 的核心输出"""
    disease_id: str
    disease_name: str
    orpha_number: Optional[str] = None
    bayesian_score: BayesianScore
    supporting_phenotypes: list[str] = Field(default_factory=list)
    contradicting_phenotypes: list[str] = Field(default_factory=list)
    rank: int = Field(..., ge=1)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0,
                              description="综合置信度")
    reasoning_chain: str = Field(
        ..., description="推理链自然语言摘要")
```

### 2.4 Layer 3 模型 — 时序推理

```python
class OnsetProfile(BaseModel):
    """疾病典型发病年龄画像"""
    typical_age_range: tuple[float, float] = Field(
        ..., description="(最小, 最大) 典型发病年龄")
    age_unit: str = "years"
    variability: float = Field(
        0.2, ge=0.0, le=1.0,
        description="变异度: 0=严格, 1=宽泛")

class ProgressionPattern(BaseModel):
    """疾病进展模式"""
    speed: TemporalPattern = Field(
        ..., description="进展速度类型")
    trajectory: str = Field(
        ..., description="轨迹: improving/stable/worsening/fluctuating")

class TemporalMatch(BaseModel):
    """时序匹配结果"""
    disease_id: str
    onset_consistency: float = Field(
        ..., ge=0.0, le=1.0, description="发病年龄一致性")
    progression_consistency: float = Field(
        ..., ge=0.0, le=1.0, description="进展模式一致性")
    sequence_consistency: float = Field(
        ..., ge=0.0, le=1.0, description="症状序列一致性")
    overall_temporal_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="综合时序得分 = weighted_avg(onset, progression, sequence)")
    notes: str = ""
```

### 2.5 Layer 4 模型 — 遗传推理

```python
class FamilyMember(BaseModel):
    """家系成员"""
    id: str
    relationship: str = Field(
        ..., description="与先证者关系: father/mother/sibling/child/...")
    phenotype_hpo_ids: list[str] = Field(default_factory=list)
    affected_status: AffectedStatus = AffectedStatus.UNKNOWN
    carrier_status: AffectedStatus = AffectedStatus.UNKNOWN
    age: Optional[float] = None
    sex: Optional[str] = None

class Pedigree(BaseModel):
    """家系图"""
    proband_id: str
    members: list[FamilyMember] = Field(default_factory=list)
    consanguinity: bool = Field(False, description="是否存在近亲婚配")
    generations: int = Field(..., ge=1, description="记录代数")

class InheritancePattern(BaseModel):
    """推断的遗传模式"""
    mode: InheritanceMode
    confidence: float = Field(..., ge=0.0, le=1.0)
    supporting_evidence: list[str] = Field(default_factory=list)

class GeneticConstraint(BaseModel):
    """遗传约束 — Layer 4 输出"""
    inheritance_patterns: list[InheritancePattern] = Field(
        default_factory=list)
    compatible_diseases: list[str] = Field(
        default_factory=list, description="遗传模式兼容的疾病 ID 列表")
    incompatible_diseases: list[str] = Field(
        default_factory=list, description="遗传模式不兼容的疾病 ID 列表")
    prior_modifier: float = Field(
        1.0, ge=0.0, le=10.0,
        description="对贝叶斯先验的修正系数")
```

### 2.6 Layer 5 模型 — 诊断路径规划 (EVOI)

```python
class DiagnosticTest(BaseModel):
    """诊断检查项目"""
    test_id: str
    test_name: str
    category: TestCategory
    sensitivity: float = Field(..., ge=0.0, le=1.0)
    specificity: float = Field(..., ge=0.0, le=1.0)
    risk_level: RiskLevel = RiskLevel.LOW
    cost_tier: int = Field(..., ge=1, le=5, description="费用等级 1-5")
    turnaround_time_days: int = Field(..., ge=0)
    description: str = ""

class EVOIScore(BaseModel):
    """信息价值评分"""
    test_id: str
    information_gain: float = Field(
        ..., ge=0.0, le=1.0, description="信息增益")
    risk_cost_penalty: float = Field(
        ..., ge=0.0, description="风险-成本惩罚")
    net_evoi: float = Field(
        ..., description="净信息价值 = information_gain - risk_cost_penalty")
    rank: int = Field(..., ge=1)

class PathwayStep(BaseModel):
    """诊断路径单步"""
    test_id: str
    evoi_score: EVOIScore
    rationale: str = Field(..., description="推荐该检查的理由")
    expected_outcomes: list[str] = Field(default_factory=list)
    alternative_tests: list[str] = Field(default_factory=list)

class DiagnosticPathway(BaseModel):
    """诊断路径 — Layer 5 输出"""
    steps: list[PathwayStep] = Field(default_factory=list)
    current_step: int = Field(0, ge=0)
    total_expected_information_gain: float = Field(
        0.0, ge=0.0, description="路径总信息增益")
```

### 2.7 证据模型

```python
class Evidence(BaseModel):
    """单条证据"""
    id: str
    source: EvidenceSource
    title: str
    abstract: Optional[str] = None
    publish_date: Optional[str] = None
    organizations: list[str] = Field(default_factory=list)
    has_pdf: bool = False
    doi: Optional[str] = None
    journal: Optional[str] = None
    study_type: Optional[str] = None
    impact_factor: Optional[float] = None
    retrieved_layer: str = Field(
        ..., description="检索该证据的推理层: layer1/layer2/...")
    relevance_score: float = Field(..., ge=0.0, le=1.0)
    grade: EvidenceGrade = EvidenceGrade.D

class EvidencePool(BaseModel):
    """证据池 — 全链路证据汇总"""
    evidences: dict[str, Evidence] = Field(default_factory=dict)

    def add(self, evidence: Evidence) -> None:
        if evidence.id not in self.evidences:
            self.evidences[evidence.id] = evidence

    def all(self) -> list[Evidence]:
        return list(self.evidences.values())

    def by_layer(self, layer: str) -> list[Evidence]:
        return [e for e in self.evidences.values()
                if e.retrieved_layer == layer]

    def by_grade(self, grade: EvidenceGrade) -> list[Evidence]:
        return [e for e in self.evidences.values()
                if e.grade == grade]
```

### 2.8 会话模型

```python
class Turn(BaseModel):
    """单轮对话"""
    round: int
    user_message: str
    intent: DiagnosticIntent
    layer_outputs: dict = Field(default_factory=dict)
    new_evidence_ids: list[str] = Field(default_factory=list)
    updated_hypothesis_ids: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class Report(BaseModel):
    """诊断报告"""
    main_text: str = ""
    summary_snapshot: str = ""
    reasoning_summary: str = ""
    evidence_citations: list[str] = Field(default_factory=list)
    uncertainty_notes: str = ""
    last_updated_round: int = 0

class DiagnosticSession(BaseModel):
    """诊断会话 — LangGraph 全局状态"""
    session_id: str
    round: int = 0
    patient_profile: Optional[Demographic] = None
    phenotype_profile: Optional[PhenotypeProfile] = None
    hypotheses: list[DiseaseHypothesis] = Field(default_factory=list)
    temporal_matches: list[TemporalMatch] = Field(default_factory=list)
    genetic_constraint: Optional[GeneticConstraint] = None
    diagnostic_pathway: Optional[DiagnosticPathway] = None
    evidence_pool: EvidencePool = Field(default_factory=EvidencePool)
    report: Report = Field(default_factory=Report)
    dialog_history: list[Turn] = Field(default_factory=list)
    # 当前轮次工作区
    current_phenotype: Optional[PhenotypeProfile] = None
    current_hypotheses: list[DiseaseHypothesis] = Field(default_factory=list)
    current_temporal: list[TemporalMatch] = Field(default_factory=list)
    current_genetic: Optional[GeneticConstraint] = None
    current_pathway: Optional[DiagnosticPathway] = None
    # 回溯控制
    backflow_count: int = Field(0, ge=0)
    max_backflow: int = 2
    # 安全等级
    safety_level: str = "normal"
```

---

## 3. 推理引擎模块设计

### 3.1 贝叶斯计算引擎 (`reasoning/bayesian.py`)

```python
import json
import math
from pathlib import Path
from typing import Optional

FREQ_TABLE_PATH = Path("data/hpo_frequency/orphanet_freq.json")

def load_frequency_table() -> dict[str, dict[str, float]]:
    """加载 HPO-疾病频率表 → {disease_id: {hpo_id: frequency}}"""
    with open(FREQ_TABLE_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    table: dict[str, dict[str, float]] = {}
    for entry in raw:
        did = entry["disease_id"]
        table.setdefault(did, {})[entry["hpo_id"]] = entry["frequency"]
    return table

def compute_prior(
    disease_id: str,
    demographic: Optional[Demographic] = None,
    disease_kb: dict | None = None,
) -> float:
    """计算疾病先验概率 P(disease)
    基础值来自 Orphanet 患病率, 经人口学修正"""
    base_prev = 1e-5  # 默认罕见病先验
    if disease_kb and disease_id in disease_kb:
        base_prev = disease_kb[disease_id].get("prevalence", 1e-5)
    modifier = 1.0
    if demographic:
        # 年龄/性别/地域修正 (简化示例)
        age = demographic.age or 30
        if age < 18:
            modifier *= 1.2  # 儿童期疾病略高先验
        if demographic.sex == "male":
            modifier *= 1.0
    return min(base_prev * modifier, 0.5)

def compute_likelihood(
    disease_id: str,
    phenotype_profile: PhenotypeProfile,
    freq_table: dict[str, dict[str, float]],
) -> float:
    """计算似然 P(phenotypes | disease)
    使用 Naive Bayes 假设, 对每个表型独立计算"""
    disease_freqs = freq_table.get(disease_id, {})
    if not disease_freqs:
        return 1e-6  # 无频率数据时极低似然

    log_likelihood = 0.0
    for vec in phenotype_profile.vectors:
        freq = disease_freqs.get(vec.hpo_id, 0.01)  # 默认 1%
        freq = max(freq, 1e-4)  # 防止 log(0)
        if vec.presence == PresenceStatus.PRESENT:
            log_likelihood += math.log(freq)
        elif vec.presence == PresenceStatus.ABSENT:
            log_likelihood += math.log(1.0 - freq)
    return math.exp(log_likelihood)

def compute_posterior(
    disease_id: str,
    phenotype_profile: PhenotypeProfile,
    demographic: Optional[Demographic] = None,
    freq_table: dict | None = None,
    disease_kb: dict | None = None,
) -> BayesianScore:
    """计算后验 P(disease | phenotypes) 并返回完整评分"""
    freq_table = freq_table or load_frequency_table()
    prior = compute_prior(disease_id, demographic, disease_kb)
    likelihood = compute_likelihood(disease_id, phenotype_profile, freq_table)

    # 简化: 使用 single-disease 近似, 不做全疾病归一化
    posterior = prior * likelihood
    posterior = min(posterior / (posterior + (1 - posterior) * 1e-3), 1.0)

    log_odds = math.log2(posterior / (1 - posterior + 1e-10))

    disease_freqs = freq_table.get(disease_id, {})
    supporting = [v.hpo_id for v in phenotype_profile.vectors
                  if v.presence == PresenceStatus.PRESENT
                  and disease_freqs.get(v.hpo_id, 0) > 0.3]
    contradicting = [v.hpo_id for v in phenotype_profile.vectors
                     if v.presence == PresenceStatus.ABSENT
                     and disease_freqs.get(v.hpo_id, 0) > 0.5]

    return BayesianScore(
        disease_id=disease_id,
        prior_probability=prior,
        likelihood=likelihood,
        posterior_probability=posterior,
        log_odds=log_odds,
        supporting_phenotype_ids=supporting,
        contradicting_phenotype_ids=contradicting,
    )

def rank_hypotheses(
    scores: list[BayesianScore],
    disease_meta: dict[str, dict],
    top_k: int = 10,
) -> list[DiseaseHypothesis]:
    """将贝叶斯评分排序为疾病假设列表"""
    sorted_scores = sorted(scores, key=lambda s: s.posterior_probability,
                           reverse=True)
    hypotheses = []
    max_post = sorted_scores[0].posterior_probability if sorted_scores else 1.0
    for rank, score in enumerate(sorted_scores[:top_k], start=1):
        meta = disease_meta.get(score.disease_id, {})
        confidence = score.posterior_probability / (max_post + 1e-10)
        hypotheses.append(DiseaseHypothesis(
            disease_id=score.disease_id,
            disease_name=meta.get("name", score.disease_id),
            orpha_number=meta.get("orpha_number"),
            bayesian_score=score,
            supporting_phenotypes=score.supporting_phenotype_ids,
            contradicting_phenotypes=score.contradicting_phenotype_ids,
            rank=rank,
            confidence=round(confidence, 4),
            reasoning_chain=(
                f"先验={score.prior_probability:.2e}, "
                f"似然={score.likelihood:.2e}, "
                f"后验={score.posterior_probability:.4f}"
            ),
        ))
    return hypotheses
```

### 3.2 时序推理引擎 (`reasoning/temporal_logic.py`)

```python
from typing import Optional

def match_onset_age(
    disease_id: str,
    patient_onset: float,
    onset_profile: OnsetProfile,
) -> float:
    """发病年龄匹配度 (0-1)
    在典型范围内 → 1.0, 偏离越远 → 越低"""
    low, high = onset_profile.typical_age_range
    mid = (low + high) / 2
    spread = (high - low) / 2 + onset_profile.variability * mid
    if spread == 0:
        spread = 1.0
    distance = abs(patient_onset - mid)
    consistency = max(0.0, 1.0 - distance / (spread * 3))
    return round(consistency, 4)

def match_progression(
    disease_id: str,
    patient_pattern: TemporalPattern,
    disease_pattern: ProgressionPattern,
) -> float:
    """进展模式匹配度"""
    if patient_pattern == disease_pattern.speed:
        return 1.0
    # 部分兼容映射
    compat_map = {
        (TemporalPattern.ACUTE, TemporalPattern.SUBACUTE): 0.6,
        (TemporalPattern.SUBACUTE, TemporalPattern.ACUTE): 0.6,
        (TemporalPattern.CHRONIC_PROGRESSIVE, TemporalPattern.CHRONIC_STATIC): 0.3,
        (TemporalPattern.FLUCTUATING, TemporalPattern.RELAPSING): 0.5,
    }
    return compat_map.get(
        (patient_pattern, disease_pattern.speed), 0.1)

def match_sequence(
    disease_id: str,
    patient_sequence: list[str],
    expected_sequence: list[str],
) -> float:
    """症状出现序列匹配 (基于 LCS 最长公共子序列)"""
    if not expected_sequence:
        return 0.5  # 无参考序列时给中性分
    m, n = len(patient_sequence), len(expected_sequence)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if patient_sequence[i-1] == expected_sequence[j-1]:
                dp[i][j] = dp[i-1][j-1] + 1
            else:
                dp[i][j] = max(dp[i-1][j], dp[i][j-1])
    lcs_len = dp[m][n]
    return round(lcs_len / max(n, 1), 4)

def compute_temporal_match(
    disease_id: str,
    phenotype_profile: PhenotypeProfile,
    disease_temporal_db: dict,
) -> TemporalMatch:
    """综合时序匹配 — Layer 3 核心"""
    db_entry = disease_temporal_db.get(disease_id, {})
    onset_profile = OnsetProfile(**db_entry.get("onset", {
        "typical_age_range": (0, 80), "age_unit": "years", "variability": 0.5
    }))
    disease_prog = ProgressionPattern(**db_entry.get("progression", {
        "speed": TemporalPattern.CHRONIC_PROGRESSIVE, "trajectory": "worsening"
    }))

    # 提取患者实际发病年龄
    patient_onset = 30.0  # 默认
    for v in phenotype_profile.vectors:
        if v.onset_age is not None:
            patient_onset = v.onset_age
            break

    onset_c = match_onset_age(disease_id, patient_onset, onset_profile)
    prog_c = match_progression(
        disease_id,
        phenotype_profile.vectors[0].modifiers[0].temporal_pattern
            if phenotype_profile.vectors
               and phenotype_profile.vectors[0].modifiers
               and phenotype_profile.vectors[0].modifiers[0].temporal_pattern
            else TemporalPattern.CHRONIC_PROGRESSIVE,
        disease_prog,
    )
    seq_c = match_sequence(
        disease_id,
        [v.hpo_id for v in phenotype_profile.vectors],
        db_entry.get("expected_sequence", []),
    )

    overall = 0.4 * onset_c + 0.35 * prog_c + 0.25 * seq_c
    return TemporalMatch(
        disease_id=disease_id,
        onset_consistency=onset_c,
        progression_consistency=prog_c,
        sequence_consistency=seq_c,
        overall_temporal_score=round(overall, 4),
        notes=f"onset={onset_c}, prog={prog_c}, seq={seq_c}",
    )
```

### 3.3 遗传推理引擎 (`reasoning/inheritance.py`)

```python
from collections import Counter

def analyze_pedigree(pedigree: Pedigree) -> list[InheritancePattern]:
    """家系分析 — 推断可能的遗传模式"""
    patterns: list[InheritancePattern] = []
    affected = [m for m in pedigree.members
                if m.affected_status == AffectedStatus.TRUE]
    if not affected:
        return [InheritancePattern(
            mode=InheritanceMode.UNKNOWN, confidence=0.1,
            supporting_evidence=["无足够家系信息"])]

    # 规则 1: 近亲婚配 → 高度提示 AR
    if pedigree.consanguinity:
        patterns.append(InheritancePattern(
            mode=InheritanceMode.AR, confidence=0.8,
            supporting_evidence=["近亲婚配"]))

    # 规则 2: 连续世代受累 → AD
    generations_affected = set()
    for m in affected:
        gen = _get_generation(m.relationship)
        generations_affected.add(gen)
    if len(generations_affected) >= 2:
        patterns.append(InheritancePattern(
            mode=InheritanceMode.AD, confidence=0.7,
            supporting_evidence=[f"连续 {len(generations_affected)} 代受累"]))

    # 规则 3: 仅男性受累 → XR
    if all(m.sex == "male" for m in affected):
        patterns.append(InheritancePattern(
            mode=InheritanceMode.XR, confidence=0.6,
            supporting_evidence=["仅男性受累"]))

    # 规则 4: 母系遗传 → Mitochondrial
    maternal_members = [m for m in affected
                        if m.relationship in ("mother", "maternal_uncle")]
    if len(maternal_members) >= 2:
        patterns.append(InheritancePattern(
            mode=InheritanceMode.MITOCHONDRIAL, confidence=0.65,
            supporting_evidence=["母系遗传模式"]))

    if not patterns:
        patterns.append(InheritancePattern(
            mode=InheritanceMode.UNKNOWN, confidence=0.2,
            supporting_evidence=["家系信息不足"]))
    return patterns

def _get_generation(relationship: str) -> int:
    gen_map = {"father": 0, "mother": 0, "paternal_uncle": 0,
               "maternal_uncle": 0, "sibling": 1, "self": 1,
               "child": 2, "nephew": 2, "niece": 2}
    return gen_map.get(relationship, 1)

def check_mendelian_consistency(
    disease_id: str,
    inheritance_patterns: list[InheritancePattern],
    disease_inheritance_db: dict[str, InheritanceMode],
) -> bool:
    """检查疾病已知遗传模式与家系推断是否兼容"""
    known_mode = disease_inheritance_db.get(disease_id)
    if not known_mode:
        return True  # 无数据时不做排除
    inferred_modes = {p.mode for p in inheritance_patterns
                      if p.confidence > 0.4}
    if not inferred_modes:
        return True
    return known_mode in inferred_modes or InheritanceMode.UNKNOWN in inferred_modes

def compute_genetic_constraint(
    pedigree: Pedigree,
    hypotheses: list[DiseaseHypothesis],
    disease_inheritance_db: dict[str, InheritanceMode],
) -> GeneticConstraint:
    """计算遗传约束 — Layer 4 输出"""
    patterns = analyze_pedigree(pedigree)
    compatible, incompatible = [], []
    for h in hypotheses:
        if check_mendelian_consistency(
                h.disease_id, patterns, disease_inheritance_db):
            compatible.append(h.disease_id)
        else:
            incompatible.append(h.disease_id)
    prior_mod = 1.5 if pedigree.consanguinity else 1.0
    return GeneticConstraint(
        inheritance_patterns=patterns,
        compatible_diseases=compatible,
        incompatible_diseases=incompatible,
        prior_modifier=prior_mod,
    )
```

### 3.4 EVOI 计算器 (`reasoning/evoi.py`)

```python
import math

def compute_information_gain(
    test: DiagnosticTest,
    current_hypotheses: list[DiseaseHypothesis],
) -> float:
    """计算信息增益 — 该检查能区分多少假设"""
    n = len(current_hypotheses)
    if n <= 1:
        return 0.0
    # 基于 sensitivity/specificity 的区分度
    avg_sens = test.sensitivity
    avg_spec = test.specificity
    youden_index = avg_sens + avg_spec - 1.0  # 约登指数
    # 假设数量越多, 区分价值越高
    discrimination_factor = min(1.0, math.log2(n + 1) / 4.0)
    return round(youden_index * discrimination_factor, 4)

def compute_risk_cost_penalty(test: DiagnosticTest) -> float:
    """计算风险-成本惩罚"""
    risk_weights = {RiskLevel.LOW: 0.05, RiskLevel.MEDIUM: 0.2, RiskLevel.HIGH: 0.5}
    risk_penalty = risk_weights.get(test.risk_level, 0.2)
    cost_penalty = test.cost_tier / 5.0 * 0.15
    time_penalty = min(test.turnaround_time_days / 30.0, 1.0) * 0.1
    return round(risk_penalty + cost_penalty + time_penalty, 4)

def compute_net_evoi(
    test: DiagnosticTest,
    current_hypotheses: list[DiseaseHypothesis],
) -> EVOIScore:
    """计算净信息价值"""
    info_gain = compute_information_gain(test, current_hypotheses)
    penalty = compute_risk_cost_penalty(test)
    net = max(0.0, info_gain - penalty)
    return EVOIScore(
        test_id=test.test_id,
        information_gain=info_gain,
        risk_cost_penalty=penalty,
        net_evoi=round(net, 4),
        rank=0,  # 排序后填充
    )

def recommend_next_tests(
    candidates: list[DiagnosticTest],
    hypotheses: list[DiseaseHypothesis],
    top_k: int = 5,
) -> list[PathwayStep]:
    """推荐下一步检查 — 按 EVOI 排序"""
    scored = []
    for test in candidates:
        evoi = compute_net_evoi(test, hypotheses)
        scored.append((test, evoi))
    scored.sort(key=lambda x: x[1].net_evoi, reverse=True)
    steps = []
    for rank, (test, evoi) in enumerate(scored[:top_k], start=1):
        evoi.rank = rank
        steps.append(PathwayStep(
            test_id=test.test_id,
            evoi_score=evoi,
            rationale=f"EVOI={evoi.net_evoi:.3f}, "
                      f"信息增益={evoi.information_gain:.3f}, "
                      f"风险惩罚={evoi.risk_cost_penalty:.3f}",
            expected_outcomes=[
                f"阳性: 支持 {h.disease_name} (rank {h.rank})"
                for h in hypotheses[:3]
            ],
            alternative_tests=[
                t.test_id for t, _ in scored[:top_k]
                if t.test_id != test.test_id
            ][:2],
        ))
    return steps
```

---

## 4. Agent 详细设计

### 4.1 PhenotypeAnalyzer (Layer 1)

**文件:** `agents/phenotype_analyzer.py`

| 项目 | 说明 |
|------|------|
| 输入 | `user_message: str`, `session: DiagnosticSession` |
| 输出 | `PhenotypeProfile` |
| LLM 角色 | 从自然语言中提取结构化表型 |

**Prompt 模板:**

```
你是一位罕见病临床表型分析专家。请从以下患者主诉中提取结构化表型信息。

## 患者主诉
{user_message}

## 患者基本信息
年龄: {age}, 性别: {sex}, 地区: {region}

## 输出要求
请输出 JSON 格式的表型向量列表, 每个向量包含:
- hpo_id: HPO 标准术语 ID (HP:xxxxxxx)
- term_name: 术语名称
- presence: present/absent/unknown
- onset_age: 发病年龄
- severity: mild/moderate/severe/life_threatening
- modifiers: 修饰符列表 (分布、时间模式、侧别等)

仅提取明确提及或强烈暗示的表型, 不要推测。
```

**KnowS 集成:** 调用 KnowS 搜索 HPO 术语标准化建议 (source=guide)。

### 4.2 HypothesisGenerator (Layer 2)

**文件:** `agents/hypothesis_generator.py`

| 项目 | 说明 |
|------|------|
| 输入 | `PhenotypeProfile`, `Demographic` |
| 输出 | `list[DiseaseHypothesis]` |
| LLM 角色 | 验证贝叶斯排序结果, 补充推理链 |

**Prompt 模板:**

```
你是一位罕见病诊断专家。基于以下结构化表型档案和贝叶斯评分结果,
请验证疾病假设排序并补充临床推理。

## 表型档案
{phenotype_profile_json}

## 贝叶斯评分 Top-10
{bayesian_scores_json}

## 任务
1. 检查排序是否合理, 是否有遗漏的鉴别诊断
2. 为 Top-3 假设各写一段推理链 (≤100 字)
3. 标注支持/反对每个假设的关键表型

输出 JSON: { "verified_hypotheses": [...], "differential_notes": "..." }
```

**KnowS 集成:** 对 Top-5 疾病分别检索文献 (source=paper_en + paper_cn)。

### 4.3 TemporalReasoner (Layer 3)

**文件:** `agents/temporal_reasoner.py`

| 项目 | 说明 |
|------|------|
| 输入 | `PhenotypeProfile`, `list[DiseaseHypothesis]` |
| 输出 | `list[TemporalMatch]` |
| LLM 角色 | 评估时序合理性 |

**Prompt 模板:**

```
你是一位擅长疾病自然史分析的专家。请评估以下疾病假设与患者症状时间线的匹配度。

## 患者时间线
{timeline_description}

## 疾病假设
{hypotheses_json}

## 各疾病典型自然史
{disease_natural_history_json}

请为每个假设输出时序匹配评分 (0-1) 及理由。
```

**KnowS 集成:** 检索疾病自然史文献 (source=guide + paper_en)。

### 4.4 GeneticReasoner (Layer 4)

**文件:** `agents/genetic_reasoner.py`

| 项目 | 说明 |
|------|------|
| 输入 | `Pedigree` (可选), `list[DiseaseHypothesis]` |
| 输出 | `GeneticConstraint` |
| LLM 角色 | 家系解读, 遗传模式推断 |

**Prompt 模板:**

```
你是一位临床遗传学专家。请根据家系信息分析可能的遗传模式,
并评估各疾病假设与遗传模式的兼容性。

## 家系信息
{pedigree_json}

## 疾病假设列表
{hypotheses_json}

## 已知遗传模式
{disease_inheritance_json}

请输出: 推断的遗传模式、兼容/不兼容的疾病列表、先验修正系数。
```

**KnowS 集成:** 检索遗传咨询指南 (source=guide)。

### 4.5 PathwayPlanner (Layer 5)

**文件:** `agents/pathway_planner.py`

| 项目 | 说明 |
|------|------|
| 输入 | `list[DiseaseHypothesis]`, `GeneticConstraint` |
| 输出 | `DiagnosticPathway` |
| LLM 角色 | 解释 EVOI 排序, 生成可读推荐 |

**Prompt 模板:**

```
你是一位诊断路径规划专家。基于当前疾病假设和 EVOI 分析结果,
请制定最优的诊断检查路径。

## 当前假设 (Top-5)
{hypotheses_json}

## EVOI 排序
{evoi_ranked_tests_json}

## 约束条件
遗传约束: {genetic_constraint_json}
安全等级: {safety_level}

请输出: 推荐检查路径 (最多 5 步), 每步包含理由和预期结果。
```

**KnowS 集成:** 检索临床试验信息 (source=trial) 和药品说明书 (source=package_insert)。

### 4.6 ReportSynthesizer

**文件:** `agents/report_synthesizer.py`

| 项目 | 说明 |
|------|------|
| 输入 | 全部 Layer 输出 + `EvidencePool` |
| 输出 | `Report` |
| LLM 角色 | 综合生成诊断报告 |

**Prompt 模板:**

```
你是一位罕见病诊断报告撰写专家。请综合所有推理层结果, 生成结构化诊断报告。

## 推理摘要
表型分析: {phenotype_summary}
疾病假设 Top-3: {top3_hypotheses}
时序匹配: {temporal_matches}
遗传分析: {genetic_summary}
推荐路径: {pathway_summary}

## 证据列表
{evidence_citations}

## 报告要求
1. 主文: 结构化诊断分析 (≤800 字)
2. 快照: 一段话摘要 (≤150 字)
3. 推理摘要: 各层关键结论
4. 不确定性说明: 当前诊断的局限性
5. 引用: 所有证据编号

⚠️ 必须在报告末尾注明: "本报告为 AI 辅助分析, 仅供参考, 不构成临床诊断依据。"
```

---

## 5. LangGraph 状态机

### 5.1 图结构

```
                    ┌─────────────────┐
                    │  phenotype_     │
                    │  analyzer       │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  hypothesis_    │◄──────────────┐
                    │  generator      │               │ (backflow: genetic)
                    └────────┬────────┘               │
                             │                        │
                    ┌────────▼────────┐               │
                    │  temporal_      │               │
                    │  reasoner       │               │
                    └────────┬────────┘               │
                             │                        │
                    ┌────────▼────────┐               │
                    │  genetic_       ├───────────────┘
                    │  reasoner       │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  pathway_       │
                    │  planner        │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  report_        │
                    │  synthesizer    │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  END / 回溯判断  │
                    └─────────────────┘
```

### 5.2 图构建代码

```python
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

def build_diagnostic_graph() -> StateGraph:
    graph = StateGraph(DiagnosticSession)

    # 注册 6 个节点
    graph.add_node("phenotype_analyzer", phenotype_analyzer_node)
    graph.add_node("hypothesis_generator", hypothesis_generator_node)
    graph.add_node("temporal_reasoner", temporal_reasoner_node)
    graph.add_node("genetic_reasoner", genetic_reasoner_node)
    graph.add_node("pathway_planner", pathway_planner_node)
    graph.add_node("report_synthesizer", report_synthesizer_node)

    # 主链路: 顺序执行
    graph.set_entry_point("phenotype_analyzer")
    graph.add_edge("phenotype_analyzer", "hypothesis_generator")
    graph.add_edge("hypothesis_generator", "temporal_reasoner")
    graph.add_edge("temporal_reasoner", "genetic_reasoner")

    # 条件边: genetic → hypothesis (backflow) 或 pathway
    graph.add_conditional_edges(
        "genetic_reasoner",
        backflow_router,  # 返回 "hypothesis_generator" 或 "pathway_planner"
        {
            "hypothesis_generator": "hypothesis_generator",
            "pathway_planner": "pathway_planner",
        },
    )

    graph.add_edge("pathway_planner", "report_synthesizer")

    # 条件边: report → END 或 backflow
    graph.add_conditional_edges(
        "report_synthesizer",
        termination_router,  # 返回 "end" 或 "phenotype_analyzer"
        {
            "end": END,
            "phenotype_analyzer": "phenotype_analyzer",
        },
    )

    # Checkpoint 持久化
    checkpointer = SqliteSaver.from_conn_string("checkpoints.db")
    return graph.compile(checkpointer=checkpointer)

def backflow_router(state: DiagnosticSession) -> str:
    """遗传推理后: 是否触发回溯"""
    if state.genetic_constraint and state.backflow_count < state.max_backflow:
        incompatible = state.genetic_constraint.incompatible_diseases
        # 如果有高排序假设被排除, 触发回溯
        top3_ids = {h.disease_id for h in state.hypotheses[:3]}
        if top3_ids & set(incompatible):
            state.backflow_count += 1
            return "hypothesis_generator"
    return "pathway_planner"

def termination_router(state: DiagnosticSession) -> str:
    """报告生成后: 是否触发全链路回溯"""
    if (state.safety_level == "alert"
            and state.backflow_count < state.max_backflow):
        state.backflow_count += 1
        return "phenotype_analyzer"
    return "end"
```

### 5.3 回溯控制

- `backflow_count` 全局计数器, 每次回溯 +1
- `max_backflow = 2` 硬上限, 防止无限循环
- 回溯类型:
  - **局部回溯**: genetic → hypothesis (仅重跑 Layer 2-5)
  - **全链路回溯**: report → phenotype (重跑 Layer 1-5, 仅在 safety_level=alert 时)

---

## 6. KnowS 证据检索集成

### 6.1 KnowSClient 封装

```python
import httpx
import asyncio
from typing import Optional

class KnowsClient:
    """KnowS 证据检索客户端 (复用 eb-consult 模式)"""

    BASE_URL = "https://knows-api.example.com/v1"
    CALL_INTERVAL = 0.4  # 串行调用间隔 (秒)

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )
        self._last_call_time: float = 0.0

    async def search(
        self,
        query: str,
        sources: list[EvidenceSource],
        top_k: int = 5,
        year_from: Optional[int] = None,
    ) -> list[Evidence]:
        """检索证据"""
        # 限速: 确保 0.4s 间隔
        elapsed = asyncio.get_event_loop().time() - self._last_call_time
        if elapsed < self.CALL_INTERVAL:
            await asyncio.sleep(self.CALL_INTERVAL - elapsed)

        payload = {
            "query": query,
            "sources": [s.value for s in sources],
            "top_k": top_k,
        }
        if year_from:
            payload["year_from"] = year_from

        resp = await self._client.post("/search", json=payload)
        resp.raise_for_status()
        self._last_call_time = asyncio.get_event_loop().time()

        results = []
        for item in resp.json()["results"]:
            results.append(Evidence(
                id=item["id"],
                source=EvidenceSource(item["source"]),
                title=item["title"],
                abstract=item.get("abstract"),
                publish_date=item.get("publish_date"),
                organizations=item.get("organizations", []),
                has_pdf=item.get("has_pdf", False),
                doi=item.get("doi"),
                journal=item.get("journal"),
                study_type=item.get("study_type"),
                impact_factor=item.get("impact_factor"),
                retrieved_layer=item.get("retrieved_layer", "unknown"),
                relevance_score=item.get("relevance_score", 0.5),
                grade=EvidenceGrade(item.get("grade", "D")),
            ))
        return results
```

### 6.2 各层检索策略

| Layer | 检索 Query 构造 | Sources | 说明 |
|-------|----------------|---------|------|
| Layer 1 | HPO term_name + 关键词 | guide | 表型标准化参考 |
| Layer 2 | disease_name + phenotype组合 | paper_en, paper_cn | 疾病-表型关联文献 |
| Layer 3 | disease_name + "natural history" | guide, paper_en | 自然史/病程文献 |
| Layer 4 | disease_name + "inheritance" + "genetic counseling" | guide | 遗传咨询指南 |
| Layer 5 | test_name + disease_name | trial, package_insert | 临床试验/药品信息 |
| Report | 汇总所有 evidence_ids | 全源 | 引用验证 |

### 6.3 证据-推理链关联

每条 Evidence 通过 `retrieved_layer` 字段标记其所属推理层, 最终在 Report 中通过 `evidence_citations` 形成可追溯的证据链。EvidencePool 作为全局共享状态, 各层 Agent 均可写入, ReportSynthesizer 统一读取。

---

## 7. LLM Gateway

### 7.1 多 Provider 支持

```python
# config/llm.yaml
providers:
  deepseek:
    base_url: "https://api.deepseek.com/v1"
    model: "deepseek-chat"
    api_key_env: "DEEPSEEK_API_KEY"
    max_tokens: 4096
    temperature: 0.3
    json_mode: true

  openai:
    base_url: "https://api.openai.com/v1"
    model: "gpt-4o"
    api_key_env: "OPENAI_API_KEY"
    max_tokens: 4096
    temperature: 0.3
    json_mode: true

  qwen:
    base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model: "qwen-max"
    api_key_env: "DASHSCOPE_API_KEY"
    max_tokens: 4096
    temperature: 0.3
    json_mode: true

  stepfun:
    base_url: "https://api.stepfun.com/v1"
    model: "step-2-16k"
    api_key_env: "STEPFUN_API_KEY"
    max_tokens: 4096
    temperature: 0.3
    json_mode: true

# 各 Agent 的 LLM 分配
agent_llm_mapping:
  phenotype_analyzer:
    primary: "deepseek"
    fallback: ["openai", "qwen"]
  hypothesis_generator:
    primary: "openai"
    fallback: ["deepseek", "qwen"]
  temporal_reasoner:
    primary: "deepseek"
    fallback: ["qwen"]
  genetic_reasoner:
    primary: "openai"
    fallback: ["deepseek"]
  pathway_planner:
    primary: "deepseek"
    fallback: ["qwen", "stepfun"]
  report_synthesizer:
    primary: "openai"
    fallback: ["deepseek", "qwen"]
```

### 7.2 Failover 链实现

```python
class LLMGateway:
    """LLM 网关 — 多 Provider + Failover"""

    def __init__(self, config: dict):
        self.providers = config["providers"]
        self.agent_mapping = config["agent_llm_mapping"]
        self._clients: dict[str, httpx.AsyncClient] = {}
        for name, cfg in self.providers.items():
            api_key = os.environ.get(cfg["api_key_env"], "")
            self._clients[name] = httpx.AsyncClient(
                base_url=cfg["base_url"],
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                timeout=60.0,
            )

    async def chat(
        self,
        agent_name: str,
        messages: list[dict],
        json_mode: bool = True,
    ) -> str:
        mapping = self.agent_mapping.get(agent_name, {})
        primary = mapping.get("primary", "deepseek")
        fallbacks = mapping.get("fallback", [])
        chain = [primary] + fallbacks

        for provider_name in chain:
            try:
                return await self._call_provider(
                    provider_name, messages, json_mode)
            except Exception as e:
                logger.warning(f"LLM failover: {provider_name} → {e}")
                continue
        raise RuntimeError(f"All LLM providers failed for {agent_name}")

    async def _call_provider(
        self, name: str, messages: list[dict], json_mode: bool
    ) -> str:
        cfg = self.providers[name]
        payload = {
            "model": cfg["model"],
            "messages": messages,
            "max_tokens": cfg["max_tokens"],
            "temperature": cfg["temperature"],
        }
        if json_mode and cfg.get("json_mode"):
            payload["response_format"] = {"type": "json_object"}
        resp = await self._clients[name].post(
            "/chat/completions", json=payload)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
```

---

## 8. 安全机制

### 8.1 四道安全阀 (Safety Valves)

```python
class SafetyValve:
    """安全阀 — 每层推理后触发检查"""

    @staticmethod
    def valve_1_phenotype_sanity(profile: PhenotypeProfile) -> str:
        """阀1: 表型合理性检查
        - 表型数量 < 1 → 提示补充信息
        - 全部 ABSENT → 数据异常
        - 矛盾表型 (如同时 present + absent 同一 HPO) → 标记"""
        if len(profile.vectors) == 0:
            return "alert"
        if all(v.presence == PresenceStatus.ABSENT for v in profile.vectors):
            return "alert"
        return "normal"

    @staticmethod
    def valve_2_hypothesis_coverage(
        hypotheses: list[DiseaseHypothesis],
        profile: PhenotypeProfile,
    ) -> str:
        """阀2: 假设覆盖度检查
        - Top-1 置信度 < 0.1 → 低信心, 提示可能需要更多信息
        - 所有假设 confidence < 0.05 → 触发保守降级"""
        if not hypotheses:
            return "alert"
        if hypotheses[0].confidence < 0.05:
            return "conservative"
        return "normal"

    @staticmethod
    def valve_3_genetic_conflict(
        genetic: GeneticConstraint,
        hypotheses: list[DiseaseHypothesis],
    ) -> str:
        """阀3: 遗传冲突检查
        - Top-1 假设被遗传约束排除 → 触发回溯"""
        if not genetic or not hypotheses:
            return "normal"
        top1_id = hypotheses[0].disease_id
        if top1_id in genetic.incompatible_diseases:
            return "alert"
        return "normal"

    @staticmethod
    def valve_4_safety_critical(
        pathway: DiagnosticPathway,
        phenotype: PhenotypeProfile,
    ) -> str:
        """阀4: 危急值检查
        - 存在 LIFE_THREATENING 表型 → 立即提示紧急就医
        - 推荐检查含 HIGH risk → 标注风险"""
        has_critical = any(
            v.severity_level == SeverityLevel.LIFE_THREATENING
            for v in phenotype.vectors
        )
        if has_critical:
            return "emergency"
        return "normal"
```

### 8.2 保守降级逻辑

当 `safety_level` 被设为 `"conservative"` 时:
- 假设列表仅展示 confidence > 0.1 的疾病
- 诊断报告中增加更多不确定性说明
- 推荐检查仅保留 LOW/MEDIUM risk 项目
- LLM temperature 降至 0.1

### 8.3 审计日志 (不可关闭)

```python
import logging

# 审计 logger — 始终启用, 不可被关闭
audit_logger = logging.getLogger("rare_dx.audit")
audit_handler = logging.FileHandler("logs/audit.log", encoding="utf-8")
audit_handler.setFormatter(logging.Formatter(
    "%(asctime)s | %(levelname)s | %(message)s"))
audit_logger.addHandler(audit_handler)
audit_logger.setLevel(logging.INFO)
audit_logger.propagate = False  # 防止被上层 logger 关闭

def audit_log(event: str, session_id: str, detail: dict):
    audit_logger.info(f"[{event}] session={session_id} detail={detail}")

# 关键审计点:
# - 每次 LLM 调用 (provider, model, token_count, latency)
# - 每次 KnowS 检索 (query, sources, result_count)
# - 安全阀触发 (valve_id, level, reason)
# - 回溯触发 (from_node, to_node, backflow_count)
# - 报告生成 (round, hypothesis_count, evidence_count)
```

---

## 9. 前端组件设计

### 9.1 组件树

```
<App>
├── <DiagnosticStream>          ← SSE 事件流容器
│   ├── <PhenotypePanel>        ← Layer 1: 表型可视化
│   │   ├── <PhenotypeTag>      ← 单个 HPO 标签 (颜色编码 presence)
│   │   └── <ModifierBadge>     ← 修饰符徽章
│   ├── <HypothesisRanking>     ← Layer 2: 疾病假设排行
│   │   ├── <HypothesisCard>    ← 单疾病卡片
│   │   │   ├── <BayesianBar>   ← 后验概率条形图
│   │   │   └── <EvidenceList>  ← 支持/反对证据
│   │   └── <ConfidenceMeter>   ← 置信度仪表
│   ├── <TemporalTimeline>      ← Layer 3: 时间线可视化
│   │   ├── <OnsetMarker>       ← 发病年龄标记
│   │   └── <ProgressionArrow>  ← 进展方向箭头
│   ├── <PedigreeViewer>        ← Layer 4: 家系图 (SVG)
│   │   ├── <MemberNode>        ← 家系成员节点
│   │   └── <ConnectionLine>    ← 关系连线
│   ├── <PathwayRecommendation> ← Layer 5: 诊断路径
│   │   ├── <StepCard>          ← 检查步骤卡片
│   │   └── <EVOIGauge>         ← EVOI 仪表盘
│   ├── <EvidenceCard>          ← 证据卡片 (通用)
│   └── <DiagnosticReport>      ← 最终诊断报告
│       ├── <ReportSection>     ← 报告分区
│       └── <CitationLink>      ← 引用链接
└── <ChatInput>                 ← 用户输入区
```

### 9.2 SSE 事件处理

```typescript
// hooks/useDiagnosticStream.ts
interface SSEEvent {
  type: "phenotype" | "hypothesis" | "temporal" | "genetic"
      | "pathway" | "report" | "evidence" | "safety" | "done";
  layer: number;
  data: any;
  round: number;
}

export function useDiagnosticStream(sessionId: string) {
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [currentLayer, setCurrentLayer] = useState(0);
  const [isStreaming, setIsStreaming] = useState(false);

  useEffect(() => {
    const source = new EventSource(
      `/api/chat/stream?session_id=${sessionId}`
    );
    source.onmessage = (e) => {
      const event: SSEEvent = JSON.parse(e.data);
      setEvents(prev => [...prev, event]);
      setCurrentLayer(event.layer);
      if (event.type === "done") {
        setIsStreaming(false);
        source.close();
      }
    };
    setIsStreaming(true);
    return () => source.close();
  }, [sessionId]);

  return { events, currentLayer, isStreaming };
}
```

### 9.3 Zustand 状态管理

```typescript
// store/diagnosticStore.ts
import { create } from "zustand";

interface DiagnosticState {
  sessionId: string | null;
  round: number;
  phenotypeProfile: PhenotypeProfile | null;
  hypotheses: DiseaseHypothesis[];
  temporalMatches: TemporalMatch[];
  geneticConstraint: GeneticConstraint | null;
  pathway: DiagnosticPathway | null;
  report: Report | null;
  evidences: Record<string, Evidence>;
  safetyLevel: string;
  isProcessing: boolean;

  // Actions
  setSession: (id: string) => void;
  updateFromSSE: (event: SSEEvent) => void;
  reset: () => void;
}

export const useDiagnosticStore = create<DiagnosticState>((set) => ({
  sessionId: null,
  round: 0,
  phenotypeProfile: null,
  hypotheses: [],
  temporalMatches: [],
  geneticConstraint: null,
  pathway: null,
  report: null,
  evidences: {},
  safetyLevel: "normal",
  isProcessing: false,

  setSession: (id) => set({ sessionId: id }),

  updateFromSSE: (event) => set((state) => {
    switch (event.type) {
      case "phenotype":
        return { phenotypeProfile: event.data, round: event.round };
      case "hypothesis":
        return { hypotheses: event.data, round: event.round };
      case "temporal":
        return { temporalMatches: event.data };
      case "genetic":
        return { geneticConstraint: event.data };
      case "pathway":
        return { pathway: event.data };
      case "report":
        return { report: event.data, isProcessing: false };
      case "evidence":
        const newEvidences = { ...state.evidences };
        event.data.forEach((e: Evidence) => { newEvidences[e.id] = e; });
        return { evidences: newEvidences };
      case "safety":
        return { safetyLevel: event.data.level };
      default:
        return state;
    }
  }),

  reset: () => set({
    sessionId: null, round: 0, phenotypeProfile: null,
    hypotheses: [], temporalMatches: [], geneticConstraint: null,
    pathway: null, report: null, evidences: {},
    safetyLevel: "normal", isProcessing: false,
  }),
}));
```

---

## 10. 配置管理

### 10.1 `config/llm.yaml`

参见 [7.1 节](#71-多-provider-支持) 中的完整定义。

### 10.2 `config/reasoning.yaml`

```yaml
# config/reasoning.yaml — 推理引擎参数

bayesian:
  frequency_table_path: "data/hpo_frequency/orphanet_freq.json"
  default_frequency: 0.01        # 无数据时的默认表型频率
  min_posterior_threshold: 0.001 # 低于此值的假设不进入 Top-K
  top_k_hypotheses: 10
  prior_modifier:
    consanguinity_multiplier: 2.0
    pediatric_multiplier: 1.2
    region_specific_multiplier: 1.5

temporal:
  weights:
    onset: 0.40
    progression: 0.35
    sequence: 0.25
  default_variability: 0.5       # 无数据时的默认变异度
  min_temporal_score: 0.2        # 低于此值的时序匹配标记为弱相关

genetic:
  pedigree_max_members: 50
  confidence_threshold: 0.4      # 低于此值的遗传模式不参与兼容判断
  consanguinity_ar_priority: 0.8 # 近亲婚配时 AR 模式的置信度

evoi:
  risk_weights:
    low: 0.05
    medium: 0.20
    high: 0.50
  cost_weight: 0.15
  time_weight: 0.10
  max_recommended_tests: 5
  min_net_evoi: 0.05             # 低于此值的检查不推荐

safety:
  max_backflow: 2
  emergency_keywords:
    - "呼吸困难"
    - "意识障碍"
    - "抽搐"
    - "大出血"
  conservative_threshold: 0.05   # Top-1 置信度低于此值时降级
  report_disclaimer: "本报告为 AI 辅助分析, 仅供参考, 不构成临床诊断依据。"
```

### 10.3 `config/disease_kb.yaml`

```yaml
# config/disease_kb.yaml — 疾病知识库配置

sources:
  orphanet:
    base_url: "https://www.orpha.net/api/v1"
    sync_interval_hours: 168     # 每周同步
    local_cache: "data/orphanet_cache.json"
  omim:
    api_key_env: "OMIM_API_KEY"
    base_url: "https://api.omim.org/api/v2"
    sync_interval_hours: 168
    local_cache: "data/omim_cache.json"
  hpo:
    ontology_path: "data/hpo/hp.obo"
    annotation_path: "data/hpo/phenotype_annotation.txt"
    sync_interval_hours: 336     # 每两周同步

disease_metadata:
  total_count: 7391              # Orphanet 罕见病总数
  with_frequency_data: 4218      # 有表型频率数据的疾病数
  with_inheritance_data: 5102    # 有遗传模式数据的疾病数
```

### 10.4 `.env.example`

```bash
# === LLM Providers ===
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
STEPFUN_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx

# === KnowS API ===
KNOWS_API_KEY=knows-xxxxxxxxxxxxxxxxxxxxxxxx
KNOWS_BASE_URL=https://knows-api.example.com/v1

# === Disease KB ===
OMIM_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxx

# === Application ===
APP_ENV=development
APP_PORT=8000
APP_HOST=0.0.0.0
LOG_LEVEL=INFO

# === Database ===
SQLITE_DB_PATH=data/checkpoints.db

# === Safety ===
SAFETY_MODE=normal              # normal / conservative / emergency
AUDIT_LOG_PATH=logs/audit.log
```

---

> **文档结束** · rare-dx 技术设计书 v0.1.0
>
> 本设计书覆盖系统架构、数据模型、推理算法、Agent 设计、状态机、证据检索、LLM 网关、安全机制、前端组件及配置管理共 10 个模块。所有 Pydantic 模型定义与推理算法实现均可直接作为开发参考。
