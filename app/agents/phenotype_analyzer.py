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
    # ── 新增：头面/五官/呼吸道（已用频率表验证 ID 真实）──
    {"keywords":["头痛","头疼","偏头痛","migraine","headache","胀痛","搏动样痛"],"hpo_id":"HP:0002315","term_name":"头痛","default_modifiers":{}},
    {"keywords":["鼻塞","鼻不通气","鼻腔阻塞","nasal obstruction","鼻堵"],"hpo_id":"HP:0000242","term_name":"鼻塞","default_modifiers":{}},
    {"keywords":["鼻出血","鼻衄","鼻涕带血","鼻涕中带血","epistaxis","鼻血"],"hpo_id":"HP:0000233","term_name":"鼻出血","default_modifiers":{}},
    {"keywords":["咳痰","咳痰增多","痰多","多痰","咳嗽咳痰","sputum"],"hpo_id":"HP:0002094","term_name":"咳痰","default_modifiers":{}},
    {"keywords":["鼻充血","鼻黏膜充血","nasal congestion","鼻黏膜红"],"hpo_id":"HP:0000245","term_name":"鼻充血","default_modifiers":{}},
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
    {"keywords":["喂养困难"],"hpo_id":"HP:0011968","term_name":"喂养困难","default_modifiers":{}},
]
# 为常见临床表述提供更多同义词/别名/拼音/缩写映射
SYNONYM_EXTENSIONS: dict[str, list[str]] = {
    # 神经肌肉
    "HP:0001290": ["肌张力低", "肌张力减弱", "floppy", "松软", "软婴儿", "低张力"],
    "HP:0001250": ["抽搐", "惊厥", "羊癫疯", "seizure", "抽风", "突然倒地"],
    "HP:0001268": ["发育退步", "以前会现在不会", "技能丧失", "regression"],
    "HP:0001270": ["发育落后", "大运动落后", "不会抬头", "不会坐", "不会走", "motor delay"],
    "HP:0001263": ["说话晚", "不会说话", "语言落后", "speech delay", "言语少"],
    "HP:0001251": ["走路不稳", "摇摇晃晃", "醉汉步态", "ataxia", "共济失调步态"],
    "HP:0001332": ["眼球乱转", "眼球跳动", "眼睛抖动", "nystagmus", "眼球震颤"],
    "HP:0001324": ["没劲", "抬不起胳膊", "举不起来", "weakness", "肌力下降"],
    "HP:0001347": ["肌肉跳动", "肌阵挛", "myoclonus"],
    "HP:0001257": ["腿硬", "剪刀步态", "spastic", "痉挛", "肌张力高", "腱反射亢进"],

    # 代谢/生化
    "HP:0002154": ["乳酸高", "乳酸高值", "血乳酸", "lactic acidosis", "乳酸酸中毒"],
    "HP:0003073": ["血氨高", "ammonia", "高氨血症"],
    "HP:0001943": ["血糖低", "低血糖发作", "hypoglycemia", "低血糖症"],
    "HP:0003074": ["血糖高", "高血糖", "hyperglycemia", "糖尿病"],
    "HP:0012135": ["酮症酸中毒", "酮体", "ketoacidosis", "酮尿"],
    "HP:0002910": ["转氨酶高", "ALT高", "AST高", "肝酶升高", "肝功能异常"],
    "HP:0002240": ["肝脏大", "肝大", "hepatomegaly", "肝脾大"],
    "HP:0001744": ["脾脏大", "脾大", "splenomegaly", "巨脾"],
    "HP:0003236": ["CK高", "肌酶高", "creatine kinase", "肌酸激酶升高"],
    "HP:0002900": ["钾低", "血钾低", "低钾血症", "hypokalemia"],
    "HP:0002908": ["镁低", "血镁低", "hypomagnesemia"],
    "HP:0003557": ["碱中毒", "代谢性碱中毒", "metabolic alkalosis", "HCO3高"],
    "HP:0003118": ["尿钾高", "尿钾排泄多", "尿钾升高"],
    "HP:0000863": ["肾素高", "醛固酮高", "肾素醛固酮", "RAAS激活"],

    # 影像/结构
    "HP:0002011": ["基底节病变", "壳核信号", "苍白球信号", "basal ganglia", "T2高信号"],
    "HP:0002500": ["白质病变", "脱髓鞘", "white matter", "脑白质异常", "白质疏松"],
    "HP:0000556": ["视网膜问题", "视网膜病变", "retinal", "视力问题"],
    "HP:0000518": ["白内障", "晶体混浊", "cataract"],
    "HP:0000648": ["视神经萎缩", "视盘苍白", "optic atrophy"],

    # 皮肤/其他
    "HP:0001010": ["皮肤黑", "皮肤颜色深", "hyperpigmentation", "色素沉着", "皮肤色沉"],
    "HP:0000988": ["红疹", "皮疹", "rash", "红斑", "斑丘疹", "皮肤疹"],
    "HP:0000952": ["皮肤黄", "巩膜黄", "黄疸", "jaundice", "皮肤黄染"],
    "HP:0000137": ["浮肿", "水肿", "edema", "皮下肿"],
    "HP:0000098": ["肠子肿", "肠壁增厚", "肠壁水肿"],
    "HP:0000056": ["喉咙肿", "上呼吸道水肿", "喉头水肿"],
    "HP:0000123": ["角膜白", "角膜混浊", "corneal opacity"],
    "HP:0000238": ["脸型异常", "面部畸形", "特殊面容", "face anomaly"],
    "HP:0000380": ["听不到", "耳聋", "hearing loss", "感音神经性耳聋"],
    "HP:0000508": ["眼皮抬不起来", "上睑下垂", "ptosis"],
    "HP:0000639": ["视神经问题", "视神经萎缩", "optic atrophy"],

    # 全身/其他
    "HP:0001903": ["贫血", "血红蛋白低", "anemia", "血色素低"],
    "HP:0001945": ["发烧", "发热", "fever", "高热"],
    "HP:0002098": ["喘", "呼吸困难", "dyspnea", "呼吸急促", "气促", "tachypnea"],
    "HP:0012735": ["咳", "咳嗽", "cough"],
    "HP:0002013": ["吐", "呕吐", "vomiting", "恶心"],
    "HP:0002014": ["拉稀", "腹泻", "diarrhea", "水样便"],
    "HP:0002019": ["便秘", "排便困难", "constipation"],
    "HP:0002027": ["肚子疼", "腹痛", "abdominal pain"],
    "HP:0000103": ["尿多", "多尿", "polyuria", "尿频"],
    "HP:0001959": ["喝水多", "多饮", "polydipsia", "烦渴"],
    "HP:0000093": ["尿蛋白", "蛋白尿", "proteinuria"],
    "HP:0002902": ["钠低", "低钠血症", "hyponatremia", "低血钠"],
    "HP:0002615": ["血压低", "低血压", "hypotension"],
    "HP:0004372": ["昏迷", "意识不清", "lethargy", "意识障碍", "嗜睡"],
    "HP:0004325": ["瘦", "体重下降", "weight loss", "消瘦"],
    "HP:0012378": ["累", "乏力", "fatigue", "易疲劳", "精神差"],
    "HP:0004322": ["矮", "身材矮小", "short stature", "生长慢"],
    "HP:0000729": ["自闭", "孤独症", "autism", "社交差", "刻板"],
    "HP:0000365": ["听力差", "耳聋", "hearing loss"],
    "HP:0000252": ["头小", "小头", "microcephaly", "头围小"],
    "HP:0000961": ["紫", "发紫", "发绀", "cyanosis", "口唇青紫"],
    "HP:0001624": ["心电图异常", "心电图问题"],
    "HP:0001627": ["肺充血", "肺血多"],
    "HP:0001639": ["心脏大", "扩心病", "扩张型心肌病"],
    "HP:0001640": ["心脏杂音", "murmur", "心杂音"],
    "HP:0002750": ["脊髓问题", "脊髓畸形"],
    "HP:0002788": ["氧低", "低氧血症", "缺氧"],
    "HP:0003128": ["钠低", "低钠血症", "hyponatremia"],
    "HP:0003198": ["CK高", "血清CK升高"],
    "HP:0003745": ["假性肌肥大", "肌肉假肥大"],
    "HP:0003808": ["易累", "易疲劳"],
    "HP:0004360": ["多饮", "喝水多"],
    "HP:0006986": ["上行性麻痹", "ascending paralysis"],
    "HP:0011947": ["呼吸急促", "呼吸快"],
    "HP:0011952": ["多尿", "尿多"],
    "HP:0011968": ["喂养困难", "吃奶差"],
}

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
    """从临床文本提取表型向量列表（支持精确匹配 + 模糊匹配）。"""
    vectors: list[PhenotypeVector] = []
    seen_hpo: set[str] = set()
    text_lower = text.lower()

    # ===== 第一轮：精确匹配 =====
    for entry in PHENOTYPE_DICTIONARY:
        matched = False
        matched_kw = ""
        for kw in entry["keywords"]:
            if kw in text or kw.lower() in text_lower:
                matched = True
                matched_kw = kw
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
            raw_description=matched_kw,
        ))

    # ===== 第二轮：模糊匹配（同义词扩展 + 部分匹配）=====
    fuzzy_matched_hpo: set[str] = set()
    for hpo_id, synonyms in SYNONYM_EXTENSIONS.items():
        if hpo_id in seen_hpo or hpo_id in fuzzy_matched_hpo:
            continue
        for syn in synonyms:
            syn_lower = syn.lower()
            # 支持部分匹配：只要同义词出现在文本中即认为匹配
            if syn in text or syn_lower in text_lower:
                # 查找该 HPO 的标准词条
                entry = next((e for e in PHENOTYPE_DICTIONARY if e["hpo_id"] == hpo_id), None)
                if entry is None:
                    # 词典中没有，创建一个最小条目
                    entry = {
                        "hpo_id": hpo_id,
                        "term_name": hpo_id,  # 临时用 ID，后续 LLM 会修正
                        "keywords": [syn],
                        "default_modifiers": {},
                    }
                fuzzy_matched_hpo.add(hpo_id)
                modifiers = _extract_modifiers(text, entry.get("default_modifiers", {}))
                onset_age, onset_unit = _extract_onset_age(text)
                vectors.append(PhenotypeVector(
                    hpo_id=hpo_id,
                    term_name=entry["term_name"],
                    modifiers=[modifiers],
                    presence=PresenceStatus.PRESENT,
                    onset_age=onset_age,
                    onset_age_unit=onset_unit,
                    raw_description=syn,
                ))
                break  # 一个 HPO 只匹配一次

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
    """Layer 1 异步版本：LLM 表型提取 + 词典兜底 + KnowS 检索验证。

    提取策略（两路并行，按置信度择优合并）：
    - LLM 主力路径：要求返回 {"phenotypes": [...]}，至少 3 项
    - 词典兜底路径：LLM 失败 / 返回少于 3 项时，以词典结果为底座补充

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

    # ===== LLM 表型提取（主力路径，要求 ≥5 项）=====
    LLM_MIN_THRESHOLD = 5
    llm_used = False
    llm_below_threshold = False
    llm_err: str | None = None
    llm_vectors: list[PhenotypeVector] = []
    if llm_gateway is not None:
        try:
            llm_profile = await _extract_phenotypes_with_llm(
                text, session_id, llm_gateway
            )
            llm_vectors = llm_profile.vectors
            llm_used = True
            # 不达 5 项基线视为「LLM 不可靠」，词典兜底打底
            if len(llm_vectors) < LLM_MIN_THRESHOLD:
                llm_below_threshold = True
        except Exception as e:
            llm_vectors = []
            llm_below_threshold = True
            llm_err = f"{type(e).__name__}: {e}"

    # ===== 词典兜底路径（LLM 失败 / 少于 5 项时以此为底座）=====
    dict_vectors = extract_phenotypes(text)
    demographic = extract_demographic(text)

    # ===== 合并去重：置信度择优 =====
    # 策略：
    # - 若 LLM ≥5 项：LLM 为底座，词典补充遗漏
    # - 若 LLM <5 项或失败：词典为底座，LLM 补充（若有少量结果）
    if llm_used and not llm_below_threshold:
        merged = list(llm_vectors)
        supplement = dict_vectors
    else:
        # 词典兜底为主
        merged = list(dict_vectors)
        supplement = llm_vectors

    seen_hpo: set[str] = set()
    seen_terms: set[str] = set()
    for v in merged:
        if v.hpo_id and not v.hpo_id.startswith("LLM:"):
            seen_hpo.add(v.hpo_id)
        if v.term_name:
            seen_terms.add(v.term_name)

    for dv in supplement:
        dict_key = dv.hpo_id if dv.hpo_id and not dv.hpo_id.startswith("LLM:") else dv.term_name
        if dict_key and dict_key not in seen_hpo and dv.term_name not in seen_terms:
            merged.append(dv)
            if dict_key:
                seen_hpo.add(dict_key)
            if dv.term_name:
                seen_terms.add(dv.term_name)

    profile = PhenotypeProfile(
        patient_id=session_id,
        vectors=merged,
        raw_text=text,
        demographic=demographic,
    )

    # ===== 日志：LLM vs 词典提取统计 =====
    import logging
    _logger = logging.getLogger(__name__)
    log_payload = {
        "layer": "phenotype",
        "session_id": session_id,
        "llm_used": llm_used,
        "llm_count": len(llm_vectors),
        "llm_below_threshold": llm_below_threshold,
        "fallback_used": llm_below_threshold,
        "dict_count": len(dict_vectors),
        "merged_count": len(merged),
        "text_length": len(text),
    }
    if llm_err:
        log_payload["llm_error"] = llm_err
    if llm_used and len(llm_vectors) < 3:
        log_payload["llm_warning"] = (
            f"LLM 仅提取 {len(llm_vectors)} 项（<3 基线），已启用词典兜底为底座"
        )
    _logger.info("phenotype_layer1_extraction", extra=log_payload)

    result = {
        "phenotype_profile": profile,
        "patient_profile": {"raw_input": text, **demographic},
        "llm_extracted": llm_used,
        "llm_below_threshold": llm_below_threshold,
        "llm_supplement_count": len(llm_vectors),
        "layer1_metrics": {
            "llm_count": len(llm_vectors),
            "dict_count": len(dict_vectors),
            "merged_count": len(merged),
            "llm_below_threshold": llm_below_threshold,
            "fallback_base": llm_below_threshold,
            "llm_error": llm_err,
        },
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

## 核心任务
从临床文本中**全面、无遗漏**地提取所有表型，包括：
1. **明确提及**的症状、体征、检查异常
2. **强烈暗示**的表型（如"软"暗示肌张力低下，"吃奶差"暗示喂养困难）
3. **系统层面**的表现（神经、代谢、心血管、呼吸、消化、肾脏、皮肤、眼、耳等各系统）

## 输出要求
请输出 JSON 对象，顶层必须是 {"phenotypes": [...]}，数组包含 5-15 个表型向量：
- hpo_id: HPO 标准 ID（格式 HP:xxxxxxx，7位数字，尽量真实）
- term_name: 术语名称（中文）
- presence: present / absent / unknown（默认为 present）
- onset_age: 发病年龄数值（数字，无则 null）
- onset_age_unit: years / months / days / weeks（无则 null）
- severity: mild / moderate / severe / life_threatening（无则 null）
- modifiers: 修饰符对象，含 distribution/temporal_pattern/laterality/progression_rate（无则省略键）

## 规则（必须遵守）
1. **数量要求**：至少提取 5 个以上表型，宁多勿少
2. **覆盖要求**：必须覆盖多个系统（如神经 + 代谢 + 影像 + 其他），不要只提取 1-2 个
3. **暗示推断**：根据临床描述推断隐含表型（如"乳酸酸中毒"暗示代谢异常，"基底节T2高信号"暗示神经影像异常）
4. **HPO 映射**：尽量使用真实 HPO ID，常见参考：
   - HP:0001290 肌张力低下 / HP:0002033 喂养困难 / HP:0002154 乳酸性酸中毒
   - HP:0002011 基底节区MRI异常信号 / HP:0001332 眼球运动异常 / HP:0001250 癫痫发作
   - HP:0001268 发育倒退 / HP:0001270 运动发育迟缓 / HP:0001263 语言发育迟缓
   - HP:0002500 脑白质MRI异常 / HP:0001257 痉挛性截瘫 / HP:0001324 肌无力
   - HP:0002900 低钾血症 / HP:0003557 代谢性碱中毒 / HP:0000863 肾素-醛固酮系统激活
   - HP:0001010 皮肤色素沉着 / HP:0000556 视网膜变性 / HP:0000518 白内障
5. **输出格式**：纯 JSON，不要任何解释文字或 markdown 代码块
6. **包装格式**：顶层必须是 {"phenotypes": [...]}， phenotypes 数组含所有表型

## 示例
输入: "男婴3月龄，进行性肌张力低下，喂养困难，乳酸性酸中毒，眼球震颤"
输出: {"phenotypes": [
  {"hpo_id": "HP:0001290", "term_name": "肌张力低下", "presence": "present", "onset_age": 3, "onset_age_unit": "months", "severity": null, "modifiers": {"temporal_pattern": "progressive"}},
  {"hpo_id": "HP:0002033", "term_name": "喂养困难", "presence": "present", "onset_age": 3, "onset_age_unit": "months", "severity": null, "modifiers": {}},
  {"hpo_id": "HP:0002154", "term_name": "乳酸性酸中毒", "presence": "present", "onset_age": 3, "onset_age_unit": "months", "severity": "severe", "modifiers": {"temporal_pattern": "persistent"}},
  {"hpo_id": "HP:0001332", "term_name": "眼球运动异常", "presence": "present", "onset_age": 3, "onset_age_unit": "months", "severity": null, "modifiers": {"laterality": "bilateral"}},
  {"hpo_id": "HP:0002011", "term_name": "基底节区MRI异常信号", "presence": "present", "onset_age": null, "onset_age_unit": null, "severity": null, "modifiers": {"laterality": "bilateral"}}
]}"""


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
