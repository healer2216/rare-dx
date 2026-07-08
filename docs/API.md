# Rare-Dx API 接口文档

## 一、基础信息

**Base URL**: `http://localhost:8765`（后端直连）
**前端代理**: 通过 Next.js rewrite (`/api/*` → `localhost:8765`)，前端端口 3001
**Content-Type**: `application/json`
**认证方式**: 无（演示版本）
**CORS**: 已启用，允许所有来源

---

## 二、接口清单

| 方法 | 路径 | 功能 | 说明 |
|-----|------|------|------|
| GET | `/api/health` | 健康检查 | 服务状态检测 |
| GET | `/api/diagnostic/stream` | SSE流式诊断 | 核心接口，5层推理流水线 |
| GET | `/api/report/download` | 下载诊断报告 | DOCX / PDF |
| GET | `/api/sessions` | 历史会话列表 | SQLite 持久化 |
| GET | `/api/sessions/{session_id}` | 会话详情 | 完整状态快照 |
| GET | `/api/sessions/{session_id}/audit` | 审计日志 | 推理链路追溯 |
| DELETE | `/api/sessions/{session_id}` | 删除会话 | — |

---

## 三、接口详情

### 3.1 健康检查

```
GET /api/health
```

**响应** (200 OK)：`{"status": "ok", "version": "0.1.0"}`

```bash
curl http://localhost:8000/api/health
```

---

### 3.2 SSE 流式诊断（核心接口）

```
GET /api/diagnostic/stream?user_message=...&session_id=...
Accept: text/event-stream
```

| 参数 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| user_message | string | 是 | 患者临床描述文本 |
| session_id | string | 否 | 会话ID，不传则自动创建 |

**事件流顺序**：
```
round_start → agent_start(phenotype) → agent_delta → evidence
→ phenotype_vector(含 metrics) → agent_done
→ agent_start(hypothesis) → evidence → hypothesis_ranking → agent_done
→ agent_start(temporal) → evidence → temporal_match → agent_done
→ agent_start(genetic) → evidence → inheritance_pattern → agent_done
→ agent_start(pathway) → evidence → evoi_recommendation → agent_done
→ agent_start(report) → report_delta → agent_done
→ round_end
```

**SSE 事件类型（14 种）**：

| 事件 | 触发时机 | payload 关键字段 |
|------|---------|-----------------|
| `round_start` | 推理开始 | `round`, `session_id` |
| `agent_start` | 每层启动 | `agent`, `layer` |
| `agent_delta` | 中间状态 | `agent`, `delta` |
| `agent_done` | 每层完成 | `agent`, `output` |
| `phenotype_vector` | L1 完成 | `phenotypes[...]`, `metrics{llm_count, dict_count, merged_count}` |
| `hypothesis_ranking` | L2 完成 | `hypotheses[...]`（含 LLM 兜底标注） |
| `temporal_match` | L3 完成 | `matches[...]` |
| `inheritance_pattern` | L4 完成 | `patterns[...]`, `compatible`, `incompatible` |
| `evoi_recommendation` | L5 完成 | `steps[...]`, `total_information_gain` |
| `report_delta` | L6 报告 | 结构化报告 |
| `evidence` | 各层证据 | `source_layer`, `references[...]` |
| `safety_valve` | 安全触发 | `type`, `severity`, `message` |
| `round_end` | 回合结束 | `round`, `session_id` |
| `error` | 异常 | `code`, `message` |

```bash
# 后端直连（端口 8765，无 ping 干扰）
curl -sN "http://localhost:8765/api/diagnostic/stream?user_message=男婴，3月龄，进行性肌张力低下&session_id=demo"

# 通过前端代理（端口 3001）
curl -sN "http://localhost:3001/api/diagnostic/stream?user_message=男婴，3月龄，进行性肌张力低下&session_id=demo"
```

---

### 3.3 创建诊断会话

```
POST /api/agent/session
Content-Type: application/json
```

| 参数 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| user_message | string | 是 | 患者临床描述 |
| safety_level | string | 否 | `strict`（默认）/ `relaxed` |

