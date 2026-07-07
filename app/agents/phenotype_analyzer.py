"""Layer 1 · 表型深度分析 Agent。

从临床文本提取 HPO 表型向量 + 修饰符。演示版使用关键词词典映射，
覆盖 D1/D2/D3 演示剧本的核心表型。后续可替换为 LLM NER。

KnowS 集成（按 PRD §4.2 Layer 1 策略）：
- 检索源：guide
- 检索目的：验证表型-HPO 映射参考
- 检索时机：表型提取完成后
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from ..state.session import (
    EvidencePool,
    PhenotypeModifier,
    PhenotypeProfile,
    PhenotypeVector,
    PresenceStatus,
)
from ..tools.knows_client import KnowsClient, LAYER_SOURCES
from ..tools.llm_gateway import LLMGateway


# ========== 表型关键词词典 ==========
# (关键词列表, hpo_id, term_name, 默认修饰符)
PHENOTYPE_DICTIONARY: list[dict[str, Any]] = [
    {
        "keywords": ["肌张力低下", "肌张力减低", "肌张力降低", "hypotonia", "肌力低下"],
        "hpo_id": "HP:0001290",
        "term_name": "肌张力低下",
        "default_modifiers": {"distribution": "generalized", "temporal_pattern": "progressive"},
    },
    {
        "keywords": ["喂养困难", "吸吮无力", "鼻饲", "feeding difficulty", "经口喂养"],
        "hpo_id": "HP:0002033",
        "term_name": "喂养困难",
        "default_modifiers": {},
    },
    {
        "keywords": ["乳酸性酸中毒", "血乳酸升高", "高乳酸", "lactic acidosis", "乳酸升高"],
        "hpo_id": "HP:0002154",
        "term_name": "乳酸性酸中毒",
        "default_modifiers": {"temporal_pattern": "persistent"},
    },
    {
        "keywords": ["基底节", "基底核", "壳核", "苍白球", "basal ganglia", "T2高信号"],
        "hpo_id": "HP:0002011",
        "term_name": "基底节区MRI异常信号",
        "default_modifiers": {"laterality": "bilateral"},
    },
    {
        "keywords": ["眼球震颤", "nystagmus", "眼球运动异常", "眼球运动受限"],
        "hpo_id": "HP:0001332",
        "term_name": "眼球运动异常",
        "default_modifiers": {"laterality": "bilateral"},
    },
    {
        "keywords": ["癫痫", "抽搐", "惊厥", "seizure", "癫痫发作"],
        "hpo_id": "HP:0001250",
        "term_name": "癫痫发作",
        "default_modifiers": {},
    },
    {
        "keywords": ["发育倒退", "认知倒退", "学习退步", "developmental regression", "行为异常"],
        "hpo_id": "HP:0001268",
        "term_name": "发育倒退",
        "default_modifiers": {"temporal_pattern": "progressive"},
    },
    {
        "keywords": ["皮肤色素沉着", "色素沉着", "色素减退", "hyperpigmentation", "皮肤色素"],
        "hpo_id": "HP:0001010",
        "term_name": "皮肤色素沉着",
        "default_modifiers": {},
    },
    {
        "keywords": ["VLCFA", "极长链脂肪酸", "极长链脂肪酸升高"],
        "hpo_id": "HP:0002315",
        "term_name": "VLCFA升高",
        "default_modifiers": {},
    },
    {
        "keywords": ["脑白质", "白质异常信号", "白质病变", "white matter", "脱髓鞘"],
        "hpo_id": "HP:0002500",
        "term_name": "脑白质MRI异常",
        "default_modifiers": {"laterality": "bilateral"},
    },
    {
        "keywords": ["痉挛性截瘫", "截瘫", "spastic paraplegia", "肌张力增高", "腱反射亢进"],
        "hpo_id": "HP:0001257",
        "term_name": "痉挛性截瘫",
        "default_modifiers": {},
    },
    {
        "keywords": ["低钾", "血钾低", "低钾血症", "hypokalemia", "血钾1.8", "血钾2.1"],
        "hpo_id": "HP:0002900",
        "term_name": "低钾血症",
        "default_modifiers": {"temporal_pattern": "relapsing"},
    },
    {
        "keywords": ["低镁", "血镁低", "低镁血症", "hypomagnesemia"],
        "hpo_id": "HP:0002908",
        "term_name": "低镁血症",
        "default_modifiers": {},
    },
    {
        "keywords": ["代谢性碱中毒", "碱中毒", "metabolic alkalosis", "HCO3"],
        "hpo_id": "HP:0003557",
        "term_name": "代谢性碱中毒",
        "default_modifiers": {},
    },
    {
        "keywords": ["尿钾升高", "尿钾排泄", "尿钾45", "尿钾增高"],
        "hpo_id": "HP:0003118",
        "term_name": "尿钾升高",
        "default_modifiers": {},
    },
    {
        "keywords": ["肾素", "醛固酮", "肾素活性升高", "醛固酮升高", "肾素-醛固酮"],
        "hpo_id": "HP:0000863",
        "term_name": "肾素-醛固酮系统激活",
        "default_modifiers": {},
    },
    {
        "keywords": ["视网膜变性", "视力下降", "视网膜", "retinal degeneration"],
        "hpo_id": "HP:0000556",
        "term_name": "视网膜变性",
        "default_modifiers": {},
    },
    {
        "keywords": ["肌无力", "四肢无力", "无力", "weakness", "肌力3级"],
        "hpo_id": "HP:0001324",
        "term_name": "肌无力",
        "default_modifiers": {"distribution": "proximal"},
    },
    # ── 新增：代谢 ──
    {"keywords":["高血糖","血糖升高","糖尿病","hyperglycemia"],"hpo_id":"HP:0003074","term_name":"高血糖","default_modifiers":{}},
    {"keywords":["低血糖","血糖低","hypoglycemia","低血糖症"],"hpo_id":"HP:0001943","term_name":"低血糖","default_modifiers":{}},
    {"keywords":["酮症","酮体升高","ketoacidosis","酮尿"],"hpo_id":"HP:0012135","term_name":"酮症","default_modifiers":{}},
    {"keywords":["高血氨","血氨升高","ammonia","高氨血症"],"hpo_id":"HP:0003073","term_name":"高血氨","default_modifiers":{}},
    {"keywords":["肝大","肝肿大","hepatomegaly","肝脾肿大"],"hpo_id":"HP:0002240","term_name":"肝大","default_modifiers":{}},
    # ── 新增：神经 ──
    {"keywords":["共济失调","走路不稳","宽基步态","ataxia","步态不稳"],"hpo_id":"HP:0001251","term_name":"共济失调","default_modifiers":{}},
    {"keywords":["发育迟缓","运动发育迟缓","motor delay","发育落后"],"hpo_id":"HP:0001270","term_name":"运动发育迟缓","default_modifiers":{}},
    {"keywords":["语言发育迟缓","言语障碍","speech delay"],"hpo_id":"HP:0001263","term_name":"语言发育迟缓","default_modifiers":{}},
    {"keywords":["小头畸形","microcephaly","头围小"],"hpo_id":"HP:0000252","term_name":"小头畸形","default_modifiers":{}},
    {"keywords":["自闭症","孤独症","autism","社交障碍","刻板行为"],"hpo_id":"HP:0000729","term_name":"自闭症样行为","default_modifiers":{}},
    {"keywords":["听力下降","耳聋","hearing loss","感音神经性耳聋"],"hpo_id":"HP:0000365","term_name":"听力障碍","default_modifiers":{}},
    # ── 新增：心血管/呼吸 ──
    {"keywords":["心脏杂音","murmur","心前区杂音"],"hpo_id":"HP:0030148","term_name":"心脏杂音","default_modifiers":{}},
    {"keywords":["发绀","紫绀","cyanosis","口唇发紫"],"hpo_id":"HP:0000961","term_name":"发绀","default_modifiers":{}},
    {"keywords":["呼吸困难","气促","呼吸急促","dyspnea","tachypnea"],"hpo_id":"HP:0002098","term_name":"呼吸急促","default_modifiers":{}},
    {"keywords":["咳嗽","cough","阵发性咳嗽"],"hpo_id":"HP:0012735","term_name":"咳嗽","default_modifiers":{}},
    {"keywords":["发热","fever","高热","发烧"],"hpo_id":"HP:0001945","term_name":"发热","default_modifiers":{}},
    # ── 新增：消化道 ──
    {"keywords":["呕吐","vomiting","恶心","喷射性呕吐"],"hpo_id":"HP:0002013","term_name":"呕吐","default_modifiers":{}},
    {"keywords":["腹泻","diarrhea","水样便","稀便"],"hpo_id":"HP:0002014","term_name":"腹泻","default_modifiers":{}},
    {"keywords":["便秘","constipation","排便困难"],"hpo_id":"HP:0002019","term_name":"便秘","default_modifiers":{}},
    {"keywords":["腹痛","abdominal pain","肚子痛"],"hpo_id":"HP:0002027","term_name":"腹痛","default_modifiers":{}},
    # ── 新增：肾脏/电解质 ──
    {"keywords":["多尿","polyuria","尿频","尿量增多"],"hpo_id":"HP:0000103","term_name":"多尿","default_modifiers":{}},
    {"keywords":["多饮","polydipsia","烦渴","口渴多饮"],"hpo_id":"HP:0001959","term_name":"多饮","default_modifiers":{}},
    {"keywords":["蛋白尿","proteinuria","尿蛋白"],"hpo_id":"HP:0000093","term_name":"蛋白尿","default_modifiers":{}},
    {"keywords":["低钠","低钠血症","低血钠","hyponatremia"],"hpo_id":"HP:0002902","term_name":"低钠血症","default_modifiers":{}},
    # ── 新增：皮肤/眼 ──
    {"keywords":["皮疹","rash","红斑","多形红斑","斑丘疹"],"hpo_id":"HP:0000988","term_name":"皮疹","default_modifiers":{}},
    {"keywords":["白内障","cataract","晶体混浊"],"hpo_id":"HP:0000518","term_name":"白内障","default_modifiers":{}},
    {"keywords":["视神经萎缩","optic atrophy","视盘苍白"],"hpo_id":"HP:0000648","term_name":"视神经萎缩","default_modifiers":{}},
    {"keywords":["眼睑下垂","ptosis","上睑下垂"],"hpo_id":"HP:0000508","term_name":"眼睑下垂","default_modifiers":{}},
    # ── 新增：全身症状 ──
    {"keywords":["贫血","anemia","血红蛋白低"],"hpo_id":"HP:0001903","term_name":"贫血","default_modifiers":{}},
    {"keywords":["黄疸","jaundice","皮肤黄染","巩膜黄染"],"hpo_id":"HP:0000952","term_name":"黄疸","default_modifiers":{}},
    {"keywords":["低血压","hypotension","血压低","血压90/60"],"hpo_id":"HP:0002615","term_name":"低血压","default_modifiers":{}},
    {"keywords":["脾大","巨脾","splenomegaly","脾脏增大"],"hpo_id":"HP:0001744","term_name":"脾大","default_modifiers":{}},
    {"keywords":["肌酸激酶升高","CK升高","creatine kinase","肌酶升高"],"hpo_id":"HP:0003236","term_name":"肌酸激酶升高","default_modifiers":{}},
    {"keywords":["肝酶升高","转氨酶升高","ALT升高","AST升高"],"hpo_id":"HP:0002910","term_name":"肝酶升高","default_modifiers":{}},
    {"keywords":["嗜睡","昏睡","意识障碍","lethargy","昏迷"],"hpo_id":"HP:0004372","term_name":"意识障碍","default_modifiers":{}},
    {"keywords":["体重下降","消瘦","体重减轻","weight loss"],"hpo_id":"HP:0004325","term_name":"体重下降","default_modifiers":{}},
    {"keywords":["易疲劳","倦怠","乏力","fatigue","精神萎靡"],"hpo_id":"HP:0012378","term_name":"易疲劳","default_modifiers":{}},
    {"keywords":["身材矮小","矮小","short stature","生长迟缓"],"hpo_id":"HP:0004322","term_name":"身材矮小","default_modifiers":{}},
    {"keywords":["上呼吸道水肿"],"hpo_id":"HP:0000056","term_name":"上呼吸道水肿","default_modifiers":{}},
    {"keywords":["肠壁水肿"],"hpo_id":"HP:0000098","term_name":"肠壁水肿","default_modifiers":{}},
    {"keywords":["角膜混浊"],"hpo_id":"HP:0000123","term_name":"角膜混浊","default_modifiers":{}},
    {"keywords":["皮下水肿"],"hpo_id":"HP:0000137","term_name":"皮下水肿","default_modifiers":{}},
    {"keywords":["面部畸形"],"hpo_id":"HP:0000238","term_name":"面部畸形","default_modifiers":{}},
    {"keywords":["耳聋"],"hpo_id":"HP:0000380","term_name":"耳聋","default_modifiers":{}},
    {"keywords":["视网膜变性", "retinal degeneration"],"hpo_id":"HP:0000556","term_name":"视网膜变性","default_modifiers":{}},
    {"keywords":["视神经萎缩"],"hpo_id":"HP:0000639","term_name":"视神经萎缩","default_modifiers":{}},
    {"keywords":["眼睑下垂"],"hpo_id":"HP:0000646","term_name":"眼睑下垂","default_modifiers":{}},
    {"keywords":["自闭症行为"],"hpo_id":"HP:0000717","term_name":"自闭症行为","default_modifiers":{}},
    {"keywords":["低血压", "hypertension"],"hpo_id":"HP:0000822","term_name":"低血压","default_modifiers":{}},
    {"keywords":["肾上腺功能不全"],"hpo_id":"HP:0000836","term_name":"肾上腺功能不全","default_modifiers":{}},
    {"keywords":["肾素-醛固酮系统激活"],"hpo_id":"HP:0000863","term_name":"肾素-醛固酮系统激活","default_modifiers":{}},
    {"keywords":["垂体腺瘤"],"hpo_id":"HP:0000951","term_name":"垂体腺瘤","default_modifiers":{}},
    {"keywords":["皮肤色素沉着"],"hpo_id":"HP:0000953","term_name":"皮肤色素沉着","default_modifiers":{}},
    {"keywords":["甲状旁腺功能亢进"],"hpo_id":"HP:0000957","term_name":"甲状旁腺功能亢进","default_modifiers":{}},
    {"keywords":["咳嗽"],"hpo_id":"HP:0000960","term_name":"咳嗽","default_modifiers":{}},
    {"keywords":["胰腺神经内分泌肿瘤"],"hpo_id":"HP:0000967","term_name":"胰腺神经内分泌肿瘤","default_modifiers":{}},
    {"keywords":["皮肤色素沉着"],"hpo_id":"HP:0001010","term_name":"皮肤色素沉着","default_modifiers":{}},
    {"keywords":["惊厥"],"hpo_id":"HP:0001250","term_name":"惊厥","default_modifiers":{}},
    {"keywords":["颅骨增厚"],"hpo_id":"HP:0001256","term_name":"颅骨增厚","default_modifiers":{}},
    {"keywords":["痉挛性截瘫", "spastic paraplegia"],"hpo_id":"HP:0001257","term_name":"痉挛性截瘫","default_modifiers":{}},
    {"keywords":["痴呆"],"hpo_id":"HP:0001260","term_name":"痴呆","default_modifiers":{}},
    {"keywords":["发育倒退"],"hpo_id":"HP:0001268","term_name":"发育倒退","default_modifiers":{}},
    {"keywords":["新生儿低血糖"],"hpo_id":"HP:0001272","term_name":"新生儿低血糖","default_modifiers":{}},
    {"keywords":["肌张力增高"],"hpo_id":"HP:0001276","term_name":"肌张力增高","default_modifiers":{}},
    {"keywords":["心肺功能不全"],"hpo_id":"HP:0001283","term_name":"心肺功能不全","default_modifiers":{}},
    {"keywords":["肌张力低下"],"hpo_id":"HP:0001290","term_name":"肌张力低下","default_modifiers":{}},
    {"keywords":["刻板行为"],"hpo_id":"HP:0001298","term_name":"刻板行为","default_modifiers":{}},
    {"keywords":["肌无力", "muscle weakness"],"hpo_id":"HP:0001324","term_name":"肌无力","default_modifiers":{}},
    {"keywords":["眼球运动异常"],"hpo_id":"HP:0001332","term_name":"眼球运动异常","default_modifiers":{}},
    {"keywords":["肌阵挛"],"hpo_id":"HP:0001347","term_name":"肌阵挛","default_modifiers":{}},
    {"keywords":["肝脾肿大"],"hpo_id":"HP:0001382","term_name":"肝脾肿大","default_modifiers":{}},
    {"keywords":["肥胖"],"hpo_id":"HP:0001392","term_name":"肥胖","default_modifiers":{}},
    {"keywords":["脾肿大"],"hpo_id":"HP:0001607","term_name":"脾肿大","default_modifiers":{}},
    {"keywords":["心电图异常"],"hpo_id":"HP:0001624","term_name":"心电图异常","default_modifiers":{}},
    {"keywords":["肺充血"],"hpo_id":"HP:0001627","term_name":"肺充血","default_modifiers":{}},
    {"keywords":["骨畸形"],"hpo_id":"HP:0001637","term_name":"骨畸形","default_modifiers":{}},
    {"keywords":["扩张型心肌病"],"hpo_id":"HP:0001639","term_name":"扩张型心肌病","default_modifiers":{}},
    {"keywords":["心脏杂音", "cardiomegaly"],"hpo_id":"HP:0001640","term_name":"心脏杂音","default_modifiers":{}},
    {"keywords":["空腹低血糖"],"hpo_id":"HP:0001939","term_name":"空腹低血糖","default_modifiers":{}},
    {"keywords":["发绀"],"hpo_id":"HP:0001947","term_name":"发绀","default_modifiers":{}},
    {"keywords":["糖尿病"],"hpo_id":"HP:0001956","term_name":"糖尿病","default_modifiers":{}},
    {"keywords":["基底节异常信号"],"hpo_id":"HP:0001984","term_name":"基底节异常信号","default_modifiers":{}},
    {"keywords":["肝肿大"],"hpo_id":"HP:0001994","term_name":"肝肿大","default_modifiers":{}},
    {"keywords":["基底节区MRI异常信号"],"hpo_id":"HP:0002011","term_name":"基底节区MRI异常信号","default_modifiers":{}},
    {"keywords":["腹痛"],"hpo_id":"HP:0002017","term_name":"腹痛","default_modifiers":{}},
    {"keywords":["喂养困难"],"hpo_id":"HP:0002033","term_name":"喂养困难","default_modifiers":{}},
    {"keywords":["振动觉减退"],"hpo_id":"HP:0002060","term_name":"振动觉减退","default_modifiers":{}},
    {"keywords":["肺部啰音"],"hpo_id":"HP:0002094","term_name":"肺部啰音","default_modifiers":{}},
    {"keywords":["乳酸性酸中毒"],"hpo_id":"HP:0002154","term_name":"乳酸性酸中毒","default_modifiers":{}},
    {"keywords":["膀胱功能障碍"],"hpo_id":"HP:0002169","term_name":"膀胱功能障碍","default_modifiers":{}},
    {"keywords":["VLCFA升高"],"hpo_id":"HP:0002315","term_name":"VLCFA升高","default_modifiers":{}},
    {"keywords":["脑白质MRI异常"],"hpo_id":"HP:0002500","term_name":"脑白质MRI异常","default_modifiers":{}},
    {"keywords":["脊髓畸形"],"hpo_id":"HP:0002750","term_name":"脊髓畸形","default_modifiers":{}},
    {"keywords":["低氧血症"],"hpo_id":"HP:0002788","term_name":"低氧血症","default_modifiers":{}},
    {"keywords":["低钾血症"],"hpo_id":"HP:0002900","term_name":"低钾血症","default_modifiers":{}},
    {"keywords":["低镁血症"],"hpo_id":"HP:0002908","term_name":"低镁血症","default_modifiers":{}},
    {"keywords":["尿钾升高"],"hpo_id":"HP:0003118","term_name":"尿钾升高","default_modifiers":{}},
    {"keywords":["低钠血症"],"hpo_id":"HP:0003128","term_name":"低钠血症","default_modifiers":{}},
    {"keywords":["血清CK升高"],"hpo_id":"HP:0003198","term_name":"血清CK升高","default_modifiers":{}},
    {"keywords":["代谢性碱中毒"],"hpo_id":"HP:0003557","term_name":"代谢性碱中毒","default_modifiers":{}},
    {"keywords":["假性肌肥大"],"hpo_id":"HP:0003745","term_name":"假性肌肥大","default_modifiers":{}},
    {"keywords":["易疲劳"],"hpo_id":"HP:0003808","term_name":"易疲劳","default_modifiers":{}},
    {"keywords":["多饮"],"hpo_id":"HP:0004360","term_name":"多饮","default_modifiers":{}},
    {"keywords":["上行性麻痹"],"hpo_id":"HP:0006986","term_name":"上行性麻痹","default_modifiers":{}},
    {"keywords":["呼吸急促"],"hpo_id":"HP:0011947","term_name":"呼吸急促","default_modifiers":{}},
    {"keywords":["多尿"],"hpo_id":"HP:0011952","term_name":"多尿","default_modifiers":{}},
    {"keywords":["喂养困难"],"hpo_id":"HP:0011968","term_name":"喂养困难","default_modifiers":{}}]

# 修饰符关键词映射
MODIFIER_KEYWORDS = {
    "进行性": {"temporal_pattern": "progressive"},
    "progressive": {"temporal_pattern": "progressive"},
    "先天性": {"temporal_pattern": "congenital"},
    "发作性": {"temporal_pattern": "relapsing"},
    "反复": {"temporal_pattern": "relapsing"},
    "持续性": {"temporal_pattern": "persistent"},
    "急性": {"temporal_pattern": "acute"},
    "慢性": {"temporal_pattern": "chronic_progressive"},
    "全身性": {"distribution": "generalized"},
    "全身": {"distribution": "generalized"},
    "generalized": {"distribution": "generalized"},
    "近端": {"distribution": "proximal"},
    "远端": {"distribution": "distal"},
    "双侧": {"laterality": "bilateral"},
    "bilateral": {"laterality": "bilateral"},
    "左侧": {"laterality": "left"},
    "右侧": {"laterality": "right"},
    "重度": {"severity": "severe"},
    "严重": {"severity": "severe"},
    "中度": {"severity": "moderate"},
    "轻度": {"severity": "mild"},
    "severe": {"severity": "severe"},
    "moderate": {"severity": "moderate"},
    "mild": {"severity": "mild"},
}

# 发病年龄提取正则
ONSET_AGE_PATTERNS = [
    (re.compile(r"(\d+)\s*月龄"), "months"),
    (re.compile(r"(\d+)\s*个月"), "months"),
    (re.compile(r"(\d+)\s*岁"), "years"),
    (re.compile(r"(\d+)\s*years?"), "years"),
    (re.compile(r"(\d+)\s*days?"), "days"),
]


def _extract_onset_age(text: str) -> tuple[float | None, str | None]:
    """从文本提取发病年龄，返回 (age_value, age_unit)。"""
    for pattern, unit in ONSET_AGE_PATTERNS:
        m = pattern.search(text)
        if m:
            return (float(m.group(1)), unit)
    return (None, None)


def _extract_modifiers(text: str, defaults: dict[str, str]) -> PhenotypeModifier:
    """从文本提取修饰符，合并默认值。"""
    merged = dict(defaults)
    text_lower = text.lower()
    for kw, mods in MODIFIER_KEYWORDS.items():
        if kw in text or kw.lower() in text_lower:
            merged.update(mods)
    return PhenotypeModifier(
        distribution=merged.get("distribution"),
        temporal_pattern=merged.get("temporal_pattern"),
        severity=merged.get("severity"),
        laterality=merged.get("laterality"),
        progression_rate=merged.get("progression_rate"),
    )


def extract_phenotypes(text: str) -> list[PhenotypeVector]:
    """从临床文本提取表型向量列表。"""
    vectors: list[PhenotypeVector] = []
    seen_hpo: set[str] = set()

    for entry in PHENOTYPE_DICTIONARY:
        matched = False
        for kw in entry["keywords"]:
            if kw in text or kw.lower() in text.lower():
                matched = True
                break
        if not matched:
            continue

        hpo_id = entry["hpo_id"]
        if hpo_id in seen_hpo:
            continue
        seen_hpo.add(hpo_id)

        modifiers = _extract_modifiers(text, entry.get("default_modifiers", {}))
        onset_age, onset_unit = _extract_onset_age(text)

        vectors.append(PhenotypeVector(
            hpo_id=hpo_id,
            term_name=entry["term_name"],
            modifiers=[modifiers],
            presence=PresenceStatus.PRESENT,
            onset_age=onset_age,
            onset_age_unit=onset_unit,
            raw_description=kw if (kw := next((k for k in entry["keywords"] if k in text), "")) else "",
        ))

    return vectors


def extract_demographic(text: str) -> dict[str, Any]:
    """从文本提取人口学信息。"""
    demo: dict[str, Any] = {}

    # 性别
    if any(kw in text for kw in ["男婴", "男孩", "患儿男", "男性"]):
        demo["sex"] = "male"
    elif any(kw in text for kw in ["女婴", "女孩", "患儿女", "女性"]):
        demo["sex"] = "female"

    # 年龄
    age, unit = _extract_onset_age(text)
    if age is not None:
        demo["age"] = age
        demo["age_unit"] = unit or "years"

    return demo


# ========== Agent 入口 ==========

def run(state: dict | Any) -> dict:
    """Layer 1 入口：从临床文本提取表型向量。

    同步版本（不调 KnowS），用于 LangGraph 节点。
    KnowS 检索在异步路径中由 _run_with_knows 处理。
    """
    if hasattr(state, "current_user_message"):
        text = state.current_user_message or ""
        session_id = getattr(state, "session_id", "")
    else:
        text = state.get("current_user_message", "") if isinstance(state, dict) else ""
        session_id = state.get("session_id", "") if isinstance(state, dict) else ""

    vectors = extract_phenotypes(text)
    demographic = extract_demographic(text)

    profile = PhenotypeProfile(
        patient_id=session_id,
        vectors=vectors,
        raw_text=text,
        demographic=demographic,
    )

    return {
        "phenotype_profile": profile,
        "patient_profile": {"raw_input": text, **demographic},
    }


async def run_with_knows(
    state: dict | Any,
    knows_client: KnowsClient,
    llm_gateway: LLMGateway | None = None,
) -> dict:
    """Layer 1 异步版本：LLM 表型提取 + KnowS 检索验证。

    LLM 优先路径：用 LLM 做表型 NER（更精准，支持复杂表述）
    词典兜底路径：LLM 失败时降级到关键词词典（保证可用性）

    KnowS 策略（PRD §4.2 Layer 1）：
    - 源：guide
    - 查询：核心表型术语
    - 目的：表型-HPO 映射参考
    """
    text = (
        state.current_user_message
        if hasattr(state, "current_user_message")
        else state.get("current_user_message", "")
    )
    session_id = (
        getattr(state, "session_id", "")
        if hasattr(state, "session_id")
        else state.get("session_id", "")
    )

    # ===== LLM 表型提取（主力，覆盖全 HPO）=====
    llm_used = False
    llm_vectors: list[PhenotypeVector] = []
    if llm_gateway is not None:
        try:
            llm_profile = await _extract_phenotypes_with_llm(
                text, session_id, llm_gateway
            )
            llm_vectors = llm_profile.vectors
            llm_used = True
        except Exception:
            llm_vectors = []

    # ===== 词典提取（兜底，补充 LLM 遗漏的常见表型）=====
    dict_vectors = extract_phenotypes(text)
    demographic = extract_demographic(text)

    # 合并去重：**LLM 为底座，词典补充**
    merged = list(llm_vectors)
    seen_hpo = {v.hpo_id for v in merged if v.hpo_id and not v.hpo_id.startswith("LLM:")}
    seen_terms = {v.term_name for v in merged}
    for dv in dict_vectors:
        key = dv.hpo_id if dv.hpo_id and not dv.hpo_id.startswith("LLM:") else dv.term_name
        if key and key not in seen_hpo and dv.term_name not in seen_terms:
            merged.append(dv)
            seen_hpo.add(key)
            seen_terms.add(dv.term_name)

    profile = PhenotypeProfile(
        patient_id=session_id,
        vectors=merged,
        raw_text=text,
        demographic=demographic,
    )

    result = {
        "phenotype_profile": profile,
        "patient_profile": {"raw_input": text, **demographic},
        "llm_extracted": llm_used,
        "llm_supplement_count": len(llm_vectors),
    }

    if not profile.vectors:
        return result

    # ===== KnowS 检索（不变）=====
    top_terms = [v.term_name for v in profile.vectors[:3]]
    query = " ".join(top_terms) + " 罕见病 表型 HPO"

    try:
        evidences = await knows_client.search_single_source(
            source=LAYER_SOURCES["layer1"][0],
            query=query,
            retrieved_layer="layer1",
            top_k=5,
        )
        if evidences:
            evidence_ids = [ev.id for ev in evidences]
            result["current_layer_evidence_ids"] = evidence_ids
            result["current_layer_evidences"] = evidences
    except Exception:
        pass

    return result


# ========== LLM 表型 NER ==========

_LLM_SYSTEM_PROMPT = """你是一位罕见病临床表型分析专家。请从患者临床描述中提取结构化表型信息，映射到 HPO（Human Phenotype Ontology）标准术语。

