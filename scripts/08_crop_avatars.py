# -*- coding: utf-8 -*-
"""scripts/08_crop_avatars.py — 头像智能裁切
白描/立轴画像留白多，object-fit:cover 圆形裁切后只剩噪点。
本脚本按"与边缘底色的色差"找人物内容包围盒，扩边后中心裁方、统一 256px。
"""
from pathlib import Path
from PIL import Image

AV = Path(__file__).resolve().parent.parent / "web" / "static" / "avatars"

def content_bbox(im: Image.Image):
    """以四角中值色为底色，返回与底色差异显著的像素包围盒。"""
    rgb = im.convert("RGB")
    w, h = rgb.size
    px = rgb.load()
    corners = [px[0, 0], px[w-1, 0], px[0, h-1], px[w-1, h-1]]
    bg = tuple(sorted(c[i] for c in corners)[1] for i in range(3))  # 中值抗单角异常
    step = max(2, min(w, h) // 220)  # 采样步长，控制耗时
    x0, y0, x1, y1 = w, h, 0, 0
    found = False
    for y in range(0, h, step):
        for x in range(0, w, step):
            r, g, b = px[x, y]
            if abs(r-bg[0]) + abs(g-bg[1]) + abs(b-bg[2]) > 66:
                found = True
                if x < x0: x0 = x
                if x > x1: x1 = x
                if y < y0: y0 = y
                if y > y1: y1 = y
    if not found:
        return None
    return (x0, y0, x1+1, y1+1)

for f in sorted(AV.glob("*.jpg")):
    im = Image.open(f).convert("RGB")
    w, h = im.size
    bb = content_bbox(im)
    if bb:
        bx0, by0, bx1, by1 = bb
        pad = int(max(bx1-bx0, by1-by0) * 0.08)
        bx0, by0 = max(0, bx0-pad), max(0, by0-pad)
        bx1, by1 = min(w, bx1+pad), min(h, by1+pad)
        im = im.crop((bx0, by0, bx1, by1))
    # 中心裁方
    w, h = im.size
    s = min(w, h)
    im = im.crop(((w-s)//2, (h-s)//2, (w+s)//2, (h+s)//2)).resize((256, 256), Image.LANCZOS)
    im.save(f, quality=88)
    print(f"{f.stem}: 裁切完成")
print("全部完成")