**请求体**：`{"user_message": "男婴，3月龄，进行性肌张力低下，喂养困难，乳酸性酸中毒", "safety_level": "strict"}`

**响应** (200 OK)：`{"session_id": "s-a1b2c3d4", "status": "created"}`

```bash
curl -X POST http://localhost:8000/api/agent/session \
  -H "Content-Type: application/json" \
  -d '{"user_message":"男婴，3月龄，进行性肌张力低下，喂养困难，乳酸性酸中毒","safety_level":"strict"}'
```

---

### 3.4 查询会话状态

```
GET /api/agent/session/{session_id}
```

| 参数 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| session_id | string（路径） | 是 | 会话ID |

**响应** (200 OK)：
```json
{
  "session_id": "s-a1b2c3d4",
  "status": "completed",
  "round": 1,
  "phenotype_profile": {
    "vectors": [
      {"hpo_id": "HP:0001250", "term_name": "肌张力低下", "presence": "present", "onset_age": "P3M"},
      {"hpo_id": "HP:0003256", "term_name": "乳酸性酸中毒", "presence": "present", "onset_age": "P3M"}
    ]
  },
  "hypotheses": [
    {"disease_id": "ORPHA:520", "disease_name": "Leigh综合征", "bayesian_score": 0.87, "rank": 1},
    {"disease_id": "ORPHA:209", "disease_name": "丙酮酸脱氢酶缺乏症", "bayesian_score": 0.72, "rank": 2},
    {"disease_id": "ORPHA:32", "disease_name": "戊二酸血症II型", "bayesian_score": 0.45, "rank": 3}
  ],
  "temporal_matches": [{"disease_id": "ORPHA:520", "overall_temporal_score": 0.91}],
  "genetic_constraint": {"inheritance_patterns": [{"mode": "MITOCHONDRIAL", "confidence": 0.7}], "prior_modifier": 1.2},
  "diagnostic_pathway": {"steps": [{"test_name": "线粒体基因组全序列分析", "net_evoi": 0.92, "rank": 1}]},
  "evidence_pool": {"total_count": 8, "high_quality": 3},
  "report": "## 诊断辅助报告\n\n### 首要考虑\n**Leigh综合征 (ORPHA:520)** — 综合评分 0.89\n..."
}
```

```bash
curl http://localhost:8000/api/agent/session/s-a1b2c3d4
```

---

### 3.5 表型分析（Layer 1）

```
POST /api/agent/phenotype/{session_id}
Content-Type: application/json
```

| 参数 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| session_id | string（路径） | 是 | 会话ID |
| text | string | 是 | 临床表型描述文本 |

**请求体**：`{"text": "男婴，3月龄，进行性肌张力低下，喂养困难，乳酸性酸中毒，头颅MRI示基底节区对称性异常信号"}`

**响应** (200 OK)：
```json
{
  "session_id": "s-a1b2c3d4",
  "layer": 1, "agent": "phenotype",
  "phenotype_profile": {
    "vectors": [
      {"hpo_id": "HP:0001250", "term_name": "肌张力低下", "modifiers": {"severity": "moderate", "progression": "worsening"}, "presence": "present", "onset_age": "P3M"},
      {"hpo_id": "HP:0011968", "term_name": "喂养困难", "modifiers": {"severity": "severe"}, "presence": "present", "onset_age": "P1M"},
      {"hpo_id": "HP:0003256", "term_name": "乳酸性酸中毒", "modifiers": {"lab_value": "4.8 mmol/L"}, "presence": "present", "onset_age": "P3M"},
      {"hpo_id": "HP:0002135", "term_name": "基底节区对称性异常信号", "modifiers": {"imaging": "T2高信号", "distribution": "bilateral_symmetric"}, "presence": "present", "onset_age": "P3M"}
    ],
    "hpo_domains": ["HP:0000708", "HP:0001939", "HP:0002011"]
  }
}
```

```bash
curl -X POST http://localhost:8000/api/agent/phenotype/s-a1b2c3d4 \
  -H "Content-Type: application/json" \
  -d '{"text":"男婴，3月龄，进行性肌张力低下，喂养困难，乳酸性酸中毒，头颅MRI示基底节区对称性异常信号"}'
```

