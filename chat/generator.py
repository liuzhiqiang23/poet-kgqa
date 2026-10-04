# -*- coding: utf-8 -*-
"""chat/generator.py — DeepSeek 生成层（OpenAI 兼容 chat completions）"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import urllib.request

API_URL = "https://api.deepseek.com/chat/completions"
KEY_CMD_FALLBACK = Path.home() / ".claude" / "deepseek-api-key.cmd"


def _load_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if key.startswith("sk-"):
        return key
    # 兜底：从本机密钥文件解析（不外泄打印）
    try:
        m = re.search(r"sk-[A-Za-z0-9]+", KEY_CMD_FALLBACK.read_text(encoding="utf-8", errors="ignore"))
        if m:
            return m.group()
    except Exception:
        pass
    return ""


def chat(messages: list[dict], temperature: float = 0.3, max_tokens: int = 600) -> str:
    key = _load_key()
    if not key:
        return "[未配置 DEEPSEEK_API_KEY：请设置环境变量，或确认 ~/.claude/deepseek-api-key.cmd 存在]"
    body = json.dumps({"model": "deepseek-chat", "messages": messages,
                       "temperature": temperature, "max_tokens": max_tokens}).encode()
    req = urllib.request.Request(API_URL, data=body, method="POST", headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=90) as r:
        data = json.loads(r.read())
    return data["choices"][0]["message"]["content"].strip()


def organize_answer(question: str, facts: dict, temperature: float = 0.2) -> str:
    """事实型问答：图谱结果作为已核实事实注入，LLM 只组织语言。"""
    sys = ("你是知识图谱问答系统的答案组织器。下面给你【已核实事实】（来自 Neo4j 图谱查询），"
           "你的任务只是把这些事实组织成通顺、准确的中文回答，禁止编造或修改任何事实数字、"
           "人名、诗名；事实之外的内容不要补充。回答简洁，末尾单独一行列出证据诗篇（若有）。")
    user = f"问题：{question}\n\n【已核实事实】\n{json.dumps(facts, ensure_ascii=False, indent=1)}"
    return chat([{"role": "system", "content": sys}, {"role": "user", "content": user}],
                temperature=temperature)


def persona_answer(poet: str, system_prompt: str, history: list[dict], question: str) -> str:
    msgs = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": question}]
    return chat(msgs, temperature=0.7, max_tokens=500)
