# -*- coding: utf-8 -*-
"""docx 交付前校验

用法: python postcheck.py <docx路径>
退出码 0 = 通过；1 = 有错误。
已知可接受 warning：表格/图题/算法块的行距与正文不同（有意为之）。
"""
import json
import re
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).parent


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        HERE / "毕设论文-融合知识图谱与大语言模型的诗人知识问答与对话系统设计.docx"
    errors, warnings = [], []

    z = zipfile.ZipFile(path)
    names = z.namelist()
    xml = z.read("word/document.xml").decode("utf-8")

    # 1) 目录：标题数 = 书签数 = 缓存条目数，锚点一一对应
    n_heads = len(re.findall(r'<w:pStyle w:val="Heading[123]"/>', xml))
    bms = re.findall(r'<w:bookmarkStart w:id="\d+" w:name="(_Toc\d+)"/>', xml)
    anchors = re.findall(r'<w:hyperlink w:anchor="(_Toc\d+)"', xml)
    if not (n_heads == len(bms) == len(anchors)):
        errors.append(f"TOC 不完整: headings={n_heads} bookmarks={len(bms)} entries={len(anchors)}")
    elif bms != anchors:
        errors.append("TOC 锚点与书签顺序不一致")
    if 'fldCharType="separate"' not in xml or xml.count('w:val="目录"') == 0:
        errors.append("TOC 域缺失")

    # 2) 页码兼容：不允许空 pgNumType
    if "<w:pgNumType/>" in xml:
        errors.append("存在空 <w:pgNumType/>（WPS 兼容问题，先跑 add_toc_placeholders.py）")

    # 3) 插图：media 数与 content.json 图块数一致
    n_media = len([n for n in names if n.startswith("word/media/") and not n.endswith("/")])
    blocks = json.loads((HERE / "content.json").read_text(encoding="utf-8"))["sections"]
    n_figs = sum(1 for v in blocks.values() for b in v if b.get("type") == "image")
    if n_media != n_figs:
        errors.append(f"插图数量不符: media={n_media} figs={n_figs}")

    # 4) 域更新开关与字体
    settings = z.read("word/settings.xml").decode("utf-8")
    if "w:updateFields" not in settings:
        warnings.append("settings.xml 无 updateFields，打开时不会自动刷新目录页码")
    styles = z.read("word/styles.xml").decode("utf-8")
    for f in ('w:eastAsia="SimSun"', 'w:eastAsia="SimHei"'):
        if f not in styles:
            errors.append(f"styles.xml 缺字体 {f}")

    # 5) 空段/占位符残留
    for pat, msg in [(r"【[^】]{1,12}】", "封面占位符"), (r"\bTODO\b", "TODO")]:
        hits = re.findall(pat, xml)
        if hits:
            warnings.append(f"发现 {msg}: {sorted(set(hits))[:6]}")

    # 6) 体量
    text = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml))
    print(f"字符总数(含目录缓存): {len(text)}")
    print(f"标题 {n_heads} | 插图 {n_media} | TOC 条目 {len(anchors)}")

    for w in warnings:
        print("WARNING:", w)
    for e in errors:
        print("ERROR:", e)
    print("postcheck:", "PASS" if not errors else f"FAIL ({len(errors)} errors)")
    sys.exit(0 if not errors else 1)


if __name__ == "__main__":
    main()