---

### 3.6 假设生成（Layer 2）

```
POST /api/agent/hypothesis/{session_id}
Content-Type: application/json
```

| 参数 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| session_id | string（路径） | 是 | 会话ID（需已完成 Layer 1） |
| （请求体） | object | 否 | 空对象，使用会话中已有的 phenotype_profile |

**请求体**：`{}`

**响应** (200 OK)：
```json
{
  "session_id": "s-a1b2c3d4",
  "layer": 2, "agent": "hypothesis",
  "hypotheses": [
    {
      "disease_id": "ORPHA:520", "disease_name": "Leigh综合征", "bayesian_score": 0.87,
      "supporting_phenotypes": ["HP:0001250", "HP:0011968", "HP:0003256", "HP:0002135"],
      "reasoning_chain": "婴儿期起病的进行性神经系统退行性变，基底节对称性病变为特征性影像表现，合并乳酸性酸中毒高度提示线粒体能量代谢障碍"
    },
    {
      "disease_id": "ORPHA:209", "disease_name": "丙酮酸脱氢酶缺乏症", "bayesian_score": 0.72,
      "supporting_phenotypes": ["HP:0001250", "HP:0003256", "HP:0002135"],
      "reasoning_chain": "PDH缺乏可致Leigh样表型，乳酸性酸中毒为直接代谢证据，需基因检测鉴别"
    }
  ]
}
```

```bash
curl -X POST http://localhost:8000/api/agent/hypothesis/s-a1b2c3d4 -H "Content-Type: application/json" -d '{}'
```

---

### 3.7 时序推理（Layer 3）

```
POST /api/agent/temporal/{session_id}
Content-Type: application/json
```

| 参数 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| session_id | string（路径） | 是 | 会话ID（需已完成 Layer 1-2） |
| （请求体） | object | 否 | 空对象，使用会话中已有数据 |

**请求体**：`{}`

**响应** (200 OK)：
```json
{
  "session_id": "s-a1b2c3d4",
  "layer": 3, "agent": "temporal",
  "temporal_matches": [
    {
      "disease_id": "ORPHA:520", "disease_name": "Leigh综合征",
      "onset_consistency": 0.95, "progression_consistency": 0.88,
      "sequence_consistency": 0.90, "overall_temporal_score": 0.91,
      "notes": "婴儿期起病、进行性加重的时间序列与典型Leigh综合征自然史高度一致"
    }
  ]
}
```

```bash
curl -X POST http://localhost:8000/api/agent/temporal/s-a1b2c3d4 -H "Content-Type: application/json" -d '{}'
```

---

### 3.8 遗传推理（Layer 4）

```
POST /api/agent/genetic/{session_id}
Content-Type: application/json
```

| 参数 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| session_id | string（路径） | 是 | 会话ID |
| pedigree | object | 否 | 家系信息 |
| pedigree.members | array | 否 | 成员列表，含 id/sex/affected |
| pedigree.consanguinity | boolean | 否 | 是否存在近亲婚配 |

**请求体**：
```json
{"pedigree": {"members": [{"id": "proband", "sex": "M", "affected": true}, {"id": "mother", "sex": "F", "affected": false}, {"id": "father", "sex": "M", "affected": false}], "consanguinity": false}}
```

**响应** (200 OK)：
```json
{
  "session_id": "s-a1b2c3d4",
  "layer": 4, "agent": "genetic",
  "genetic_constraint": {
    "inheritance_patterns": [
      {"mode": "MITOCHONDRIAL", "confidence": 0.70},
      {"mode": "AUTOSOMAL_RECESSIVE", "confidence": 0.25},
      {"mode": "X_LINKED_RECESSIVE", "confidence": 0.05}
    ],
    "compatible_diseases": ["ORPHA:520", "ORPHA:209", "ORPHA:685"],
    "incompatible_diseases": ["ORPHA:32"],
    "prior_modifier": 1.2,
    "notes": "父母均未受累，先证者为男性，线粒体遗传和常染色体隐性遗传均可解释"
  }
}
```

