# -*- coding: utf-8 -*-
"""
02_mine_title_edges.py — 诗题模式挖掘交游关系边（核心工程创新点）

原理：唐代赠答诗的诗题有固定格式——
  正向（作者→对象）：《赠汪伦》《春日忆李白》《酬乐天…》《送孟浩然之广陵》
  反向（对象→作者）：《…乐天…见赠》（乐天先赠，作者酬答）
本脚本用 关系动词 + 别名/人名 相邻匹配，从 5.7 万诗题中抽出有文献证据的交游边。
每条边可回指到具体诗篇（证据链）。

输入: data/processed/poems.jsonl + data/alias/poet_aliases.json + data/processed/poets.jsonl
输出: data/processed/edges_raw.jsonl  {src,dst,rel,poem_id,title,confidence}
      data/processed/external_mentions.jsonl  （指向 30 人之外对象的边，二期扩展用）
"""
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
ALIAS_FILE = ROOT / "data" / "alias" / "poet_aliases.json"

# 关系动词 → 边类型（正向：作者 → 诗题中被称呼者）
FORWARD = [
    (r"(?:戏赠|又赠|重寄|寄赠|遥赠)", "赠答"),
    (r"(?:赠|贻|遗)", "赠答"),
    (r"(?:寄)", "赠答"),
    (r"(?:送|饯送|送别)", "赠别"),
    (r"(?:和|酬|答|次韵|依韵)", "唱和"),
    (r"(?:哭|挽|悼|祭)", "悼亡"),
    (r"(?:忆|怀|思|念)", "忆念"),
    (r"(?:呈|献|投)", "干谒"),  # 不含裸「上」（藍上/灞上等地名易误报）
]
# 反向：诗题含「X 见赠/见寄」= X 先赠给作者（如刘禹锡《酬乐天扬州初逢席上见赠》）
REVERSE = re.compile(r"(见赠|见寄|见示|见访|见过|见招)")

# 相邻容距：动词与称呼之间允许官职/行第等修饰，如「送李少府…」「呈张十八员外」
GAP = 6

# 官职词：称呼后紧跟官职（杜二拾遺/高三十五書記）= 行第+官职强指认，置信升 high
OFFICIAL = re.compile(r"^(拾遺|员外|員外|補闕|补阙|侍御|使君|長史|长史|書記|书记|郎中|舍人|學士|学士|將軍|将军|中丞|刺史|司馬|司马|主簿|校書|校书|常侍|監|监|工部|右丞|大夫|司勳|赞善|贊善)")
# 宗教称谓：「太白禅师/太白隐者」等是僧道法号而非李白，出现即排除该候选
RELIGIOUS = re.compile(r"(禪師|禅师|隱者|隐者|上人|道士|煉師|炼师|法師|法师|居士|真人)")
# 高危别名限定动词：如「太白」也是山名/星名，仅允许强人际动词成边（防《送僧归太白山》类误命中）
ALIAS_REL_WHITELIST = {"太白": {"赠答", "唱和", "悼亡", "干谒"},
                       "玉溪": {"赠答", "唱和", "悼亡"}}

# 繁体全名（与 data/alias/poet_aliases.json 各列表中的同名条目对应），命中即视为零歧义指认
TRAD_FULLNAMES = {"王維", "李商隱", "韓愈", "劉禹錫", "王昌齡", "高適", "岑參", "賀知章",
                  "張九齡", "陳子昂", "楊炯", "盧照鄰", "駱賓王", "賈島", "李賀", "溫庭筠",
                  "韋應物", "劉長卿", "杜荀鶴", "羅隱", "崔顥"}

FULLNAMES: set[str] = set()  # build_alias_maps() 时填充：30 标准名 + 繁体全名


def build_alias_maps() -> tuple[dict[str, str], dict[str, str]]:
    """alias -> 标准名（30 头部诗人）；name -> 标准名（全唐作者，用于外向提及）"""
    aliases = json.loads(ALIAS_FILE.read_text(encoding="utf-8"))
    a2p: dict[str, str] = {}
    fullnames: set[str] = set()
    for poet, alist in aliases.items():
        if poet.startswith("_") or not isinstance(alist, list):
            continue  # _notes 等元数据键
        a2p[poet] = poet
        fullnames.add(poet)
        for a in alist:
            if a in a2p and a2p[a] != poet:
                raise SystemExit(f"别名冲突: {a} -> {a2p[a]} 与 {poet}")
            a2p[a] = poet
    fullnames.update(TRAD_FULLNAMES)  # 繁体全名已在各别名列表中映射到标准名，此处仅用于置信判定
    FULLNAMES.update(fullnames)
    name2p = {}
    for line in (PROC / "poets.jsonl").read_text(encoding="utf-8").splitlines():
        name = json.loads(line)["name"]
        if len(name) >= 2 and name not in ("无名氏", "佚名"):
            name2p[name] = name
    return a2p, name2p


