# -*- coding: utf-8 -*-
"""docx 目录预填充（--auto）+ WPS 兼容清理

用法: python add_toc_placeholders.py --auto <docx路径>

做三件事：
1. 给正文所有 Heading1/2/3 段落插入 _Toc1000NN 书签；
2. 在目录 sdt 的 separate 与 end 之间插入缓存条目（toc 1/2/3 样式、
   点线右制表位、PAGEREF 域缓存页码）——打开时 Word/WPS 的
   updateFields 会用真实页码覆盖，预填仅保证目录在更新前不空白；
3. 移除空 <w:pgNumType/>（WPS 兼容）。
页码为按 content.json 块序估算的连续页码，仅供参考。
"""
import json
import re
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
TOC_STYLE = {1: "9", 2: "11", 3: "12"}          # styles.xml: toc 1 / toc 2 / toc 3
TOC_INDENT = {1: "", 2: '<w:ind w:left="360"/>', 3: '<w:ind w:left="720"/>'}
CHARS_PER_PAGE = 850
BM_ID0 = 100000


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def heading_iter(xml: str):
    """依次产出 (段起点, 段终点, 级别, 段全文)"""
    for m in re.finditer(r'<w:p><w:pPr><w:pStyle w:val="Heading([123])"/>.*?</w:p>', xml, re.S):
        yield m.start(), m.end(), int(m.group(1)), m.group(0)


def para_text(fragment: str) -> str:
    return "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", fragment))


def estimate_pages(headings, content_path: Path):
    """按 content.json 块序估算每个标题的连续页码"""
    sec = json.loads(content_path.read_text(encoding="utf-8"))["sections"]
    order = ["ABSTRACT_CN", "ABSTRACT_EN", "BODY", "APPENDIX", "ACKNOWLEDGEMENTS"]
    blocks = [b for k in order for b in sec.get(k, [])]
    cum = 0
    pages = []
    hi = 0
    for b in blocks:
        t = b.get("type")
        if t in ("h1", "h2", "h3"):
            if hi < len(headings):
                pages.append(1 + cum // CHARS_PER_PAGE)
                hi += 1
            cum += 60
        elif t == "p":
            cum += len(b.get("text", ""))
        elif t == "li":
            cum += len(b.get("text", "")) + 20
        elif t == "image":
            cum += 700
        elif t == "table":
            cum += sum(len(c) for row in b.get("rows", []) for c in row) + 40 * len(b.get("rows", []))
        elif t == "tbltitle":
            cum += 40
        elif t == "alg":
            cum += sum(len(l) for l in b.get("lines", [])) + 80
    while len(pages) < len(headings):      # 兜底：标题数多于块时顺延
        pages.append(pages[-1] if pages else 1)
    return pages


def main() -> None:
    args = sys.argv[1:]
    if "--auto" in args:
        args.remove("--auto")
    path = Path(args[0]) if args else HERE / "毕设论文-融合知识图谱与大语言模型的诗人知识问答与对话系统设计.docx"

    zin = zipfile.ZipFile(path)
    items = {n: zin.read(n) for n in zin.namelist()}
    zin.close()
    xml = items["word/document.xml"].decode("utf-8")

    # 幂等：先剥掉旧书签与旧缓存条目
    xml = re.sub(r'<w:bookmark(?:Start|End) w:id="\d+" w:name="_Toc\d+"/>', "", xml)

    heads = [(s, e, lv, para_text(frag)) for s, e, lv, frag in heading_iter(xml)]
    if not heads:
        print("no headings found — skip");  return

    # 1) 插书签（从后往前插避免位移）
    for i in range(len(heads) - 1, -1, -1):
        s, e, lv, _ = heads[i]
        frag = xml[s:e]
        j = frag.find("</w:pPr>") + len("</w:pPr>")
        frag = (frag[:j]
                + f'<w:bookmarkStart w:id="{BM_ID0 + i}" w:name="_Toc{BM_ID0 + i}"/>'
                + frag[j:-len("</w:p>")]
                + f'<w:bookmarkEnd w:id="{BM_ID0 + i}"/></w:p>')
        xml = xml[:s] + frag + xml[e:]

    # 2) 目录缓存条目
    pages = estimate_pages([h[2] for h in heads], HERE / "content.json")
    ents = []
    for i, (_, _, lv, title) in enumerate(heads):
        a = f"_Toc{BM_ID0 + i}"
        ents.append(
            f'<w:p><w:pPr><w:pStyle w:val="{TOC_STYLE[lv]}"/>{TOC_INDENT[lv]}'
            '<w:tabs><w:tab w:val="right" w:leader="dot" w:pos="9026"/></w:tabs>'
            '<w:spacing w:before="120" w:after="60"/></w:pPr>'
            f'<w:hyperlink w:anchor="{a}" w:history="1">'
            '<w:r><w:rPr><w:rStyle w:val="Hyperlink"/></w:rPr>'
            f'<w:t xml:space="preserve">{esc(title)}</w:t></w:r>'
            '<w:r><w:tab/></w:r>'
            '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            f'<w:r><w:instrText xml:space="preserve"> PAGEREF {a} \\h </w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
            f'<w:r><w:t>{pages[i]}</w:t></w:r>'
            '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
            '</w:hyperlink></w:p>')
    entries = "".join(ents)

    i_alias = xml.find('<w:alias w:val="目录"/>')
    if i_alias < 0:
        print("TOC sdt not found — entries skipped")
    else:
        i_sep = xml.find('fldCharType="separate"', i_alias)
        i_ins = xml.find("</w:p>", i_sep) + len("</w:p>")
        i_close = xml.find("</w:sdtContent>", i_ins)
        endp = '<w:p><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
        i_endp = xml.rfind(endp, i_ins, i_close)
        tail = xml[i_endp:i_close] if i_endp >= 0 else endp
        xml = xml[:i_ins] + entries + tail + xml[i_close:]

    # 3) WPS 兼容：空 pgNumType 移除
    xml = xml.replace("<w:pgNumType/>", "")

    items["word/document.xml"] = xml.encode("utf-8")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zout:
        for n, data in items.items():
            if n.endswith("/"):        # 跳过 zip 目录占位条目
                continue
            zout.writestr(n, data)
    print(f"TOC placeholders written: {len(heads)} headings -> {path.name}")
    print("page estimate:", pages)


if __name__ == "__main__":
    main()
