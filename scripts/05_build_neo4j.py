# -*- coding: utf-8 -*-
"""
05_build_neo4j.py — 生成 Neo4j 导入包（CSV + Cypher）

输出: data/neo4j_import/
    poets.csv, works.csv, groups.csv, wrote.csv, assoc.csv, member.csv, import.cypher
用法: 1) 把 data/neo4j_import 下所有 CSV 放进 Neo4j 的 import 目录
      2) neo4j-admin / browser 执行 import.cypher（LOAD CSV + MERGE，可重复执行）
不依赖 Neo4j 运行，本脚本只产文件。
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kg.graph_service import _alias_map  # noqa: E402

PROC = ROOT / "data" / "processed"
OUT = ROOT / "data" / "neo4j_import"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    aliases = json.loads((ROOT / "data" / "alias" / "poet_aliases.json").read_text(encoding="utf-8"))
    head30 = {k for k in aliases if not k.startswith("_")}
    a2p = _alias_map()

    def std(name: str) -> str:
        return a2p.get(name, name)

    # ---- 节点：诗人（3663；head30 的繁体语料名归一到标准名并合并存诗数）----
    poets_raw = [json.loads(l) for l in (PROC / "poets.jsonl").read_text(encoding="utf-8").splitlines()]
    merged: dict[str, dict] = {}
    for p in poets_raw:
        name = std(p["name"])
        if name in merged:
            merged[name]["n_poems"] += p["n_poems"]
        else:
            merged[name] = {"name": name, "desc": p["desc"], "dynasty": p["dynasty"],
                            "n_poems": p["n_poems"]}
    poets = list(merged.values())

    # NER 实体（04 产出）：并入 poets 列表
    ent_file = PROC / "poet_entities.jsonl"
    ner_map: dict[str, list] = {}
    if ent_file.exists():
        for line in ent_file.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            ner_map[std(r["name"])] = r["entities"]
    for p in poets:
        ents = ner_map.get(p["name"], [])
        p["ner_people"] = "、".join(dict.fromkeys(
            e["text"] for e in ents if e["type"] == "name" and e["text"] != p["name"]).keys())[:120]
        p["ner_places"] = "、".join(dict.fromkeys(
            e["text"] for e in ents if e["type"] == "address").keys())[:80]

    with (OUT / "poets.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        # 纯净列名：类型后缀(:int/:bool)是 neo4j-admin import 语法，LOAD CSV 不认
        w.writerow(["poet_name", "desc", "dynasty", "n_poems", "head30", "ner_people", "ner_places"])
        for p in poets:
            w.writerow([p["name"], (p["desc"] or "")[:300], p["dynasty"], p["n_poems"],
                        "true" if p["name"] in head30 else "false",
                        p.get("ner_people", ""), p.get("ner_places", "")])

    # ---- 节点：作品（5.7万，正文不入图——正文在 FAISS/poems.jsonl）----
    n_works = 0
    with (OUT / "works.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["wid", "title"])
        for line in (PROC / "poems.jsonl").read_text(encoding="utf-8").splitlines():
            p = json.loads(line)
            w.writerow([p["id"], p["title"]])
            n_works += 1

    # ---- 节点：并称群体 + MEMBER 边 ----
    with (OUT / "groups.csv").open("w", encoding="utf-8-sig", newline="") as f, \
         (OUT / "member.csv").open("w", encoding="utf-8-sig", newline="") as g:
        wc, gm = csv.writer(f), csv.writer(g)
        wc.writerow(["gname"])
        gm.writerow([":START_ID", ":END_ID", ":TYPE"])
        for line in (PROC / "groups_clean.jsonl").read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            wc.writerow([r["group"], "Group"])
            for m in r["members"]:
                gm.writerow([m, r["group"], "MEMBER"])

    # ---- WROTE 边（作者→作品）----
    with (OUT / "wrote.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([":START_ID", ":END_ID", ":TYPE"])
        for line in (PROC / "poems.jsonl").read_text(encoding="utf-8").splitlines():
            p = json.loads(line)
            w.writerow([std(p["author"]), p["id"], "WROTE"])

    # ---- ASSOC 交游边 ----
    with (OUT / "assoc.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([":START_ID", ":END_ID", "rel", "n_evidence", "n_high"])
        for line in (PROC / "edges_clean.jsonl").read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            w.writerow([r["src"], r["dst"], r["rel"], len(r["evidence"]), r["n_high"]])

    # ---- Cypher 导入脚本（LOAD CSV，幂等 MERGE；列名与各 CSV 表头一致）----
    cypher = """// poet-kgqa 图谱导入（Neo4j Browser / cypher-shell；CSV 需在 import 目录）
// 注意：列名是普通名（类型后缀 :int/:bool/:ID 是 neo4j-admin import 专用语法，LOAD CSV 不识别）
CREATE CONSTRAINT poet_name IF NOT EXISTS FOR (p:Poet) REQUIRE p.name IS UNIQUE;
CREATE CONSTRAINT work_id IF NOT EXISTS FOR (w:Work) REQUIRE w.wid IS UNIQUE;
CREATE CONSTRAINT group_name IF NOT EXISTS FOR (g:Group) REQUIRE g.gname IS UNIQUE;

LOAD CSV WITH HEADERS FROM 'file:///poets.csv' AS row
MERGE (p:Poet {name: row.poet_name})
  ON CREATE SET p.desc=row.desc, p.dynasty=row.dynasty, p.n_poems=toInteger(row.n_poems), p.head30=row.head30, p.ner_people=row.ner_people, p.ner_places=row.ner_places
  ON MATCH SET p.desc=row.desc, p.n_poems=toInteger(row.n_poems), p.head30=row.head30, p.ner_people=row.ner_people, p.ner_places=row.ner_places;

LOAD CSV WITH HEADERS FROM 'file:///works.csv' AS row
MERGE (w:Work {wid: row.wid}) SET w.title=row.title;

LOAD CSV WITH HEADERS FROM 'file:///groups.csv' AS row
MERGE (g:Group {gname: row.gname});

LOAD CSV WITH HEADERS FROM 'file:///wrote.csv' AS row
MATCH (p:Poet {name: row[':START_ID']}), (w:Work {wid: row[':END_ID']})
MERGE (p)-[:WROTE]->(w);

LOAD CSV WITH HEADERS FROM 'file:///member.csv' AS row
MATCH (p:Poet {name: row[':START_ID']}), (g:Group {gname: row[':END_ID']})
MERGE (p)-[:MEMBER]->(g);

LOAD CSV WITH HEADERS FROM 'file:///assoc.csv' AS row
MATCH (a:Poet {name: row[':START_ID']}), (b:Poet {name: row[':END_ID']})
MERGE (a)-[r:ASSOC]->(b) SET r.rel=row.rel, r.n_evidence=toInteger(row.n_evidence), r.n_high=toInteger(row.n_high);
"""
    (OUT / "import.cypher").write_text(cypher, encoding="utf-8")
    print(f"导入包就绪: {OUT}")
    print(f"  诗人 {len(poets)} | 作品 {n_works} | 交游边(去重对) {sum(1 for _ in (OUT/'assoc.csv').open(encoding='utf-8-sig'))-1}")


if __name__ == "__main__":
    main()