```bash
curl -X POST http://localhost:8000/api/agent/genetic/s-a1b2c3d4 \
  -H "Content-Type: application/json" \
  -d '{"pedigree":{"members":[{"id":"proband","sex":"M","affected":true},{"id":"mother","sex":"F","affected":false},{"id":"father","sex":"M","affected":false}],"consanguinity":false}}'
```

---

### 3.9 路径规划（Layer 5 / EVOI）

```
POST /api/agent/pathway/{session_id}
Content-Type: application/json
```

| 参数 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| session_id | string（路径） | 是 | 会话ID（需已完成 Layer 1-4） |
| （请求体） | object | 否 | 空对象，综合前 4 层输出进行 EVOI 分析 |

**请求体**：`{}`

**响应** (200 OK)：
```json
{
  "session_id": "s-a1b2c3d4",
  "layer": 5, "agent": "pathway",
  "diagnostic_pathway": {
    "steps": [
      {
        "test_name": "线粒体基因组全序列分析", "test_code": "MT-WS",
        "net_evoi": 0.92, "rank": 1,
        "rationale": "首选检查，可直接确认或排除线粒体DNA致病突变（如m.8993T>G/C），对Leigh综合征诊断具有决定性意义",
        "expected_outcomes": ["确认mtDNA突变→明确诊断", "阴性→转向核基因panel"],
        "turnaround_days": 14
      },
      {
        "test_name": "线粒体疾病相关核基因Panel", "test_code": "Mito-NGS-50",
        "net_evoi": 0.78, "rank": 2,
        "rationale": "若mtDNA分析阴性，需检测SURF1、NDUFS系列等核基因突变",
        "expected_outcomes": ["检出核基因致病变异→明确亚型", "阴性→考虑全外显子组测序"],
        "turnaround_days": 21
      }
    ]
  }
}
```

```bash
curl -X POST http://localhost:8000/api/agent/pathway/s-a1b2c3d4 -H "Content-Type: application/json" -d '{}'
```

---

## 四、错误响应格式

```json
{"detail": "错误描述信息"}
```

| HTTP 状态码 | 说明 | 处理方式 |
|------------|------|---------|
| 200 | 成功 | 正常处理 |
| 404 | 会话不存在 | 检查 session_id |
| 422 | 请求参数校验失败 | 检查请求体格式 |
| 500 | 服务器内部错误 | 查看服务端日志 |

---

## 五、SSE 事件类型详解

每个事件格式：`event: <类型>\ndata: <JSON>\n\n`

| # | 事件类型 | 说明 | JSON 示例 |
|---|---------|------|----------|
| 1 | `round_start` | 推理轮次开始 | `{"round": 1, "session_id": "s-a1b2c3d4", "stub_mode": false}` |
| 2 | `agent_start` | Agent 启动 | `{"agent": "phenotype", "round": 1}` |
| 3 | `agent_delta` | 流式文本片段 | `{"agent": "phenotype", "chunk": "正在分析表型特征..."}` |
| 4 | `agent_done` | Agent 完成 | `{"agent": "phenotype", "output": {"phenotype_count": 4, "hpo_domains": ["HP:0000708"]}}` |
| 5 | `phenotype_vector` | 表型向量输出 | `{"vectors": [{"hpo_id": "HP:0001250", "term_name": "肌张力低下", "modifiers": {"severity": "moderate"}, "presence": "present"}]}` |
| 6 | `hypothesis_ranking` | 贝叶斯假设排序 | `{"hypotheses": [{"disease_id": "ORPHA:520", "disease_name": "Leigh综合征", "bayesian_score": 0.87, "rank": 1}]}` |
| 7 | `temporal_match` | 时序一致性评分 | `{"disease_id": "ORPHA:520", "onset_consistency": 0.95, "progression_consistency": 0.88, "overall_temporal_score": 0.91}` |
| 8 | `inheritance_pattern` | 遗传模式推断 | `{"patterns": [{"mode": "MITOCHONDRIAL", "confidence": 0.7}], "compatible_count": 12}` |
| 9 | `evoi_recommendation` | 诊断路径推荐 | `{"steps": [{"test_name": "线粒体基因组全序列分析", "net_evoi": 0.92, "rank": 1}]}` |
| 10 | `evidence` | 循证证据引用 | `{"evidence": {"id": "ev-001", "title": "Mitochondrial DNA mutations in Leigh syndrome", "source": "paper_en", "journal": "Brain", "year": 2019}, "layer": "hypothesis"}` |
| 11 | `report_delta` | 报告流式片段 | `{"delta_md": "## 诊断辅助报告\n\n### 首要考虑\n**Leigh综合征 (ORPHA:520)** — 综合评分 0.89\n", "round": 1}` |
| 12 | `safety_valve` | 安全阀触发 | `{"type": "info_revise", "message": "表型信息修订，假设已重评估"}` |
| 13 | `heartbeat` | 心跳保活 | `{}` |
| 14 | `round_end` | 轮次结束 | `{"round": 1, "session_id": "s-a1b2c3d4"}` |
| 15 | `error` | 错误事件 | `{"message": "LLM 推理超时，已跳过当前层并继续流水线"}` |

