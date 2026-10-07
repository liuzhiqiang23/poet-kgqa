# -*- coding: utf-8 -*-
"""
kg/graph_service.py — 图谱查询统一服务层

两个后端，接口一致：
  JsonlGraph   —— 直接读 data/processed/*.jsonl（Neo4j 未起时的兜底，也让系统今天就能跑）
  Neo4jGraph   —— bolt 连真实 Neo4j（起了之后自动切换，查询走 Cypher 模板）

铁律：所有 Cypher 参数化模板，绝不让 LLM 生成 Cypher。
"""
from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"


def _head30() -> set[str]:
    aliases = json.loads((ROOT / "data" / "alias" / "poet_aliases.json").read_text(encoding="utf-8"))
    return {k for k in aliases if not k.startswith("_")}


def _alias_map() -> dict[str, str]:
    """语料名（含繁体全名/字号）→ 30 人标准名"""
    aliases = json.loads((ROOT / "data" / "alias" / "poet_aliases.json").read_text(encoding="utf-8"))
    a2p: dict[str, str] = {}
    for poet, alist in aliases.items():
        if poet.startswith("_") or not isinstance(alist, list):
            continue
        a2p[poet] = poet
        for a in alist:
            a2p[a] = poet
    return a2p


class JsonlGraph:
    """内存版图：交游网络 BFS/ego/common_friends 足够；意象统计扫描 poems.jsonl（带缓存）。"""

    def __init__(self) -> None:
        self.poets: dict[str, dict] = {}
        a2p = _alias_map()
        for l in (PROC / "poets.jsonl").read_text(encoding="utf-8").splitlines():
            r = json.loads(l)
            std = a2p.get(r["name"], r["name"])  # 繁体全名 → 标准名（如 劉禹錫→刘禹锡）
            if std != r["name"]:
                if std in self.poets:  # 简繁两个条目并存时合并计数
                    self.poets[std]["n_poems"] += r["n_poems"]
                else:
                    r2 = dict(r, name=std)
                    self.poets[std] = r2
                self.poets.setdefault(r["name"], r)  # 保留原键便于外部诗人反查
            else:
                self.poets[std] = r
        self.head30 = _head30()
        self.assoc: dict[str, list[dict]] = {}   # name -> [{dst, rel, evidence...}]
        self.assoc_flat: list[dict] = []
        for l in (PROC / "edges_clean.jsonl").read_text(encoding="utf-8").splitlines():
            r = json.loads(l)
            self.assoc_flat.append(r)
            self.assoc.setdefault(r["src"], []).append(r)
            self.assoc.setdefault(r["dst"], []).append(r)
        self.groups: dict[str, list[str]] = {}
        for l in (PROC / "groups_clean.jsonl").read_text(encoding="utf-8").splitlines():
            r = json.loads(l)
            self.groups[r["group"]] = r["members"]
        self._poems_loaded = False
        self._poems: list[dict] = []
        self._imagery_cache: dict[str, list[tuple[str, int]]] = {}
        self._a2p = a2p  # 繁体→标准名映射（top_poets 去重用）
        self._ner: dict[str, list] = {}
        ent_file = PROC / "poet_entities.jsonl"
        if ent_file.exists():
            for l in ent_file.read_text(encoding="utf-8").splitlines():
                r = json.loads(l)
                self._ner[a2p.get(r["name"], r["name"])] = r["entities"]

    # ---------- 基础 ----------
    def has_poet(self, name: str) -> bool:
        return name in self.poets

    def poet_card(self, name: str) -> Optional[dict]:
        p = self.poets.get(name)
        if not p:
            return None
        card = dict(p)
        card["head30"] = name in self.head30
        card["groups"] = [g for g, ms in self.groups.items() if name in ms]
        card["associates"] = self._neighbors(name)
        ents = self._ner.get(name, [])
        card["ner_people"] = "、".join(dict.fromkeys(
            e["text"] for e in ents if e["type"] == "name" and e["text"] != name).keys())[:120]
        card["ner_places"] = "、".join(dict.fromkeys(
            e["text"] for e in ents if e["type"] == "address").keys())[:80]
        return card

    def _neighbors(self, name: str) -> list[dict]:
        seen: set[str] = set()
        out = []
        for r in self.assoc.get(name, []):
            other = r["dst"] if r["src"] == name else r["src"]
            if other in seen:
                continue
            seen.add(other)
            out.append({"poet": other, "rel": r["rel"], "n_evidence": len(r["evidence"]),
                        "sample": r["evidence"][0]["title"] if r["evidence"] else ""})
        out.sort(key=lambda x: -x["n_evidence"])
        return out

    # ---------- 关系查询 ----------
    def relation(self, a: str, b: str) -> dict:
        rels = [r for r in self.assoc.get(a, []) if (r["dst"] == b or r["src"] == b)]
        if not rels:
            return {"a": a, "b": b, "connected": False}
        return {"a": a, "b": b, "connected": True, "edges": [
            {"direction": f"{r['src']}→{r['dst']}", "rel": r["rel"],
             "n_evidence": len(r["evidence"]),
             "poems": [e["title"] for e in r["evidence"][:5]]} for r in rels]}

    def ego(self, name: str, depth: int = 1) -> dict:
        """pyvis 子图：{nodes:[{id,label,group}], edges:[{from,to,label}]}"""
        depth = max(1, min(int(depth), 3))  # 钳制深度，防变长遍历放大
        if name not in self.poets and name not in self.assoc:
            return {"nodes": [], "edges": []}
        nodes, edges, visited = {}, [], {name}
        frontier = {name}
        for _ in range(depth):
            nxt: set[str] = set()
            for u in frontier:
                for r in self.assoc.get(u, []):
                    v = r["dst"] if r["src"] == u else r["src"]
                    if (u, v) not in edges and (v, u) not in edges:
                        edges.append({"from": u, "to": v, "label": r["rel"], "id": f"{u}|{v}"})
                    if v not in visited:
                        nxt.add(v)
            visited |= nxt
            frontier = nxt
        for n in visited:
            nodes[n] = {"id": n, "label": n,
                        "group": "head" if n in self.head30 else "poet"}
        return {"nodes": list(nodes.values()), "edges": edges}

    def shortest_path(self, a: str, b: str) -> Optional[list[str]]:
        if a not in self.poets and a not in self.assoc:
            return None
        if b not in self.poets and b not in self.assoc:
            return None
        q = deque([(a, [a])])
        seen = {a}
        while q:
            u, path = q.popleft()
            if u == b:
                return path
            for r in self.assoc.get(u, []):
                v = r["dst"] if r["src"] == u else r["src"]
                if v not in seen:
                    seen.add(v)
                    q.append((v, path + [v]))
        return None

    def common_friends(self, a: str, b: str) -> list[str]:
        na = {r["dst"] if r["src"] == a else r["src"] for r in self.assoc.get(a, [])}
        nb = {r["dst"] if r["src"] == b else r["src"] for r in self.assoc.get(b, [])}
        return sorted(na & nb)

    # ---------- 统计/意象 ----------
    def _load_poems(self) -> None:
        if self._poems_loaded:
            return
        for l in (PROC / "poems.jsonl").read_text(encoding="utf-8").splitlines():
            self._poems.append(json.loads(l))
        self._poems_loaded = True

    def top_imagery(self, keyword: str, top: int = 10) -> list[dict]:
        """意象/关键词统计：谁的作品含该词最多（正文扫描，缓存）。作者名归一到标准名。"""
        if keyword in self._imagery_cache:
            cnt = self._imagery_cache[keyword]
        else:
            self._load_poems()
            a2p = _alias_map()
            c: dict[str, int] = {}
            for p in self._poems:
                if keyword in p["text"] or keyword in p["title"]:
                    author = a2p.get(p["author"], p["author"])
                    c[author] = c.get(author, 0) + 1
            cnt = sorted(c.items(), key=lambda x: -x[1])[:50]
            self._imagery_cache[keyword] = cnt
        return [{"poet": k, "n": v} for k, v in cnt[:top]]

    def group_info(self, gname: str) -> Optional[dict]:
        return {"group": gname, "members": self.groups.get(gname)} if gname in self.groups else None

    def all_groups(self) -> list[str]:
        return list(self.groups)

    def top_poets(self, top: int = 5) -> list[dict]:
        """按存诗量排名（标准名去重，繁体条目与无名氏归属不计入）。"""
        skip = {"不詳", "不详", "無名氏", "无名氏", "佚名", "闕名", "阙名"}
        rows = {}
        for name, p in self.poets.items():
            if self._a2p.get(name, name) != name or name in skip:
                continue  # 繁体原键计数已并入标准名；无名氏不是诗人
            n = p.get("n_poems") or 0
            if n:
                rows[name] = n
        best = sorted(rows.items(), key=lambda x: -x[1])[:top]
        return [{"poet": k, "n": v} for k, v in best]


