# -*- coding: utf-8 -*-
"""
rag/retriever.py — 语义检索层
优先级: faiss/npy 向量索引（需 bge 模型）→ 关键词扫描兜底（无模型也能跑）
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
IDX = ROOT / "data" / "index"
PROC = ROOT / "data" / "processed"
QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："  # bge v1.5 官方查询前缀


class Retriever:
    def __init__(self, topk: int = 5):
        self.topk = topk
        self.meta: list[dict] = []
        meta_file = IDX / "meta.jsonl"
        if meta_file.exists():
            self.meta = [json.loads(l) for l in meta_file.read_text(encoding="utf-8").splitlines()]
        self.vecs = None
        self.model = None
        self._try_load()

    def _query_variants(self, query: str) -> list[str]:
        """原句 + 繁体变体（语料为繁体）。"""
        vs = [query]
        try:
            from zhconv import convert
            t = convert(query, "zh-hant")
            if t != query:
                vs.append(t)
        except Exception:
            pass
        return vs

    def _try_load(self) -> None:
        try:
            import numpy as np
            if (IDX / "vectors.faiss").exists():
                import faiss
                self.faiss = faiss.read_index(str(IDX / "vectors.faiss"))
                self.vecs = "faiss"
            elif (IDX / "vectors.npy").exists():
                self.vecs = np.load(IDX / "vectors.npy")
            else:
                return
            from sentence_transformers import SentenceTransformer
            snaps = sorted((Path.home() / ".cache" / "huggingface" / "hub"
                            / "models--BAAI--bge-small-zh-v1.5" / "snapshots").glob("*"))
            if snaps:
                self.model = SentenceTransformer(str(snaps[-1]))
        except Exception:
            self.vecs = None  # 兜底模式

    @property
    def mode(self) -> str:
        if self.vecs is None or self.model is None:
            return "keyword-fallback"
        return "faiss" if isinstance(self.vecs, str) else "numpy"

    def search(self, query: str, topk: Optional[int] = None) -> list[dict]:
        k = topk or self.topk
        if self.vecs is None or self.model is None or not self.meta:
            return self._keyword_scan(query, k)
        # 简繁双路：语料为繁体，简体问句补一路繁体变体；两路余弦分数量纲不可比，
        # 按倒数排名（RRF）归并，避免繁体路的整体高分淹没简体路的正确命中
        variants = self._query_variants(query)
        merged: dict[int, dict] = {}
        for v in variants:
            for rank, (s, i) in enumerate(self._search_vec(v, k)):
                if i < 0 or i >= len(self.meta):
                    continue
                fused = 1.0 / (60 + rank + 1)
                m = merged.get(i)
                if m is None or fused > m["_fused"]:
                    merged[i] = {**dict(self.meta[i]), "_fused": fused, "score": round(float(s), 3)}
        # 诗题精确加权：问句中完整出现某诗题（≥2字）视为强信号，置顶
        merged.update(self._title_hits(variants))
        out = sorted(merged.values(), key=lambda x: -x.get("_fused", 1.0))[:k]
        for o in out:
            o.pop("_fused", None)
        return out

    def _title_hits(self, variants: list[str]) -> dict[int, dict]:
        """题名子串命中 → 以 1.0 分置顶（高于一般向量得分），并排前 k。
        仅取 ≥3 字题名：二字题（感時/夜思/登樓…）过泛，会劫持名句问句。"""
        qs = " ".join(variants)
        out: dict[int, dict] = {}
        for i, m in enumerate(self.meta):
            t = (m.get("title") or "").strip()
            if len(t) >= 3 and t in qs:
                out[i] = {**dict(m), "score": 1.0}
        return out

    def _search_vec(self, query: str, k: int) -> list[tuple[float, int]]:
        qv = self.model.encode([QUERY_PREFIX + query], normalize_embeddings=True)
        import numpy as np
        qv = np.asarray(qv, dtype="float32")
        if isinstance(self.vecs, str):  # faiss
            scores, ids = self.faiss.search(qv, k)
            return list(zip(scores[0].tolist(), ids[0].tolist()))
        scores = (self.vecs @ qv.T)[:, 0]
        ids = scores.argsort()[-k:][::-1].tolist()
        return list(zip(scores[ids].tolist(), ids))

    def _keyword_scan(self, query: str, k: int) -> list[dict]:
        """兜底：按题名/正文包含命中排序（无向量模型时保证可用）"""
        try:
            from zhconv import convert
            query = query + convert(query, "zh-hant")  # 繁体语料匹配
        except Exception:
            pass
        chars = [c for c in dict.fromkeys(query) if '\u4e00' <= c <= '\u9fff']
        if not chars:
            return []
        hits: list[tuple[float, dict]] = []
        for line in (PROC / "poems.jsonl").read_text(encoding="utf-8").splitlines():
            p = json.loads(line)
            sc = sum(1 for c in chars if c in p["title"]) * 3 + \
                 sum(1 for c in chars if c in p["text"][:200])
            if sc > 0:
                hits.append((sc, {"id": p["id"], "title": p["title"], "author": p["author"],
                                  "preview": p["text"][:80], "score": sc}))
            if len(hits) > 5000:
                break
        hits.sort(key=lambda x: -x[0])
        return [h[1] for h in hits[:k]]


if __name__ == "__main__":
    r = Retriever()
    print("mode:", r.mode)
    for h in r.search("月亮 思乡", 3):
        print(h["score"], h["author"], "《" + h["title"] + "》", h["preview"][:30])
