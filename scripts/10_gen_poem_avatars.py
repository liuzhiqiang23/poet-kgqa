# -*- coding: utf-8 -*-
"""scripts/10_gen_poem_avatars.py — 无画像诗人的「名句诗签」头像生成
宣纸渐变底 + 竖排楷体名句 + 姓氏朱印，256×256，与系统水墨风格一致。
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

AV = Path(__file__).resolve().parent.parent / "web" / "static" / "avatars"
KAI = "C:/Windows/Fonts/simkai.ttf"

# 诗人 -> (名句, 出处不计入画面)；名句选中学课本级、无可争议者
POEMS = {
    "孟郊":   "慈母手中线",     # 《游子吟》
    "罗隐":   "今朝有酒今朝醉", # 《自遣》
    "贾岛":   "僧敲月下门",     # 《题李凝幽居》
    "杜荀鹤": "时人不识凌云木", # 《小松》
    "崔颢":   "白云千载空悠悠", # 《黄鹤楼》
}

INK = (42, 38, 30)
GOLD = (184, 154, 94)
SEAL = (157, 59, 40)
SEAL_D = (124, 45, 30)

def paper(draw):
    """竖向宣纸渐变 + 细颗粒。"""
    for y in range(256):
        t = y / 255
        r = int(248 - 10 * t); g = int(242 - 14 * t); b = int(226 - 18 * t)
        draw.line([(0, y), (256, y)], fill=(r, g, b))
    import random
    rnd = random.Random(7)
    for _ in range(900):
        x, y = rnd.randrange(256), rnd.randrange(256)
        c = rnd.choice([(228, 218, 196), (238, 230, 210), (220, 208, 184)])
        draw.point((x, y), fill=c)

def gen(name: str, line: str):
    im = Image.new("RGB", (256, 256))
    d = ImageDraw.Draw(im)
    paper(d)
    # 双线边框（外粗内细）
    d.rounded_rectangle([8, 8, 247, 247], radius=18, outline=GOLD, width=2)
    d.rounded_rectangle([13, 13, 242, 242], radius=14, outline=(*GOLD, ), width=1)
    # 竖排名句（单列居中）
    n = len(line)
    size = 46 if n <= 5 else 30
    font = ImageFont.truetype(KAI, size)
    total = n * size + (n - 1) * 6
    y = (256 - total) / 2 + size / 2
    for ch in line:
        d.text((128, y), ch, font=font, fill=INK, anchor="mm")
        y += size + 6
    # 姓氏朱印（右下）
    sfont = ImageFont.truetype(KAI, 26)
    d.rounded_rectangle([196, 196, 240, 240], radius=7, fill=SEAL, outline=SEAL_D, width=2)
    d.text((218, 218), name[0], font=sfont, fill=(247, 239, 221), anchor="mm")
    im.save(AV / f"{name}.jpg", quality=90)
    print(f"[gen] {name} <- {line}")

for poet, verse in POEMS.items():
    gen(poet, verse)
print("完成")