class Neo4jGraph:
    """真实 Neo4j 后端：环境变量 NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD 存在时启用。
    Cypher 全部参数化模板。"""

    def __init__(self) -> None:
        from neo4j import GraphDatabase  # noqa: 延迟导入
        import os
        uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        self.driver = GraphDatabase.driver(
            uri, auth=(os.environ.get("NEO4J_USER", "neo4j"),
                       os.environ.get("NEO4J_PASSWORD", "poet-kgqa")))
        self.driver.verify_connectivity()

    def _run(self, query: str, **params) -> list[dict]:
        with self.driver.session() as s:
            return [dict(r) for r in s.run(query, **params)]

    def poet_card(self, name: str) -> Optional[dict]:
        rows = self._run(
            "MATCH (p:Poet {name:$n}) "
            "OPTIONAL MATCH (p)-[:MEMBER]->(g:Group) "
            "OPTIONAL MATCH (p)-[a:ASSOC]-(q:Poet) "
            "RETURN p.name AS name, p.desc AS desc, p.dynasty AS dynasty, p.n_poems AS n_poems, "
            "p.head30 AS head30, collect(DISTINCT g.gname) AS groups, "
            "collect(DISTINCT {poet:q.name, rel:a.rel, n_evidence:a.n_evidence}) AS associates", n=name)
        if not rows:
            return None
        r = rows[0]
        r["associates"] = [a for a in r["associates"] if a["poet"]]
        return r

    def ego(self, name: str, depth: int = 1) -> dict:
        depth = max(1, min(int(depth), 3))  # 变长路径上限，防深度注入放大遍历
        rows = self._run(
            f"MATCH (p:Poet {{name:$n}})-[a:ASSOC*1..{depth}]-(q:Poet) "
            "WITH p, q, a LIMIT 200 UNWIND a AS rel "
            "WITH p, q, rel LIMIT 500 "
            "RETURN DISTINCT startNode(rel).name AS f, endNode(rel).name AS t, rel.rel AS r, p.name AS me", n=name)
        nodes: dict[str, dict] = {}
        edges = []
        for r in rows:
            edges.append({"from": r["f"], "to": r["t"], "label": r["r"], "id": f"{r['f']}|{r['t']}"})
            for x in (r["f"], r["t"]):
                if x not in nodes:
                    nodes[x] = {"id": x, "label": x, "group": "head" if x == r["me"] else "poet"}
        return {"nodes": list(nodes.values()), "edges": edges}

    def relation(self, a: str, b: str) -> dict:
        rows = self._run(
            "MATCH (x:Poet {name:$a})-[r:ASSOC]->(y:Poet {name:$b}) "
            "RETURN r.rel AS rel, r.n_evidence AS n_evidence", a=a, b=b)
        rows2 = self._run(
            "MATCH (x:Poet {name:$a})<-[r:ASSOC]-(y:Poet {name:$b}) "
            "RETURN r.rel AS rel, r.n_evidence AS n_evidence", a=a, b=b)
        allr = [dict(x, direction=f"{a}→{b}") for x in rows] + \
               [dict(x, direction=f"{b}→{a}") for x in rows2]
        ev = self._evidence_index()
        for x in allr:
            x["poems"] = [e["title"] for e in ev.get((a if x["direction"].startswith(a + "→") else b,
                                                     b if x["direction"].endswith("→" + b) else a,
                                                     x["rel"]), [])][:5]
        return {"a": a, "b": b, "connected": bool(allr), "edges": allr}

    def _evidence_index(self) -> dict:
        """证据诗篇存于数据层（edges_clean.jsonl），按需加载回填。"""
        if not hasattr(self, "_ev"):
            import json
            self._ev = {}
            f = PROC / "edges_clean.jsonl"
            if f.exists():
                for line in f.read_text(encoding="utf-8").splitlines():
                    r = json.loads(line)
                    self._ev[(r["src"], r["dst"], r["rel"])] = r["evidence"]
        return self._ev

    def shortest_path(self, a: str, b: str) -> Optional[list[str]]:
        rows = self._run(
            "MATCH p = shortestPath((x:Poet {name:$a})-[:ASSOC*..6]-(y:Poet {name:$b})) "
            "RETURN [n IN nodes(p) | n.name] AS names", a=a, b=b)
        return rows[0]["names"] if rows else None

    def common_friends(self, a: str, b: str) -> list[str]:
        rows = self._run(
            "MATCH (x:Poet {name:$a})-[:ASSOC]-(m:Poet)-[:ASSOC]-(y:Poet {name:$b}) "
            "RETURN DISTINCT m.name AS n", a=a, b=b)
        return [r["n"] for r in rows]

    def top_imagery(self, keyword: str, top: int = 10) -> list[dict]:
        # 正文不在图中；为与 JsonlGraph 口径一致（正文+标题扫描），统一委托底表扫描并缓存
        if not hasattr(self, "_jsonl_stats"):
            self._jsonl_stats = JsonlGraph()
        return self._jsonl_stats.top_imagery(keyword, top)

    def all_groups(self) -> list[str]:
        return [r["g"] for r in self._run("MATCH (g:Group) RETURN g.gname AS g ORDER BY g.gname")]

    def top_poets(self, top: int = 5) -> list[dict]:
        return self._run(
            "MATCH (p:Poet)-[:WROTE]->(w) WHERE NOT p.name IN ['不詳','不详','無名氏','无名氏','佚名'] "
            "RETURN p.name AS poet, count(w) AS n ORDER BY n DESC LIMIT $top", top=top)


def get_graph():
    """优先 Neo4j，失败/未配置则 JSONL 兜底（系统永不离线）。"""
    import os
    if os.environ.get("POET_KGQA_USE_NEO4J") == "1":
        try:
            return Neo4jGraph()
        except Exception as e:  # 库未启动/密码错误/驱动缺失：兜底而非崩溃
            print(f"[graph_service] Neo4j 不可用（{type(e).__name__}: {e}），退回 JsonlGraph 后端")
    return JsonlGraph()


if __name__ == "__main__":
    g = get_graph()
    print("backend:", type(g).__name__, "| poets:", len(getattr(g, "poets", [])) or "-")
    print("李白 邻居:", [x["id"] for x in g.ego("李白")["nodes"]][:12] if hasattr(g, "ego") else "")
    rel = g.relation("杜甫", "李白")
    print("杜甫-李白:", json.dumps(rel, ensure_ascii=False)[:300])
    print("李白→韩愈 路径:", g.shortest_path("李白", "韩愈"))
    print("李白/杜甫 共同好友:", g.common_friends("李白", "杜甫"))
    print("写月 TOP5:", g.top_imagery("月")[:5] if hasattr(g, "top_imagery") else "")
