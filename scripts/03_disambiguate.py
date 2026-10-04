# -*- coding: utf-8 -*-
"""
03_disambiguate.py — 消歧审计 + 边聚合 + 并称表合并

三层消歧策略的落点：
  第一层：人工别名表（02 已用，含高危别名黑名单/动词白名单）
  第二层：本脚本做审计——置信度分层、自环检查、可疑边标记
  第三层：低置信边宁缺勿错，剔除出正式图谱（进 quarantined 供人工复核）

输入: edges_raw.jsonl / groups.json / poets.jsonl
输出: edges_clean.jsonl  {src,dst,rel,evidence:[{poem_id,title,confidence}...]}
      groups_clean.jsonl
      report.json        （统计+可疑样例，写论文用）
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
ALIAS = ROOT / "data" / "alias"

# 低置信关系类型（易与地名/泛指混淆），默认隔离待人工复核
QUARANTINE_RELS = {"干谒"}   # 「呈/上/献」多含公文性作品，人工确认后放行
QUARANTINE_PAIRS = set()    # 预留：逐对黑名单

REVIEW_FILE = ROOT / "data" / "alias" / "edge_review.json"


def load_review() -> tuple[set[str], set[str]]:
    """人工复核结论：poem_id 级 accept/reject"""
    if not REVIEW_FILE.exists():
        return set(), set()
    r = json.loads(REVIEW_FILE.read_text(encoding="utf-8"))
    return set(r.get("accept_poem_ids", [])), set(r.get("reject_poem_ids", []))


def main() -> None:
    poets = {json.loads(l)["name"] for l in (PROC / "poets.jsonl").read_text(encoding="utf-8").splitlines()}
    aliases = json.loads((ALIAS / "poet_aliases.json").read_text(encoding="utf-8"))
    head30 = {k for k in aliases if not k.startswith("_")}

    edges = [json.loads(l) for l in (PROC / "edges_raw.jsonl").read_text(encoding="utf-8").splitlines()]
    print(f"raw edges: {len(edges)}")

    # ---- 审计 ----
    self_loops = [e for e in edges if e["src"] == e["dst"]]
    bad_node = [e for e in edges if e["src"] not in poets and e["dst"] not in head30]
    conf_dist = Counter(e["confidence"] for e in edges)
    rel_dist = Counter(e["rel"] for e in edges)
    print(f"自环: {len(self_loops)}  无效节点: {len(bad_node)}  置信度: {dict(conf_dist)}")

    # ---- 过滤 + 聚合（按 src,dst,rel 聚证据），人工复核结论优先 ----
    acc_ids, rej_ids = load_review()
    kept, quarantined, rejected = [], [], []
    agg: dict[tuple, dict] = {}
    for e in edges:
        if e["src"] == e["dst"]:
            continue
        key = (e["src"], e["dst"], e["rel"])
        if key not in agg:
            agg[key] = {"src": e["src"], "dst": e["dst"], "rel": e["rel"], "evidence": []}
        agg[key]["evidence"].append({"poem_id": e["poem_id"], "title": e["title"],
                                     "confidence": e["confidence"]})
    for rec in agg.values():
        n_high = sum(1 for v in rec["evidence"] if v["confidence"] == "high")
        rec["n_high"] = n_high
        has_accepted_evidence = any(v["poem_id"] in acc_ids for v in rec["evidence"])
        all_rejected = all(v["poem_id"] in rej_ids for v in rec["evidence"])
        if all_rejected:
            rejected.append(rec)  # 人工驳回，永不入图
        elif has_accepted_evidence:
            rec["reviewed"] = True
            kept.append(rec)      # 人工放行
        else:
            suspicious = (
                rec["rel"] in QUARANTINE_RELS
                or rec["src"] in QUARANTINE_PAIRS or (rec["src"], rec["dst"]) in QUARANTINE_PAIRS
                or (n_high == 0 and len(rec["evidence"]) == 1)  # 孤立且无高置信证据
            )
            (quarantined if suspicious else kept).append(rec)

    with (PROC / "edges_clean.jsonl").open("w", encoding="utf-8") as f:
        for r in kept:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with (PROC / "quarantined_edges.jsonl").open("w", encoding="utf-8") as f:
        for r in quarantined:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with (PROC / "rejected_edges.jsonl").open("w", encoding="utf-8") as f:
        for r in rejected:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # ---- 并称表 ----
    groups = {k: v for k, v in json.loads((ALIAS / "groups.json").read_text(encoding="utf-8")).items() if v}
    with (PROC / "groups_clean.jsonl").open("w", encoding="utf-8") as f:
        for g, members in groups.items():
            f.write(json.dumps({"group": g, "members": members}, ensure_ascii=False) + "\n")

    # ---- 报告 ----
    pair_deg = Counter()
    for r in kept:
        pair_deg[r["src"]] += 1
        pair_deg[r["dst"]] += 1
    report = {
        "raw_edges": len(edges),
        "kept_pairs": len(kept),
        "kept_reviewed": sum(1 for r in kept if r.get("reviewed")),
        "quarantined_pairs": len(quarantined),
        "rejected_pairs": len(rejected),
        "self_loops": len(self_loops),
        "confidence_dist": dict(conf_dist),
        "rel_dist": dict(rel_dist),
        "degree_top": pair_deg.most_common(15),
        "quarantine_reason": "rel∈干谒 或 孤立且无高置信证据（未被人工复核放行）",
        "quarantined_sample": [
            {"pair": f"{r['src']}->{r['dst']}", "rel": r["rel"],
             "titles": [v["title"] for v in r["evidence"][:3]]} for r in quarantined[:12]
        ],
    }
    (PROC / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"保留关系对: {len(kept)}（其中人工复核放行 {sum(1 for r in kept if r.get('reviewed'))}）"
          f"  隔离待复核: {len(quarantined)}  人工驳回: {len(rejected)}  并称组: {len(groups)}")
    print("图谱度数 TOP10:", "，".join(f"{k}({v})" for k, v in pair_deg.most_common(10)))
    print("隔离样例(供人工复核):")
    for s in report["quarantined_sample"][:6]:
        print(f"   {s['pair']} [{s['rel']}] {s['titles'][:2]}")


if __name__ == "__main__":
    main()
