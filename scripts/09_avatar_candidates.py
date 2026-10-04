# -*- coding: utf-8 -*-
"""scripts/09_avatar_candidates.py — 为 8 位缺头像诗人三路挖候选图
1) Wikidata P18 图像字段  2) zh/en/ja 维基词条内嵌图  3) Commons 分类文件
全部下载到 web/static/avatars/_cand/{name}-{n}.jpg 供人工目检挑选。
"""
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAND = ROOT / "web" / "static" / "avatars" / "_cand"
CAND.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "poet-kgqa-demo/1.0 (educational)"}
SKIP = re.compile(r'\.djvu|\.pdf|\.tif|\.svg|地图|map|Map|Flag|Coat|logo|Logo|图标|书影')

POETS = ["孟郊", "杨炯", "罗隐", "贾岛", "杜荀鹤", "刘禹锡", "崔颢", "张九龄"]
TRAD = {"杨炯": "楊炯", "罗隐": "羅隱", "贾岛": "賈島", "崔颢": "崔顥", "张九龄": "張九齡", "刘禹锡": "劉禹錫", "杜荀鹤": "杜荀鶴"}

def get(url, timeout=15, tries=3):
    for _ in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except Exception:
            time.sleep(1)
    return None

def save(name, idx, title, imginfo_url):
    u = imginfo_url
    if not u or not u.lower().split("?")[0].endswith((".jpg", ".jpeg", ".png")):
        return False
    img = get(u)
    if img and len(img) > 8000:
        (CAND / f"{name}-{idx}.jpg").write_bytes(img)
        print(f"  [cand] {name}-{idx} <- {title[:66]}")
        return True
    return False

def ii_urls(titles):
    """Commons imageinfo 批量：标题列表 -> {title: thumburl}"""
    out = {}
    for i in range(0, len(titles), 20):
        batch = titles[i:i+20]
        q = urllib.parse.quote("|".join(batch), safe="")
        raw = get("https://commons.wikimedia.org/w/api.php?action=query&format=json"
                  f"&titles={q}&prop=imageinfo&iiprop=url&iiurlwidth=600")
        try:
            for p in json.loads(raw)["query"]["pages"].values():
                ii = p.get("imageinfo", [{}])[0]
                out[p["title"]] = ii.get("thumburl") or ii.get("url")
        except Exception:
            pass
        time.sleep(0.3)
    return out

for name in POETS:
    print(f"== {name} ==")
    variants = [name] + ([TRAD[name]] if TRAD.get(name) else [])
    got = 0

    # 1) Wikidata P18
    for v in variants:
        raw = get("https://www.wikidata.org/w/api.php?action=wbsearchentities&format=json"
                  f"&language=zh&limit=3&search={urllib.parse.quote(v, safe='')}")
        try:
            ids = [e["id"] for e in json.loads(raw)["search"]]
        except Exception:
            ids = []
        for qid in ids:
            raw = get(f"https://www.wikidata.org/w/api.php?action=wbgetclaims&format=json&entity={qid}&property=P18")
            try:
                f18 = json.loads(raw)["claims"].get("P18", [])
                files = ["File:" + c["mainsnak"]["datavalue"]["value"] for c in f18]
            except Exception:
                files = []
            for t, u in ii_urls(files).items():
                if save(name, got, t, u):
                    got += 1
            time.sleep(0.3)

    # 2) zh/en/ja 词条内嵌图
    for lang in ("zh", "en", "ja"):
        for v in variants[:1]:
            raw = get(f"https://{lang}.wikipedia.org/w/api.php?action=query&format=json&redirects=1"
                      f"&titles={urllib.parse.quote(v, safe='')}&prop=images&imlimit=50")
            try:
                titles = [i["title"] for p in json.loads(raw)["query"]["pages"].values()
                          for i in p.get("images", [])]
            except Exception:
                titles = []
            titles = [t for t in titles if not SKIP.search(t)]
            for t, u in ii_urls(titles).items():
                if save(name, got, t, u):
                    got += 1
            time.sleep(0.3)

    # 3) Commons 分类（英文分类名猜测 + 搜索带 Category: 前缀的结果）
    for v in variants:
        raw = get("https://commons.wikimedia.org/w/api.php?action=query&format=json&list=search"
                  f"&srsearch={urllib.parse.quote('incategory:' + v, safe='') if False else urllib.parse.quote(v + ' incategory', safe='')}&srlimit=1")
    # 分类名不可靠，改为直接搜 "名字 portrait/像/画像" 的文件命名空间，取未下载过的
    for term in (f"{name} portrait", f"{name} 像", f"{name} 畫像"):
        q = urllib.parse.quote(term, safe="")
        raw = get("https://commons.wikimedia.org/w/api.php?action=query&format=json&generator=search"
                  f"&gsrsearch={q}&gsrnamespace=6&gsrlimit=8&prop=imageinfo&iiprop=url&iiurlwidth=600")
        try:
            for p in sorted(json.loads(raw)["query"]["pages"].values(), key=lambda x: x.get("index", 9)):
                t = p["title"]
                if SKIP.search(t) or any(k in t for k in ("年譜", "年谱", "研究", "文集")):
                    continue
                ii = p.get("imageinfo", [{}])[0]
                if save(name, got, t, ii.get("thumburl") or ii.get("url")):
                    got += 1
        except Exception:
            pass
        time.sleep(0.3)
    print(f"  共 {got} 张候选")

print("完成 ->", CAND)