**字段补充说明**：
- `agent_start` 中 `agent` 取值：`phenotype` / `hypothesis` / `temporal` / `genetic` / `pathway`
- `safety_valve` 中 `type` 取值：`info_revise` / `safety_alert` / `confidence_drop`

---

## 六、端到端测试脚本

### 6.1 健康检查
```bash
curl http://localhost:8000/api/health
```

### 6.2 创建会话
```bash
curl -X POST http://localhost:8000/api/agent/session \
  -H "Content-Type: application/json" \
  -d '{"user_message":"男婴，3月龄，进行性肌张力低下，喂养困难，乳酸性酸中毒，头颅MRI示基底节区对称性异常信号","safety_level":"strict"}'
```

### 6.3 完整 SSE 流式诊断
```bash
curl -N "http://localhost:8000/api/diagnostic/stream?user_message=男婴，3月龄，进行性肌张力低下，喂养困难，乳酸性酸中毒，头颅MRI示基底节区对称性异常信号"
```

### 6.4 逐层独立测试
```bash
# Layer 1: 表型分析
curl -X POST http://localhost:8000/api/agent/phenotype/s-a1b2c3d4 \
  -H "Content-Type: application/json" \
  -d '{"text":"男婴，3月龄，进行性肌张力低下，喂养困难，乳酸性酸中毒，头颅MRI示基底节区对称性异常信号"}'

# Layer 2: 假设生成（依赖 Layer 1）
curl -X POST http://localhost:8000/api/agent/hypothesis/s-a1b2c3d4 \
  -H "Content-Type: application/json" -d '{}'

# Layer 3: 时序推理（依赖 Layer 1-2）
curl -X POST http://localhost:8000/api/agent/temporal/s-a1b2c3d4 \
  -H "Content-Type: application/json" -d '{}'

# Layer 4: 遗传推理
curl -X POST http://localhost:8000/api/agent/genetic/s-a1b2c3d4 \
  -H "Content-Type: application/json" \
  -d '{"pedigree":{"members":[{"id":"proband","sex":"M","affected":true},{"id":"mother","sex":"F","affected":false},{"id":"father","sex":"M","affected":false}],"consanguinity":false}}'

# Layer 5: 路径规划（依赖 Layer 1-4）
curl -X POST http://localhost:8000/api/agent/pathway/s-a1b2c3d4 \
  -H "Content-Type: application/json" -d '{}'
```

### 6.5 查询会话状态
```bash
curl http://localhost:8000/api/agent/session/s-a1b2c3d4
```

---

## 七、技术说明

- **框架**: FastAPI + Uvicorn
- **流式传输**: Server-Sent Events (SSE)，`Content-Type: text/event-stream`
- **推理引擎**: LangGraph 状态机编排 5 层 Agent
- **会话存储**: 内存存储（演示版本），重启后数据丢失
- **HPO 版本**: Human Phenotype Ontology 2024-04

---

**文档版本**: v0.1.0
**最后更新**: 2025-07
**维护者**: Rare-Dx 开发团队
