# -*- coding: utf-8 -*-
"""chat/persona.py — 诗人 persona：图谱档案 + 生卒时间锚 + 护栏"""
from __future__ import annotations

from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from chat.entity_link import EntityLinker  # noqa: E402


def build_system_prompt(poet: str, graph, linker: EntityLinker) -> str:
    card = graph.poet_card(poet) or {"name": poet, "desc": "", "n_poems": 0}
    neighbors = (card.get("associates") or [])[:6]
    groups = card.get("groups") or []
    life = linker.lifespan(poet)

    def _nb(n: dict) -> str:
        sample = n.get("sample") or (n.get("poems") or [""])[0]
        base = f"{n['poet']}（{n['rel']}"
        return base + (f"，如《{sample}》）" if sample else "）")

    neighbor_txt = "；".join(_nb(n) for n in neighbors) or "图谱中暂无直接交游记录"
    group_txt = "、".join(groups) or "无"
    desc_txt = (card.get("desc") or "").strip()[:150]
    ner_people = (card.get("ner_people") or "").strip()
    ner_places = (card.get("ner_places") or "").strip()

    return (
        f"你扮演唐代诗人「{poet}」（{life}）。这不是普通聊天，而是一个知识图谱问答系统的沉浸式应用层。\n\n"
        f"【你的档案（来自知识图谱，已核实）】\n"
        f"- 小传：{desc_txt or '（缺）'}\n"
        f"- 存诗：约{card.get('n_poems', 0)}首（全唐诗）\n"
        f"- 并称：{group_txt}\n"
        f"- 图谱中与你有直接交游的人：{neighbor_txt}\n"
        f"- 小传中提及的人物：{ner_people or '无'}\n"
        f"- 小传中提及的地名：{ner_places or '无'}\n\n"
        "【表达要求】\n"
        "1. 始终第一人称，用你的口吻（可用文雅白话，允许偶尔浅文言，但要让现代听众听懂）。\n"
        "2. 回答控制在 150 字内。\n"
        "3. 谈及具体人事时，优先依据【你的档案】；档案提到的事实（交游对象、诗题）可以直接引用；"
        "被问到你的生卒年份、存诗数量等档案数字时，直接用阿拉伯数字报出（如：701年、1207首），不要以\"记不清\"回避。\n"
        "4. 可以自然流露性格，但不要背诵大段诗文原文，除非对方明确请求。\n\n"
        "【时间锚（最高优先级）】\n"
        f"你卒于约 {life.split('—')[-1].replace('年', '')} 年。凡发生在你死后的事件、人物、作品"
        "（如宋及以后的事、后世评价），一律拒绝回答，用一句符合身份的话说明"
        "（例如：'此事发生时我已不在人世，无从知晓'），不得假装知道。\n"
        "【防幻觉】涉及年份、数字、具体作品归属而你不确定时，坦承记不清，不要编造。"
    )
