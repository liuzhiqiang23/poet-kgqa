# -*- coding: utf-8 -*-
"""
eval/dataset_build.py — 从图谱自动生成评测集（金标准=图谱事实，可程序化判分）

题目类型（五类）：
  life     X 大约生于哪一年？              gold=生年（poet_dates）
  dynasty  X 是哪个朝代的诗人？            gold=唐
  n_poems  X 在全唐诗中存诗多少首？        gold=n_poems
  relation X 和 Y 有什么交游记录吗？       gold=是/否（edges_clean）
  imagery  全唐诗中写「K」最多的诗人是谁？  gold=top1（poems 扫描）

输出: eval/qa_set.jsonl {id, q, type, gold, poet(s), keywords}
"""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from chat.entity_link import EntityLinker  # noqa: E402
from kg.graph_service import JsonlGraph  # noqa: E402

OUT = ROOT / "eval" / "qa_set.jsonl"
random.seed(2026)


def main() -> None:
    g = JsonlGraph()
    el = EntityLinker()
    poets30 = sorted(el.dates.keys())
    items = []

    # 1) 生年（30 题全量）
    for p in poets30:
        b, d = el.dates[p]
        items.append({"q": f"{p}大约生于哪一年？", "type": "life", "gold": str(b), "poet": p})
        items.append({"q": f"{p}大约卒于哪一年？", "type": "life", "gold": str(d), "poet": p})

    # 2) 朝代（全 30）
    for p in poets30:
        items.append({"q": f"{p}是哪个朝代的诗人？", "type": "dynasty", "gold": "唐", "poet": p})

    # 3) 存诗量（全 30）
    for p in poets30:
        card = g.poet_card(p)
        if card and card["n_poems"]:
            items.append({"q": f"{p}在《全唐诗》中存诗大约多少首？", "type": "n_poems",
                          "gold": card["n_poems"], "poet": p})

    # 4) 交游关系（正向 40 对 + 反向负例 20 对）
    pairs = [(r["src"], r["dst"]) for r in g.assoc_flat]
    random.shuffle(pairs)
    pos = [(a, b) for a, b in pairs if a in poets30 or b in poets30][:40]
    for a, b in pos:
        items.append({"q": f"{a}和{b}之间有赠答或唱和的交游记录吗？", "type": "relation",
                      "gold": "有", "poets": [a, b]})
    all30 = set(poets30)
    made = 0
    for a in poets30:
        for b in poets30:
            if a >= b or made >= 20:
                continue
            if not g.relation(a, b)["connected"]:
                items.append({"q": f"{a}和{b}之间有赠答或唱和的交游记录吗？", "type": "relation",
                              "gold": "无", "poets": [a, b]})
                made += 1

    # 5) 意象（10 个关键词）
    for kw in ["月", "酒", "柳", "雁", "雪", "春", "江", "花", "風", "山"]:
        top = g.top_imagery(kw, 1)
        if top:
            items.append({"q": f"全唐诗中写「{kw}」最多的诗人是谁？", "type": "imagery",
                          "gold": top[0]["poet"], "keyword": kw})

    random.shuffle(items)
    with OUT.open("w", encoding="utf-8") as f:
        for i, it in enumerate(items):
            it["id"] = f"q{i:04d}"
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    from collections import Counter
    print(f"qa_set.jsonl: {len(items)} 题", dict(Counter(x['type'] for x in items)))


if __name__ == "__main__":
    main()
