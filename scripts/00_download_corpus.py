# -*- coding: utf-8 -*-
"""
00_download_corpus.py — 从 jsDelivr CDN 下载 chinese-poetry 全唐诗数据
（GitHub 直连不通，jsDelivr 为本机可用通道；仅下载，不做解析）

用法:
    python 00_download_corpus.py            # 下载 authors + poet.tang.0..57 卷
    python 00_download_corpus.py --check    # 只检查已下载数量与大小
"""
import argparse
import concurrent.futures as cf
import json
import sys
import time
import urllib.request
from pathlib import Path

BASE = "https://cdn.jsdelivr.net/gh/chinese-poetry/chinese-poetry@master/%E5%85%A8%E5%94%90%E8%AF%97"
RAW = Path(__file__).resolve().parent.parent / "data" / "raw" / "tang"
MAX_VOL = 58000  # 全唐诗分卷按千首偏移：0,1000,...,57000 共 58 卷
VOL_STEP = 1000


def fetch(url: str, dest: Path, retries: int = 3) -> tuple[str, int]:
    """单文件下载：404 直接抛（跳过），网络错误退避重试。jsDelivr 会限并发，勿加大 workers。"""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            dest.write_bytes(data)
            return dest.name, len(data)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            last = e
        except Exception as e:
            last = e
        time.sleep(2 * (attempt + 1))
    raise last


def download_all(workers: int = 2) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    tasks = [(f"{BASE}/authors.tang.json", RAW / "authors.tang.json")]
    tasks += [(f"{BASE}/poet.tang.{i}.json", RAW / f"poet.tang.{i}.json") for i in range(0, MAX_VOL, VOL_STEP)]
    # 跳过已存在且 >10KB 的文件（断点续传）
    tasks = [(u, d) for u, d in tasks if not (d.exists() and d.stat().st_size > 10000)]
    print(f"to download: {len(tasks)} files -> {RAW}")
    ok, fail = 0, 0
    with cf.ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(fetch, u, d): d.name for u, d in tasks}
        for fut in cf.as_completed(futs):
            name = futs[fut]
            try:
                fname, size = fut.result()
                print(f"  ok  {fname}  {size//1024}KB", flush=True)
                ok += 1
            except Exception as e:  # 404 等
                print(f"  skip {name}: {type(e).__name__}", flush=True)
                fail += 1
    print(f"done: {ok} ok, {fail} skipped/failed")


def check() -> None:
    vols = sorted(RAW.glob("poet.tang.*.json"))
    total = sum(v.stat().st_size for v in vols)
    print(f"volumes: {len(vols)}, size: {total/1024/1024:.1f}MB")
    # 抽验 JSON 可解析
    bad = []
    for v in vols:
        try:
            json.loads(v.read_text(encoding="utf-8"))
        except Exception:
            bad.append(v.name)
    print("json parse:", "ALL OK" if not bad else f"BAD: {bad}")
    if vols:
        poems = sum(len(json.loads(v.read_text(encoding="utf-8"))) for v in vols)
        print(f"poems total: {poems}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args()
    if a.check:
        check()
    else:
        download_all(a.workers)
        check()
