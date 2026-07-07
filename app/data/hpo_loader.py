"""HPO phenotype.hpoa 全量导入器。

用法: python3 -m app.data.hpo_loader [--hpoa PATH] [--db PATH]

默认读取项目根目录 phenotype.hpoa，写入 data/ 目录的 JSON 文件。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

# ── 项目根 ──
_PROJECT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_HPOA = _PROJECT / "phenotype.hpoa"
_DISEASE_META = _PROJECT / "data" / "disease_meta.json"
_FREQ_JSON = _PROJECT / "data" / "hpo_frequency" / "orphanet_freq.json"

# ── 频率解析 ──

_FREQ_CODE_MAP = {
    "HP:0040281": 0.90,   # Very frequent (>80%)
    "HP:0040282": 0.50,   # Frequent (30-79%)
    "HP:0040283": 0.10,   # Occasional (5-29%)
    "HP:0040284": 0.02,   # Very rare (<5%)
    "HP:0040285": 0.50,   # Excluded (0%) — 暂作 unknown
    "HP:0040280": 0.50,   # Unknown
}


def parse_frequency(raw: str) -> float:
    if not raw or raw == "-":
        return 0.50
    # HPO 频率代码
    if raw in _FREQ_CODE_MAP:
        return _FREQ_CODE_MAP[raw]
    # 百分比
    m = re.match(r"(\d+(\.\d+)?)\s*%", raw)
    if m:
        return min(float(m.group(1)) / 100.0, 1.0)
    # 分数 1/n
    m = re.match(r"(\d+)/(\d+)", raw)
    if m:
        return float(m.group(1)) / max(float(m.group(2)), 1.0)
    # 纯数字（如 "1/10000" 带逗号）
    m = re.match(r"(\d{1,3})(?:,\d{3})*", raw)
    if m:
        return 0.05  # 罕见 → 低频率
    return 0.50


# ── 主解析 ──

def load_hpoa(path: Path) -> tuple[list[dict], dict]:
    """解析 phenotype.hpoa，返回 entries + disease_meta。"""
    entries: list[dict] = []
    meta: dict = {}
    seen: set = set()

    with open(path, encoding="utf-8") as f:
        lines = [l.rstrip("\n") for l in f if l.strip() and not l.startswith("#")]

    print(f"  HPO 数据行: {len(lines):,}")

    for row in lines:
        parts = row.split("\t")
        if len(parts) < 4:
            continue
        db_id = parts[0].strip()
        name = parts[1].strip()
        hpo_id = parts[3].strip()
        freq_raw = parts[7].strip() if len(parts) > 7 else ""
        aspect = parts[10].strip() if len(parts) > 10 else ""

        # 只取表型 (P)，跳过遗传模式 (M) 和病程 (C)
        if aspect not in ("", "P"):
            continue

        freq = parse_frequency(freq_raw)
        key = (db_id, hpo_id)
        if key in seen:
            continue
        seen.add(key)

        entries.append({
            "disease_id": db_id,
            "disease_name": name,
            "hpo_id": hpo_id,
            "hpo_name": "",
            "frequency": round(freq, 4),
            "frequency_qualifier": freq_raw,
            "source": "HPO",
        })

        if db_id not in meta:
            meta[db_id] = {
                "name": name,
                "category": "遗传病" if db_id.startswith("OMIM") else "罕见病" if db_id.startswith("ORPHA") else "其他",
                "prevalence": 1e-6,
                "inheritance_modes": [],
                "typical_onset": {"age_min": 0, "age_max": 80, "age_unit": "years"},
                "progression": {"speed": "variable", "trajectory": "variable"},
            }

    return entries, meta


def merge_into_existing(entries: list[dict], meta: dict):
    """合并到现有 data/*.json 文件。"""
    # 1. 读现有数据
    freq_data = {}
    if _FREQ_JSON.exists():
        with open(_FREQ_JSON, encoding="utf-8") as f:
            freq_data = json.load(f)
    existing_entries = freq_data.get("entries", [])

    disease_meta = {}
    if _DISEASE_META.exists():
        with open(_DISEASE_META, encoding="utf-8") as f:
            disease_meta = json.load(f)

    # 2. 合并 entries（按 disease_id+hpo_id 去重）
    seen = set()
    merged = []
    for e in existing_entries:
        key = (e["disease_id"], e["hpo_id"])
        if key not in seen:
            seen.add(key)
            merged.append(e)
    for e in entries:
        key = (e["disease_id"], e["hpo_id"])
        if key not in seen:
            seen.add(key)
            merged.append(e)

    # 3. 合并 disease_meta
    existing_diseases = disease_meta.get("diseases", {})
    for did, info in meta.items():
        if did not in existing_diseases:
            existing_diseases[did] = info
    disease_meta["diseases"] = existing_diseases
    disease_meta["version"] = "2.0"
    disease_meta["description"] = f"全量 HPO 导入 ({len(existing_diseases):,} 疾病, {len(merged):,} 条目)"
    disease_meta["format"] = "diseases: {disease_id: meta}, entries: [{disease_id, hpo_id, frequency}]"

    # 4. 写回
    freq_data["entries"] = merged
    freq_data["version"] = "2.0"
    freq_data["description"] = disease_meta["description"]

    with open(_FREQ_JSON, "w", encoding="utf-8") as f:
        json.dump(freq_data, f, ensure_ascii=False, indent=2)

    with open(_DISEASE_META, "w", encoding="utf-8") as f:
        json.dump(disease_meta, f, ensure_ascii=False, indent=2)

    return len(merged), len(existing_diseases)


def main():
    parser = argparse.ArgumentParser(description="HPO phenotype.hpoa 全量导入器")
    parser.add_argument("--hpoa", default=str(_DEFAULT_HPOA), help="phenotype.hpoa 路径")
    args = parser.parse_args()

    path = Path(args.hpoa)
    if not path.exists():
        print(f"❌ 文件不存在: {path}")
        print(f"请先下载: curl -L -o {path} https://github.com/obophenotype/human-phenotype-ontology/releases/latest/download/phenotype.hpoa")
        sys.exit(1)

    print(f"解析 {path} ({path.stat().st_size / 1024 / 1024:.1f} MB)...")
    entries, meta = load_hpoa(path)
    print(f"  解析: {len(entries):,} 条 HPO 关联, {len(meta):,} 个疾病")

    total_entries, total_diseases = merge_into_existing(entries, meta)
    print(f"\n  写入 data/:")
    print(f"    频率条目: {total_entries:,}")
    print(f"    疾病元数据: {total_diseases:,}")
    print(f"  done.")


if __name__ == "__main__":
    main()
