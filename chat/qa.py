# -*- coding: utf-8 -*-
"""
chat/qa.py — 图查询主流程：实体指认 → 查询类型判定 → 图谱取事实（LLM 不参与查图）
所有返回的 facts 均带证据（诗题），供答案卡展示证据链。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from chat.entity_link import EntityLinker  # noqa: E402


def answer_graph(question: str, graph, linker: EntityLinker) -> dict:
    """返回 {type, facts, evidence:[诗题...], summary:str(未接LLM时的直出文案)}"""
    poets = linker.link(question)

    # 1) 共同好友
    if len(poets) >= 2 and re.search(r"共同", question):
        common = graph.common_friends(poets[0], poets[1])
        return {"type": "common_friends",
                "facts": {"a": poets[0], "b": poets[1], "common": common},
                "evidence": [],
                "summary": (f"图谱中 {'、'.join(common)} 同时与 {poets[0]} 和 {poets[1]} 有直接交游记录。"
                            if common else f"图谱中 {poets[0]} 与 {poets[1]} 没有共同交游对象。")}

    # 2) 路径/几跳
    if len(poets) >= 2 and re.search(r"隔|路径|几步|怎么连|认识", question):
        path = graph.shortest_path(poets[0], poets[1])
        return {"type": "path", "facts": {"a": poets[0], "b": poets[1], "path": path},
                "evidence": [],
                "summary": (" → ".join(path) if path
                            else f"图谱中 {poets[0]} 与 {poets[1]} 目前不连通（可补充语料后重跑）。")}

    # 3) 两诗人关系
    if len(poets) == 2:
        rel = graph.relation(poets[0], poets[1])
        if rel["connected"]:
            ev = [p for e in rel["edges"] for p in e.get("poems", [])][:6]
            return {"type": "relation", "facts": rel, "evidence": ev,
                    "summary": "图谱中 " + "；".join(
                        f"{e['direction']}（{e['rel']}，{e['n_evidence']}篇）" for e in rel["edges"])}
        return {"type": "relation", "facts": rel, "evidence": [],
                "summary": f"图谱中 {poets[0]} 与 {poets[1]} 无直接交游记录。"}

    # 4) 意象/关键词统计（谁写 X 最多）
    m = re.search(r"(?:写|咏|吟)(?:过|的)?([^，。?？\s]{1,4}?)(?:最多|最多的是谁|排行)", question)
    if m:
        kw = m.group(1)
        top = graph.top_imagery(kw, 10)
        return {"type": "imagery", "facts": {"keyword": kw, "top": top}, "evidence": [],
                "summary": (f"全唐诗中写「{kw}」最多的诗人：" +
                            "，".join(f"{t['poet']}({t['n']}首)" for t in top[:5]) + "。")}

    # 5) 单诗人档案
    if len(poets) == 1:
        card = graph.poet_card(poets[0])
        if card:
            # 兼容双后端：Neo4j 的 associates 无 sample 字段（诗名在 poems 列表）
            nb = []
            for n in (card.get("associates") or [])[:5]:
                s = n.get("sample") or (n.get("poems") or [""])[0]
                nb.append(f"{n['poet']}（{n['rel']}" + (f"，如《{s}》" if s else "") + "）")
            return {"type": "poet_card", "facts": card, "evidence": [],
                    "summary": (f"{poets[0]}：{(card.get('desc') or '')[:80]} 存诗约{card.get('n_poems', 0)}首；"
                                f"并称：{'、'.join(card.get('groups') or []) or '无'}；"
                                f"主要交游：{'；'.join(nb) or '图谱暂无'}。生卒：{linker.lifespan(poets[0])}。")}

    # 6) 主观评价类（最有名/最伟大…）：图谱无可核验属性，不作猜测，给出替代事实
    if not poets and re.search(r"最有名|最著名|最伟大|名气最大|影响力最大|最杰出", question):
        top = graph.top_poets(5)
        return {"type": "guidance",
                "facts": {"说明": "「最有名」属于主观评价，图谱中没有可核验的对应属性，系统不作猜测。",
                          "按存诗量排名（可核验事实）": [{"诗人": t["poet"], "存诗量": t["n"]} for t in top],
                          "并称群体（可核验）": graph.all_groups()[:8],
                          "建议问法": ["李白和杜甫是什么关系", "唐代写月最多的是谁", "刘禹锡的生平档案"]},
                "evidence": [],
                "summary": ("「最有名」属主观评价，图谱不作猜测；按可核验的存诗量，前五为：" +
                            "、".join(f"{t['poet']}（{t['n']}首）" for t in top) +
                            "；并称群体：" + "、".join(graph.all_groups()[:6]) + "。")}

    return {"type": "no_entity", "facts": {}, "evidence": [],
            "summary": "未能从问题中指认诗人或查询意图，请换一种问法（如：杜甫和李白是什么关系）。"}


if __name__ == "__main__":
    from kg.graph_service import get_graph
    g, el = get_graph(), EntityLinker()
    for q in ["杜甫和李白是什么关系", "唐代写月最多的是谁", "李白和韩愈怎么连上",
              "刘禹锡和柳宗元是并称吗"]:
        r = answer_graph(q, g, el)
        print(f"Q: {q}\n  [{r['type']}] {r['summary']}\n  证据: {r['evidence'][:3]}")
