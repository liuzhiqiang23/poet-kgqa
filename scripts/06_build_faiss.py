# -*- coding: utf-8 -*-
"""
06_build_faiss.py — 全唐诗文向量化建库（bge-small-zh-v1.5 + FAISS/numpy）

有 faiss-cpu 则建 IndexFlatIP（归一化后=cosine），否则 numpy 矩阵兜底（5.7万×512 完全扛得住）。
模型从本机 HF 缓存加载（离线）。跑位：CPU。

输出: data/index/vectors.(faiss|npy) + data/index/meta.jsonl（id/title/author/preview）
运行: 用带 torch 的解释器，如：
  HF_HUB_OFFLINE=1 <venv-python> scripts/06_build_faiss.py [--limit N]
"""
import argparse
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
IDX = ROOT / "data" / "index"
BGE_REL = Path(".cache") / "huggingface" / "hub" / "models--BAAI--bge-small-zh-v1.5" / "snapshots"


def find_bge() -> Path:
    """多候选探测 bge 缓存（不同 shell 的 HOME 解析可能不同）"""
    candidates = []
    if os.environ.get("BGE_MODEL_DIR"):
        candidates.append(Path(os.environ["BGE_MODEL_DIR"]))
    for env in ("HF_HOME", "HF_HUB_CACHE"):
        if os.environ.get(env):
            candidates.append(Path(os.environ[env]) / "models--BAAI--bge-small-zh-v1.5" / "snapshots")
            candidates.append(Path(os.environ[env]) / "snapshots")
    candidates += [Path.home() / BGE_REL,
                   Path(os.environ.get("USERPROFILE", "C:/Users/Lenovo")) / BGE_REL,
                   Path("C:/Users/Lenovo") / BGE_REL]
    for c in candidates:
        snaps = sorted(c.glob("*")) if c.exists() else []
        if snaps:
            return snaps[-1]
    raise SystemExit(f"bge 模型缓存未找到，尝试过: {[str(c) for c in candidates]}")


def load_model():
    from sentence_transformers import SentenceTransformer
    model_dir = str(find_bge())
    print("model:", model_dir)
    return SentenceTransformer(model_dir)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只嵌入前 N 首（调试用）")
    ap.add_argument("--batch", type=int, default=32)
    a = ap.parse_args()

    import numpy as np
    model = load_model()
    IDX.mkdir(parents=True, exist_ok=True)

    docs, metas = [], []
    for line in (PROC / "poems.jsonl").read_text(encoding="utf-8").splitlines():
        p = json.loads(line)
        docs.append(f"{p['title']}\n{p['text'][:256]}")
        metas.append({"id": p["id"], "title": p["title"], "author": p["author"],
                      "preview": p["text"][:80]})
        if a.limit and len(docs) >= a.limit:
            break
    print(f"docs: {len(docs)}")

    import numpy as np
    all_vecs = []
    t0 = time.time()
    for i in range(0, len(docs), a.batch * 25):  # 分块编码，限制峰值内存并定期落盘
        chunk = docs[i:i + a.batch * 25]
        v = model.encode(chunk, batch_size=a.batch, normalize_embeddings=True,
                         show_progress_bar=False)
        all_vecs.append(np.asarray(v, dtype="float32"))
        print(f"  {i + len(chunk)}/{len(docs)}  {time.time()-t0:.0f}s", flush=True)
    vecs = np.concatenate(all_vecs)
    del all_vecs
    print(f"encoded in {time.time()-t0:.0f}s, shape={vecs.shape}", flush=True)

    with (IDX / "meta.jsonl").open("w", encoding="utf-8") as f:
        for m in metas:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")

    try:
        import faiss
        index = faiss.IndexFlatIP(vecs.shape[1])
        index.add(vecs)
        faiss.write_index(index, str(IDX / "vectors.faiss"))
        print("faiss index ->", IDX / "vectors.faiss")
    except ImportError:
        np.save(IDX / "vectors.npy", vecs)
        print("numpy fallback ->", IDX / "vectors.npy")
    print("done")


if __name__ == "__main__":
    main()
