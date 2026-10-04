# -*- coding: utf-8 -*-
"""
01_load_corpus.py — 全唐原始 JSON → 统一底表（poets.jsonl / poems.jsonl）

输入: data/raw/tang/authors.tang.json + poet.tang.*.json
输出: data/processed/poets.jsonl  {name, desc, dynasty, n_poems}
      data/processed/poems.jsonl  {id, title, author, text, vol}
"""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "tang"
OUT = ROOT / "data" / "processed"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    authors = json.loads((RAW / "authors.tang.json").read_text(encoding="utf-8"))
    desc_map = {a["name"]: (a.get("desc") or "").strip() for a in authors}
    print(f"authors.tang.json: {len(authors)} 位诗人")

    n_poems = Counter()
    poems_path = OUT / "poems.jsonl"
    n = 0
    with poems_path.open("w", encoding="utf-8") as f:
        for vol_file in sorted(RAW.glob("poet.tang.*.json")):
            vol = vol_file.stem.replace("poet.tang.", "")
            for i, p in enumerate(json.loads(vol_file.read_text(encoding="utf-8"))):
                author = (p.get("author") or "佚名").strip()
                text = "".join(p.get("paragraphs") or [])
                rec = {
                    "id": f"t{vol}_{i}",
                    "title": (p.get("title") or "").strip(),
                    "author": author,
                    "text": text,
                    "vol": vol,
                }
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n_poems[author] += 1
                n += 1
    print(f"poems.jsonl: {n} 首")

    poets_path = OUT / "poets.jsonl"
    # 作者表里没有但诗里出现的名字（如 无名氏/联句）也入底表，desc 留空
    all_names = set(n_poems) | set(desc_map)
    with poets_path.open("w", encoding="utf-8") as f:
        for name in all_names:
            rec = {
                "name": name,
                "desc": desc_map.get(name, ""),
                "dynasty": "唐",
                "n_poems": n_poems.get(name, 0),
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"poets.jsonl: {len(all_names)} 位作者（含无名氏等）")

    top = n_poems.most_common(10)
    print("存诗量 TOP10:", "，".join(f"{k}({v})" for k, v in top))
    head = [n for n in ["李白", "杜甫", "白居易", "王维", "孟浩然", "李商隐", "杜牧"] if n in n_poems]
    print("核心诗人在场:", "、".join(head))


if __name__ == "__main__":
    main()
