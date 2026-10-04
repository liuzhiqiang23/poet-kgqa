# -*- coding: utf-8 -*-
"""scripts/07_fetch_avatars.py — 从维基百科词条抓诗人古典画像头像（公有领域）
抓取失败的诗人不入库，由前端印章字 SVG 兜底。UA 与限速遵循 Wikimedia 政策。
"""
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "static" / "avatars"
OUT.mkdir(parents=True, exist_ok=True)

DATES = json.load(open(ROOT / "data" / "alias" / "poet_dates.json", encoding="utf-8"))
POETS = sorted(k for k in DATES if not k.startswith("_"))

UA = {"User-Agent": "poet-kgqa-graduation-demo/1.0 (educational use; contact: local)"}

def fetch(url: str, timeout: int = 15) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception:
        return None

ok, miss = [], []
for name in POETS:
    dest = OUT / f"{name}.jpg"
    if dest.exists():
        ok.append(name)
        continue
    api = ("https://zh.wikipedia.org/api/rest_v1/page/summary/"
           + urllib.request.quote(name))
    raw = fetch(api)
    data = json.loads(raw) if raw else None
    thumb = (data or {}).get("thumbnail", {}).get("source")
    if not thumb:
        miss.append(name)
        print(f"[miss] {name}: 无词条缩略图")
        time.sleep(0.3)
        continue
    # 放大到 500px（REST 缩略图 URL 形如 /320px-xxx）
    big = thumb
    if "/px-" in big:
        import re
        big = re.sub(r"/(\d+)px-", "/500px-", big, count=1)
    img = fetch(big) or fetch(thumb)
    if img and len(img) > 3000:
        dest.write_bytes(img)
        ok.append(name)
        print(f"[ok]   {name}: {len(img)//1024}KB")
    else:
        miss.append(name)
        print(f"[miss] {name}: 图片下载失败")
    time.sleep(0.3)

print(f"\n完成：{len(ok)} 成功 / {len(miss)} 缺失")
print("缺失名单：", " ".join(miss) if miss else "无")
