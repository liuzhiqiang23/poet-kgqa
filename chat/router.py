# -*- coding: utf-8 -*-
"""
chat/router.py — 意图路由（规则优先，DeepSeek 分类兜底）+ 问答主流程

路由结果:
  graph   事实/关系型 → 图查询（Cypher/JsonlGraph），LLM 只组织语言
  semantic 赏析/原文型 → 向量检索（FAISS/numpy 或关键词兜底）→ 引用生成
  dialog  persona 模式（用户显式选中诗人）
"""
from __future__ import annotations

import re

GRAPH_PATTERNS = [
    r"什么关系|认识|好友|共同好友|交游|来往",
    r"隔了几|隔着几|几步|路径|怎么连|能不能连",
    r"哪年|生卒|活了几|字号|别号|朝代|哪里人",
    r"写了几首|多少首|存诗|作品数",
    r"并称|合称|号称|号称什么",
    r"写.{0,6}最多|.{0,4}最多的是谁|排行",
    r"写过.{0,12}吗|有没有写过",
    r"是谁|是谁写的|谁写",
]
SEMANTIC_PATTERNS = [
    r"赏析|鉴赏|品读",
    r"翻译|译成|白话",
    r"什么意思|什么含义|什么情感|表达了",
    r"意境|画面|畫面|情感",
    r"全文|原文|整首|背诵|默写",
    r"名句|名篇|代表作",
    r"妙在|好在哪里|写得如何|寫得如何|写得怎么样",
    r"哪些诗句|哪些詩句|哪句诗|哪幾句|哪几句",
    r"上一句|下一句|上句|下句|前一句|后一句|後一句",
    r"描写|描绘|描繪|刻画|刻畫|渲染|烘托",
    r"如何理解|怎样理解|怎麼理解|怎么看|怎麼看",
]


def route(question: str) -> str:
    for p in GRAPH_PATTERNS:
        if re.search(p, question):
            return "graph"
    for p in SEMANTIC_PATTERNS:
        if re.search(p, question):
            return "semantic"
    return "unknown"