## 输出要求
请输出 JSON 数组，每个元素是一个表型向量，包含：
- hpo_id: HPO 标准 ID（格式 HP:xxxxxxx，7位数字）
- term_name: 术语名称（中文）
- presence: present / absent / unknown
- onset_age: 发病年龄数值（数字，无则 null）
- onset_age_unit: years / months / days / weeks（无则 null）
- severity: mild / moderate / severe / life_threatening（无则 null）
- modifiers: 修饰符对象，含 distribution/temporal_pattern/laterality/progression_rate（无则省略键）

## 规则
1. **必须提取所有**明确提及或强烈暗示的表型，不要遗漏，至少提取 3 个以上
2. 必须使用真实的 HPO ID（如 HP:0001250 肌张力低下、HP:0002154 乳酸酸中毒）
3. 如果无法确定 HPO ID，给最接近的术语，hpo_id 留空字符串
4. 输出纯 JSON 对象，不要任何解释文字
5. 必须用 {"phenotypes": [...]} 包装数组（顶层必须是对象），phenotypes 数组含所有表型

## 输出格式（示例）
输入: "男婴3月龄肌张力低下喂养困难乳酸酸中毒"
输出: {"phenotypes": [
  {"hpo_id": "HP:0001290", "term_name": "肌张力低下", "presence": "present", "onset_age": 3, "onset_age_unit": "months", "severity": null, "modifiers": {}},
  {"hpo_id": "HP:0002033", "term_name": "喂养困难", "presence": "present", "onset_age": 3, "onset_age_unit": "months", "severity": null, "modifiers": {}},
  {"hpo_id": "HP:0002154", "term_name": "乳酸性酸中毒", "presence": "present", "onset_age": 3, "onset_age_unit": "months", "severity": "severe", "modifiers": {}}
]}

