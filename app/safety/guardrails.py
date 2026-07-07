"""安全机制 — 4 类安全阀 + 保守降级 + 3 档安全闸门。

按 PRD §7 + 技术设计书 §8 实现：
- 阀 1 信息修订：表型修订后重评估
- 阀 2 议题漂移：非罕见病问题拒绝回答
- 阀 3 跨层冲突：遗传推理与表型假设矛盾（触发回流）
- 阀 4 状态压缩：多轮对话历史超阈值时摘要化
- 保守降级：Top-1 置信度过低时拒绝输出假设
- 3 档安全闸门：strict / standard / relaxed
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


# ========== 安全阀类型 ==========

SAFETY_VALVES = {
    "info_revise": "信息修订：表型修订后重评估假设",
    "topic_drift": "议题漂移：非罕见病问题拒绝回答",
    "cross_layer_conflict": "跨层冲突：遗传推理与表型假设矛盾",
    "state_compress": "状态压缩：多轮后历史摘要化",
}


@dataclass
class ValveTrigger:
    """安全阀触发结果。"""
    valve_id: str
    message: str
    severity: str = "warning"  # info / warning / error / emergency
    action: str = "continue"   # continue / refuse / reflow / compress


# ========== 3 档安全闸门 ==========

SAFETY_GATES = {
    "strict": {
        "confidence_threshold": 0.5,
        "min_evidence_count": 3,
        "min_evidence_grade": "B",
        "force_genetic_counseling": True,
        "refuse_low_confidence": True,
    },
    "standard": {
        "confidence_threshold": 0.3,
        "min_evidence_count": 1,
        "min_evidence_grade": "C",
        "force_genetic_counseling": False,
        "refuse_low_confidence": True,
    },
    "relaxed": {
        "confidence_threshold": 0.1,
        "min_evidence_count": 0,
        "min_evidence_grade": "E",
        "force_genetic_counseling": False,
        "refuse_low_confidence": False,
    },
}


def get_gate_config(safety_level: str) -> dict:
    """获取安全闸门配置。未知级别降级为 standard。"""
    return SAFETY_GATES.get(safety_level, SAFETY_GATES["standard"])


# ========== 高风险场景识别 ==========

# 高风险关键词（触发 strict 升级）
HIGH_RISK_KEYWORDS = [
    "产前", "胎儿", "孕", "新生儿", "早产",
    "危重", "ICU", "抢救", "急诊",
    "生育", "终止妊娠", "流产",
]

# 紧急关键词（触发 emergency 级别）
EMERGENCY_KEYWORDS = [
    "呼吸困难", "意识障碍", "抽搐", "大出血",
    "心跳骤停", "休克", "昏迷",
]


def detect_high_risk(text: str) -> tuple[bool, str | None]:
    """检测输入文本是否含高风险/紧急关键词。

    返回 (is_high_risk, matched_keyword)。
    """
    for kw in EMERGENCY_KEYWORDS:
        if kw in text:
            return (True, kw)
    for kw in HIGH_RISK_KEYWORDS:
        if kw in text:
            return (True, kw)
    return (False, None)


# ========== 议题漂移检测 ==========

# 罕见病诊断相关关键词（任意一个匹配即认为相关）
MEDICAL_KEYWORDS = [
    "肌张力", "喂养", "乳酸", "发育", "癫痫", "抽搐",
    "倒退", "色素", "白质", "VLCFA", "低钾", "低镁",
    "碱中毒", "肾", "肝", "心", "脑", "神经",
    "代谢", "基因", "遗传", "突变", "家系", "先证者",
    "HPO", "罕见病", "孤儿病", "Orphanet",
    "MRI", "CT", "B超", "超声", "活检",
    "患儿", "患者", "男婴", "女婴", "男孩", "女孩",
    "查体", "实验室", "主诉", "现病史", "家族史",
    "hypotonia", "seizure", "developmental", "rare disease",
    "diagnosis", "phenotype", "inheritance",
]

# 明显无关的话题关键词
OFF_TOPIC_KEYWORDS = [
    "天气", "新闻", "股票", "电影", "游戏", "食谱",
    "旅游", "美食", "购物", "星座", "运势", "笑话",
    "hello", "hi", "你好", "谢谢", "再见",
]


def is_topic_drift(text: str) -> bool:
    """检测是否议题漂移（非罕见病诊断相关）。

    判定逻辑：
    - 含明显无关话题关键词 → 漂移
    - 不含任何医学关键词 → 漂移
    - 否则 → 相关
    """
    if not text or not text.strip():
        return True

    text_lower = text.lower()

    # 高风险/紧急关键词本身是强医学信号，豁免议题漂移检查
    # （避免"胎儿产前诊断"等短高风险输入被误判为非医学问题）
    for kw in HIGH_RISK_KEYWORDS + EMERGENCY_KEYWORDS:
        if kw in text or kw.lower() in text_lower:
            return False

    # 明显无关话题
    for kw in OFF_TOPIC_KEYWORDS:
        if kw in text_lower:
            # 短文本（<20字）且只含无关关键词 → 漂移
            if len(text) < 20:
                return True

    # 含医学关键词 → 不漂移
    for kw in MEDICAL_KEYWORDS:
        if kw in text or kw.lower() in text_lower:
            return False

    # 不含任何医学关键词，且文本较短 → 漂移
    if len(text) < 30:
        return True

    return False


# ========== 跨层冲突检测 ==========

def detect_cross_layer_conflict(state: dict | Any) -> ValveTrigger | None:
    """检测 Layer 4 遗传推理与 Layer 2 假设是否冲突。

    触发条件：Top-1 假设被遗传约束标记为不兼容。
    """
    hypotheses = _get_field(state, "hypotheses", [])
    genetic = _get_field(state, "genetic_constraint")

    if not hypotheses or not genetic:
        return None

    top1 = hypotheses[0]
    incompatible = getattr(genetic, "incompatible_diseases", []) or []
    if top1.disease_id in incompatible:
        return ValveTrigger(
            valve_id="cross_layer_conflict",
            message=(
                f"遗传推理与 Top-1 假设冲突：{top1.disease_name} "
                f"({top1.disease_id}) 被遗传约束排除。触发回流重评估。"
            ),
            severity="warning",
            action="reflow",
        )
    return None


# ========== 状态压缩检测 ==========

STATE_COMPRESS_THRESHOLD = 10  # 超过 10 轮对话触发压缩


def detect_state_compress(state: dict | Any) -> ValveTrigger | None:
    """检测是否需要状态压缩（多轮对话历史过长）。"""
    dialog_history = _get_field(state, "dialog_history", [])
    round_n = _get_field(state, "round", 0)

    if len(dialog_history) >= STATE_COMPRESS_THRESHOLD or round_n >= STATE_COMPRESS_THRESHOLD:
        return ValveTrigger(
            valve_id="state_compress",
            message=(
                f"会话已达 {len(dialog_history)} 轮，超过压缩阈值 {STATE_COMPRESS_THRESHOLD}。"
                "部分历史信息将摘要化。"
            ),
            severity="info",
            action="compress",
        )
    return None


# ========== 信息修订检测 ==========

# 修订触发词
REVISION_KEYWORDS = [
    "修正", "之前说的", "不对", "应该是", "改为", "更正",
    "我之前", "不对，应", "实际是", "纠正",
    "不是X", "不是肌张力", "排除",
]


def detect_info_revise(text: str) -> ValveTrigger | None:
    """检测医师是否在修订先前信息。"""
    for kw in REVISION_KEYWORDS:
        if kw in text:
            return ValveTrigger(
                valve_id="info_revise",
                message=f"检测到信息修订信号（关键词：{kw}）。将重新评估受影响的假设。",
                severity="info",
                action="reflow",
            )
    return None


# ========== 危急值检测 ==========

def detect_emergency(state: dict | Any) -> ValveTrigger | None:
    """检测是否存在危及生命的表型。"""
    profile = _get_field(state, "phenotype_profile")
    if not profile:
        return None

    raw_text = getattr(profile, "raw_text", "") or ""
    for kw in EMERGENCY_KEYWORDS:
        if kw in raw_text:
            return ValveTrigger(
                valve_id="emergency",
                message=(
                    f"检测到危急表型：{kw}。建议立即紧急就医，"
                    "本系统输出仅供参考。"
                ),
                severity="emergency",
                action="continue",
            )
    return None


# ========== 主检查入口 ==========

def check_safety(state: dict | Any) -> ValveTrigger | None:
    """检查所有安全阀。返回第一个触发的，或 None。

    优先级：emergency > topic_drift > cross_layer_conflict > info_revise > state_compress
    """
    # 1. 危急值（最高优先级）
    em = detect_emergency(state)
    if em:
        return em

    # 2. 议题漂移
    text = _get_field(state, "current_user_message", "")
    if text and is_topic_drift(text):
        return ValveTrigger(
            valve_id="topic_drift",
            message="本系统仅支持罕见病诊断辅助，请提供相关临床信息。",
            severity="warning",
            action="refuse",
        )

    # 3. 信息修订
    if text:
        rev = detect_info_revise(text)
        if rev:
            return rev

    # 4. 跨层冲突
    conflict = detect_cross_layer_conflict(state)
    if conflict:
        return conflict

    # 5. 状态压缩
    comp = detect_state_compress(state)
    if comp:
        return comp

    return None


# ========== 保守降级 ==========

def conservative_downgrade(
    state: dict | Any,
    safety_level: str = "standard",
) -> tuple[bool, str | None]:
    """证据不足时触发保守降级，拒绝输出假设。

    返回 (should_downgrade, reason)。
    按 PRD §7.2 + 技术设计书 §8.2 实现。
    """
    gate = get_gate_config(safety_level)

    # relaxed 模式不降级
    if not gate["refuse_low_confidence"]:
        return (False, None)

    hypotheses = _get_field(state, "hypotheses", [])
    if not hypotheses:
        return (True, "无候选假设")

    top1 = hypotheses[0]
    threshold = gate["confidence_threshold"]

    if top1.confidence < threshold:
        return (True, (
            f"Top-1 假设置信度 {top1.confidence:.2f} 低于 "
            f"{safety_level} 模式阈值 {threshold}。拒绝输出假设，"
            "建议补充更多信息后再评估。"
        ))

    # 证据数量检查
    min_ev = gate["min_evidence_count"]
    if min_ev > 0 and len(top1.evidence_ids) < min_ev:
        return (True, (
            f"Top-1 假设证据数 {len(top1.evidence_ids)} 低于 "
            f"{safety_level} 模式最小要求 {min_ev}。"
        ))

    return (False, None)


# ========== 高风险场景升级 ==========

def escalate_safety_level(
    current_level: str,
    user_message: str,
) -> tuple[str, ValveTrigger | None]:
    """高风险场景下升级安全等级。

    返回 (new_level, trigger)。如：
    - 含"产前/胎儿/新生儿" → strict
    - 含紧急关键词 → strict + emergency trigger
    """
    is_risk, matched = detect_high_risk(user_message)
    if not is_risk:
        return (current_level, None)

    new_level = "strict" if current_level != "strict" else "strict"

    # 紧急关键词
    if matched in EMERGENCY_KEYWORDS:
        trigger = ValveTrigger(
            valve_id="emergency",
            message=(
                f"检测到危急表型关键词：{matched}。"
                "安全等级已升级为 strict。建议立即紧急就医。"
            ),
            severity="emergency",
            action="continue",
        )
        return (new_level, trigger)

    trigger = ValveTrigger(
        valve_id="high_risk",
        message=(
            f"检测到高风险场景关键词：{matched}。"
            "安全等级已升级为 strict，强制遗传咨询建议。"
        ),
        severity="warning",
        action="continue",
    )
    return (new_level, trigger)


# ========== 辅助函数 ==========

def _get_field(state: Any, name: str, default: Any = None) -> Any:
    """从 state（dict 或 Pydantic 模型）取字段。"""
    if hasattr(state, name):
        return getattr(state, name)
    if isinstance(state, dict):
        return state.get(name, default)
    return default
