# -*- coding: utf-8 -*-
"""md_parts → content.json（ensure_ascii=True，规避 JS 中文引号转义问题）"""
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
BLOCK_RE_LIST = re.compile(r"^[-*] ")


def parse_md(text: str) -> dict[str, list]:
    sections: dict[str, list] = {}
    cur = None
    for raw in text.splitlines():
        line = raw.rstrip()
        m = re.match(r"^=== (\w+) ===\s*$", line)
        if m:
            cur = m.group(1)
            sections[cur] = []
            continue
        if cur is None or not line.strip():
            continue
        if line.startswith("!FIG:"):
            path, _, cap = line[5:].partition("|")
            sections[cur].append({"type": "image", "path": path.strip(), "caption": cap.strip()})
        elif line.startswith("!ALG:"):
            cap, _, body = line[5:].partition("|")
            sections[cur].append({"type": "alg", "caption": cap.strip(),
                                  "lines": [l for l in body.split("||") if l.strip()]})
        elif line.startswith("!TBL:"):
            sections[cur].append({"type": "tbltitle", "text": line[5:].strip()})
        elif line.startswith("### "):
            sections[cur].append({"type": "h3", "text": line[4:].strip()})
        elif line.startswith("## "):
            sections[cur].append({"type": "h2", "text": line[3:].strip()})
        elif line.startswith("# "):
            sections[cur].append({"type": "h1", "text": line[2:].strip()})
        elif line.startswith("|"):
            # 表格行累积
            if sections[cur] and sections[cur][-1].get("type") == "table":
                cells = [c.strip() for c in line.strip("|").split("|")]
                if all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                    continue  # 分隔行
                sections[cur][-1]["rows"].append(cells)
            else:
                cells = [c.strip() for c in line.strip("|").split("|")]
                sections[cur].append({"type": "table", "rows": [cells]})
        elif BLOCK_RE_LIST.match(line):
            sections[cur].append({"type": "li", "text": line[2:].strip()})
        else:
            sections[cur].append({"type": "p", "text": line.strip()})
    return sections


def main() -> None:
    meta: dict[str, str] = {}
    merged: dict[str, list] = {}
    for name in ("part1.md", "part2.md", "part3.md"):
        sec = parse_md((HERE / name).read_text(encoding="utf-8"))
        for k, v in sec.items():
            if k == "META":
                for item in v:
                    key, _, val = item["text"].partition(":")
                    meta[key.strip()] = val.strip()
            else:
                merged.setdefault(k, []).extend(v)
    out = {"meta": meta, "sections": merged}
    (HERE / "content.json").write_text(json.dumps(out, ensure_ascii=True), encoding="utf-8")
    stat = {k: len(v) for k, v in merged.items()}
    total_chars = sum(len(b.get("text", "") + "".join(c for row in b.get("rows", []) for c in row))
                      for v in merged.values() for b in v)
    print("sections:", stat, "| approx chars:", total_chars)


if __name__ == "__main__":
    main()