## 常见 HPO 术语参考
- HP:0001290 肌张力低下 / HP:0002033 喂养困难 / HP:0002154 乳酸性酸中毒
- HP:0002011 基底节区MRI异常信号 / HP:0001332 眼球运动异常 / HP:0001250 癫痫发作
- HP:0001268 发育倒退 / HP:0001010 皮肤色素沉着 / HP:0002315 VLCFA升高
- HP:0002500 脑白质MRI异常 / HP:0001257 痉挛性截瘫 / HP:0002900 低钾血症
- HP:0002908 低镁血症 / HP:0003557 代谢性碱中毒 / HP:0003118 尿钾升高
- HP:0000863 肾素-醛固酮系统激活 / HP:0000556 视网膜变性 / HP:0001324 肌无力"""


async def _extract_phenotypes_with_llm(
    text: str,
    session_id: str,
    llm_gateway: LLMGateway,
) -> PhenotypeProfile:
    """用 LLM 从临床文本提取表型向量。

    Raises:
        RuntimeError: LLM 调用失败
        ValueError: LLM 输出无法解析
    """
    messages = [
        {"role": "system", "content": _LLM_SYSTEM_PROMPT},
        {"role": "user", "content": f"## 患者临床描述\n{text}\n\n请提取表型向量。"},
    ]

    result = await llm_gateway.chat_json("phenotype_analyzer", messages, temperature=0.1)

    # 兼容多种返回形态（flash 小模型可能不严格遵循数组包装）：
    # - {"phenotypes": [...]} 标准包装
    # - [...] 直接数组
    # - {"hpo_id":...} 单个表型对象（小模型常见退化）
    if isinstance(result, dict):
        # 找数组型字段
        for key in ("phenotypes", "data", "result", "items", "vectors"):
            val = result.get(key)
            if isinstance(val, list):
                items = val
                break
        else:
            # 没有数组字段 → 整个 dict 当作单个表型
            if any(k in result for k in ("hpo_id", "term_name", "presence")):
                items = [result]
            else:
                items = []
    elif isinstance(result, list):
        items = result
    else:
        raise ValueError(f"LLM 应返回 JSON 对象/数组，实际: {type(result)}")

    vectors: list[PhenotypeVector] = []
    seen_hpo: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        hpo_id = item.get("hpo_id", "") or ""
        term_name = item.get("term_name", "") or ""
        if not term_name and not hpo_id:
            continue
        if hpo_id and hpo_id in seen_hpo:
            continue
        if hpo_id:
            seen_hpo.add(hpo_id)

        # 修饰符
        mods_raw = item.get("modifiers", {}) or {}
        modifier = PhenotypeModifier(
            distribution=mods_raw.get("distribution"),
            temporal_pattern=mods_raw.get("temporal_pattern"),
            severity=mods_raw.get("severity") or item.get("severity"),
            laterality=mods_raw.get("laterality"),
            progression_rate=mods_raw.get("progression_rate"),
        )

        onset_age = item.get("onset_age")
        onset_age_unit = item.get("onset_age_unit")
        presence = item.get("presence", "present")

        vectors.append(PhenotypeVector(
            hpo_id=hpo_id or f"LLM:{term_name}",
            term_name=term_name,
            modifiers=[modifier],
            presence=presence if isinstance(presence, str) else "present",
            onset_age=float(onset_age) if onset_age is not None else None,
            onset_age_unit=onset_age_unit,
            raw_description="",
        ))

    # 人口学仍用词典提取（LLM 只负责表型）
    demographic = extract_demographic(text)

    return PhenotypeProfile(
        patient_id=session_id,
        vectors=vectors,
        raw_text=text,
        demographic=demographic,
    )
