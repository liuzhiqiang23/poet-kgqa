# -*- coding: utf-8 -*-
"""chat/entity_link.py — 问句中的诗人指认（别名最长匹配 → 标准名）"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALIAS_FILE = ROOT / "data" / "alias" / "poet_aliases.json"
DATES_FILE = ROOT / "data" / "alias" / "poet_dates.json"


class EntityLinker:
    def __init__(self) -> None:
        aliases = json.loads(ALIAS_FILE.read_text(encoding="utf-8"))
        self.a2p: dict[str, str] = {}
        for poet, alist in aliases.items():
            if poet.startswith("_") or not isinstance(alist, list):
                continue
            self.a2p[poet] = poet
            for a in alist:
                self.a2p[a] = poet
        self.dates = {k: v for k, v in json.loads(DATES_FILE.read_text(encoding="utf-8")).items()
                      if not k.startswith("_")}

    def link(self, text: str) -> list[str]:
        """返回问句中出现的标准诗人名（按出现顺序去重）"""
        found: list[str] = []
        spans: list[tuple[int, int, str]] = []
        for alias, std in self.a2p.items():
            for m in re.finditer(re.escape(alias), text):
                spans.append((m.start(), m.end(), std))
        spans.sort(key=lambda x: -(x[1] - x[0]))  # 长词优先
        taken: list[tuple[int, int]] = []
        for s, e, std in spans:
            if any(not (e <= ts or s >= te) for ts, te in taken):
                continue
            taken.append((s, e))
            if std not in found:
                found.append(std)
        return found

    def lifespan(self, std_name: str) -> str:
        d = self.dates.get(std_name)
        return f"约{d[0]}—{d[1]}年" if d else "生卒年不详"


if __name__ == "__main__":
    el = EntityLinker()
    for q in ["杜甫和李白是什么关系", "乐天写过哪些关于月的诗", "刘二十八和韩愈谁年纪大",
              "李十二白二十韵是谁写的", "帮我赏析静夜思"]:
        print(q, "->", el.link(q))
