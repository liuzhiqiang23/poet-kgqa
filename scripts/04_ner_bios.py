# -*- coding: utf-8 -*-
"""
04_ner_bios.py — BERT NER 从诗人小传抽实体（地点/官职/人物），丰富 Poet 节点属性

模型: uer/roberta-base-finetuned-cluener2020-chinese（中文 NER，CLUENER 10 类）
      本机未缓存时需先下载（GitHub 不通，用 hf-mirror）：
      HF_ENDPOINT=https://hf-mirror.com huggingface-cli download uer/roberta-base-finetuned-cluener2020-chinese
输入: data/processed/poets.jsonl（authors.tang.json 的 desc 一句话小传，半文言）
输出: data/processed/poet_entities.jsonl {name, entities:[{text,type}]}
      （05 重跑时并入 poets.csv 的 ner_loc/ner_office 列）
注: 小传为半文言，CLUENER 现代语料训练，效果有限——论文中如实报告（覆盖率分析素材）。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
LOCAL_MODEL = ROOT / "data" / "models" / "ner-cluener"
MODEL = str(LOCAL_MODEL) if (LOCAL_MODEL / "config.json").exists() else \
    "uer/roberta-base-finetuned-cluener2020-chinese"
KEEP_TYPES = {"address", "organization", "name", "government"}  # CLUENER 标签


def main(limit: int = 0) -> None:
    from transformers import pipeline
    ners = pipeline("ner", model=MODEL, aggregation_strategy="simple")
    out_path = PROC / "poet_entities.jsonl"
    n = 0
    with out_path.open("w", encoding="utf-8") as f:
        for line in (PROC / "poets.jsonl").read_text(encoding="utf-8").splitlines():
            p = json.loads(line)
            desc = (p.get("desc") or "").strip()[:380]  # BERT 位置编码上限 512，超长小传截断
            if not desc:
                continue
            ents = [e for e in ners(desc) if e.get("entity_group") in KEEP_TYPES
                    and e.get("score", 0) > 0.7 and len(e.get("word", "").strip()) >= 2]
            rec = {"name": p["name"],
                   "entities": [{"text": e["word"].replace(" ", ""), "type": e["entity_group"]} for e in ents]}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
            if n % 200 == 0:
                print(f"  {n} done", flush=True)
            if limit and n >= limit:
                break
    print(f"poet_entities.jsonl: {n} 位诗人")


if __name__ == "__main__":
    main(limit=int(sys.argv[1]) if len(sys.argv) > 1 else 0)
