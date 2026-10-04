# -*- coding: utf-8 -*-
"""
eval/ablation.py — 检索消融：向量检索(bge) vs 关键词扫描 hit@3

20 条名句查询（查询文本先在语料中自证存在，取其诗为目标），比较两臂 top-3 命中率。
运行（需带 torch 的解释器）:
  HF_HUB_OFFLINE=1 <venv-python> eval/ablation.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# (查询, 锚点句)：锚点句刻意选繁简同形字（语料为繁体且部分用词与通行版不同）
QUERIES = [
    ("疑是地上霜 月光 思乡", "疑是地上霜"),
    ("此物最相思 红豆 相思之情", "此物最相思"),
    ("花落知多少 春 夜雨", "花落知多少"),
    ("海上生明月 思念远方", "海上生明月"),
    ("岱宗夫如何 泰山 雄壮", "岱宗夫如何"),
    ("寸草心 母爱 报答", "寸草心"),
    ("入海流 黄河 更上层楼", "入海流"),
    ("葡萄美酒夜光杯 边塞 豪饮", "葡萄美酒夜光杯"),
    ("粒粒皆辛苦 农夫 节俭", "粒粒皆辛苦"),
    ("寒山寺 夜半钟声 客船", "寒山寺"),
    ("國破山河在 战乱 忧国", "國破山河在"),
    ("客舍青青柳色新 送别 朋友", "客舍青青柳色新"),
    ("巴山夜雨 秋池 思念", "巴山夜雨"),
    ("夜泊秦淮近酒家 商女 后庭花", "夜泊秦淮近酒家"),
    ("清泉石上流 空山 秋暝", "清泉石上流"),
    ("遍插茱萸少一人 重阳 思亲", "遍插茱萸少一人"),
]


def main() -> None:
    from rag.retriever import Retriever
    poems = {}
    for line in (ROOT / "data" / "processed" / "poems.jsonl").read_text(encoding="utf-8").splitlines():
        p = json.loads(line)
        poems[p["id"]] = p

    # 自证：用繁简同形锚点句在语料中定位目标诗
    targets = []
    for q, frag in QUERIES:
        for pid, p in poems.items():
            if frag in p["text"]:
                targets.append((q, pid, p["title"]))
                break
    print(f"queries: {len(QUERIES)}, verified targets: {len(targets)}")

    r_vec = Retriever()
    r_kw = Retriever()
    r_kw.vecs = None
    r_kw.model = None  # 强制关键词臂
    print("modes:", r_vec.mode, "/", r_kw.mode)

    def hit3(retriever, q, tid):
        return any(h["id"] == tid for h in retriever.search(q, 3))

    rows, acc = [], {"vector": 0, "keyword": 0}
    for q, tid, title in targets:
        v, k = hit3(r_vec, q, tid), hit3(r_kw, q, tid)
        acc["vector"] += v
        acc["keyword"] += k
        rows.append({"q": q, "target": title, "vector_hit3": v, "keyword_hit3": k})
    n = len(targets)
    out = {"n": n,
           "vector_hit3": f"{acc['vector']}/{n} ({acc['vector']/n:.0%})",
           "keyword_hit3": f"{acc['keyword']}/{n} ({acc['keyword']/n:.0%})",
           "detail": rows}
    (ROOT / "eval" / "results").mkdir(exist_ok=True)
    (ROOT / "eval" / "results" / "ablation.md").write_text(
        f"# 检索消融（hit@3, n={n}）\n\n| 模式 | 命中率 |\n|---|---|\n"
        f"| 向量(bge) | {out['vector_hit3']} |\n| 关键词 | {out['keyword_hit3']} |\n", encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1)[:800])
    (ROOT / "eval" / "results" / "ablation.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