def find_edges_in_title(title: str, author: str, a2p: dict, name2p: dict) -> list[dict]:
    """返回该诗题抽出的边（可能 0~多条）。author 先归一到 30 人标准名（含繁体映射）。"""
    author_std = a2p.get(author, author)
    in30 = author in a2p
    out = []
    # 反向优先：「X见赠」— 在反向动词前的称呼串里找别名
    m_rev = REVERSE.search(title)
    if m_rev:
        seg = title[: m_rev.start()]
        for a in sorted(a2p, key=len, reverse=True):
            if a in seg[-12:]:  # 只看见赠词前的近邻
                if a2p[a] != author_std:
                    out.append({"src": a2p[a], "dst": author_std, "rel": "赠答",
                                "confidence": "medium" if len(a) < 3 else "high"})
                break
    # 正向：找「动词 …(≤GAP字)… 称呼」
    for alias, std in sorted(a2p.items(), key=lambda x: -len(x[0])):
        if std == author_std:
            continue  # 防自环（含别名形态不同的自指，如 元稹 题中含「元九」）
        pos = title.find(alias)
        if pos < 0:
            continue
        if RELIGIOUS.search(title[pos:pos + len(alias) + 6]):
            continue  # 「太白禅师/太白隐者」等法号指称，非诗人本人
        before = title[max(0, pos - GAP): pos]
        for pat, rel in FORWARD:
            if re.search(pat, before):
                allow = ALIAS_REL_WHITELIST.get(alias)
                if allow is not None and rel not in allow:
                    break  # 高危别名只允许白名单关系（如「太白」防太白山）
                strong = (len(alias) >= 3 or alias in FULLNAMES
                          or OFFICIAL.match(title[pos + len(alias):]) is not None)
                out.append({"src": author_std if in30 else author, "dst": std, "rel": rel,
                            "confidence": "high" if strong else "medium"})
                break
    # 外向提及：对象不在 30 人内但在全唐作者表（供二期）
    for name in name2p:
        if name in a2p or name == author:
            continue
        pos = title.find(name)
        if pos < 0:
            continue
        before = title[max(0, pos - GAP): pos]
        for pat, rel in FORWARD:
            if re.search(pat, before):
                out.append({"src": author, "dst": name, "rel": rel,
                            "confidence": "external"})
                break
    return out


def main() -> None:
    a2p, name2p = build_alias_maps()
    print(f"别名表: {len(a2p)} 个称呼 -> {len(set(a2p.values()))} 位诗人；全唐作者名 {len(name2p)}")

    n_ext = 0
    stats: Counter = Counter()
    pair_samples: list[str] = []
    with (PROC / "edges_raw.jsonl").open("w", encoding="utf-8") as fe, \
         (PROC / "external_mentions.jsonl").open("w", encoding="utf-8") as fx:
        for line in (PROC / "poems.jsonl").read_text(encoding="utf-8").splitlines():
            poem = json.loads(line)
            title, author = poem["title"], poem["author"]
            if len(title) > 30:
                continue
            for e in find_edges_in_title(title, author, a2p, name2p):
                rec = {"poem_id": poem["id"], "title": title, **e}
                if e["confidence"] == "external":
                    fx.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    n_ext += 1
                else:
                    fe.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    stats[(e["src"], e["dst"], e["rel"])] += 1
                    if len(pair_samples) < 400:
                        pair_samples.append(f"{e['src']} -{e['rel']}→ {e['dst']} 《{title}》")

    print(f"30人内边(诗篇级): {sum(stats.values())} 条；外向提及: {n_ext} 条")
    uniq = sorted(stats.items(), key=lambda x: -x[1])
    print(f"去重后 (src,dst,rel) 组合: {len(uniq)} 个")
    print("TOP15 关系对:")
    for (s, d, r), c in uniq[:15]:
        print(f"  {s} -{r}→ {d}  ×{c}")
    print("\n证据样例:")
    for s in pair_samples[:8]:
        print("  ", s)


if __name__ == "__main__":
    main()
