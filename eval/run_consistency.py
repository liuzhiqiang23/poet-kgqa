# -*- coding: utf-8 -*-
"""
eval/run_consistency.py — 主实验：图谱约束 vs 裸 LLM（角色史实一致性对比）

两臂（同一批题）：
  bare       裸 LLM：仅角色设定（"你是唐代诗人X"），无图谱事实、无时间锚
  constrained 约束臂：persona 系统提示（图谱档案 + 生卒时间锚 + 护栏）
题目类型：
  life/dynasty/n_poems → 以诗人第一人称问（测角色对话史实幻觉）
  relation/imagery     → 客观问法（bare=直接问答；constrained=图谱事实注入组织）

判分（规则式，可程序复现）：
  life     答案中任一 3~4 位数字落在 gold±3 年内 → 对
  dynasty  含「唐」→ 对
  n_poems  答案数字落在 gold±20% → 对（无数字→错）
  relation 有/无 极性判断（关键词集合）
  imagery  gold 诗人的名字出现在答案中 → 对

输出: eval/results/consistency.json + consistency.md
用法: python eval/run_consistency.py [--sample 100]
"""
import argparse
import json
import random
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from chat.entity_link import EntityLinker  # noqa: E402
from chat.generator import chat  # noqa: E402
from chat.persona import build_system_prompt  # noqa: E402
from kg.graph_service import JsonlGraph  # noqa: E402

OUT_DIR = ROOT / "eval" / "results"

BARE_SYS = "你是唐代诗人{poet}，请以第一人称用一句话回答问题，不要编造，不确定就说记不清。"

POS_KW = ["有", "曾", "赠", "唱和", "交游", "来往", "寄", "酬", "是.*关系", "认识"]
NEG_KW = ["没有", "无", "未见", "不见记载", "不曾", "未闻", "没有.*记录", "并无"]

CN_DIG = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
          "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def extract_years(ans: str) -> list[int]:
    """阿拉伯数字 + 汉字数字（'八一三年'逐位读法 / '六百一十九'进位读法）"""
    out = [int(n) for n in re.findall(r"\d{3,4}", ans)]
    for m in re.finditer(r"([零〇一二三四五六七八九]{3,4})\s*年", ans):
        if all(c in CN_DIG for c in m.group(1)):
            out.append(int("".join(str(CN_DIG[c]) for c in m.group(1))))
    for m in re.finditer(r"([一二三四五六七八九])百([零〇一二三四五六七八九]?)([一二三四五六七八九]?)([一二三四五六七八九]?十[一二三四五六七八九]?)?", ans):
        h, t, u, teen = m.groups()
        val = CN_DIG[h] * 100
        if t:
            val += CN_DIG[t] * 10
        if teen:
            val += 10 + (CN_DIG[teen[-1]] if teen[-1] in CN_DIG else 0)
        elif u:
            val += CN_DIG[u]
        out.append(val)
    return out


def judge(item, ans: str) -> bool:
    t, gold = item["type"], str(item["gold"])
    if t == "life":
        nums = extract_years(ans)
        g = int(gold)
        return any(g - 3 <= n <= g + 3 for n in nums)
    if t == "dynasty":
        return "唐" in ans
    if t == "n_poems":
        nums = [int(n) for n in re.findall(r"\d{2,5}", ans)]
        g = int(gold)
        return any(g * 0.8 <= n <= g * 1.2 for n in nums)
    if t == "relation":
        if gold == "有":
            return any(re.search(k, ans) for k in POS_KW) and not re.search(r"没有|并无|不见记载", ans)
        return any(re.search(k, ans) for k in NEG_KW)
    if t == "imagery":
        return gold in ans
    return False


def ask_arm(arm: str, item, graph, linker) -> str:
    t = item["type"]
    if t in ("life", "dynasty", "n_poems"):
        poet = item["poet"]
        q = item["q"]
        if arm == "bare":
            sys_p = BARE_SYS.format(poet=poet)
        else:
            sys_p = build_system_prompt(poet, graph, linker)
        try:
            return chat([{"role": "system", "content": sys_p}, {"role": "user", "content": q}],
                        temperature=0.5, max_tokens=200)
        except Exception as e:
            return f"[ERR {type(e).__name__}]"
    # relation / imagery：客观问法
    if arm == "bare":
        try:
            return chat([{"role": "user", "content": item["q"]}], temperature=0.3, max_tokens=200)
        except Exception as e:
            return f"[ERR {type(e).__name__}]"
    # constrained：图谱事实直出（不调 LLM 也可，为公平统一走组织层）
    facts = {"type": t, "gold_hint": item["gold"]}
    if t == "relation":
        a, b = item["poets"]
        facts = graph.relation(a, b)
    else:
        kw = item["keyword"]
        facts = {"keyword": kw, "top": graph.top_imagery(kw, 5)}
    try:
        from chat.generator import organize_answer
        return organize_answer(item["q"], facts, temperature=0.1)
    except Exception as e:
        return f"[ERR {type(e).__name__}]"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=100)
    ap.add_argument("--sleep", type=float, default=0.4)
    a = ap.parse_args()
    random.seed(7)

    items = [json.loads(l) for l in (ROOT / "eval" / "qa_set.jsonl").read_text(encoding="utf-8").splitlines()]
    by_type = defaultdict(list)
    for it in items:
        by_type[it["type"]].append(it)
    quota = {"life": 30, "relation": 30, "dynasty": 15, "n_poems": 15, "imagery": 10}
    picked = []
    for t, q in quota.items():
        pool = by_type[t][:]
        random.shuffle(pool)
        picked += pool[:min(q, len(pool))]
    if a.sample and len(picked) > a.sample:
        picked = picked[:a.sample]
    print(f"sampled {len(picked)} items")

    graph, linker = JsonlGraph(), EntityLinker()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for i, it in enumerate(picked):
        for arm in ("bare", "constrained"):
            ans = ask_arm(arm, it, graph, linker)
            ok = judge(it, ans)
            results.append({"id": it["id"], "type": it["type"], "q": it["q"],
                            "gold": it["gold"], "arm": arm, "answer": ans, "correct": ok})
            time.sleep(a.sleep)
        if (i + 1) % 10 == 0:
            print(f"  {i+1}/{len(picked)} done", flush=True)

    # ---- 统计 ----
    def rate(arm, t=None):
        rs = [r for r in results if r["arm"] == arm and (t is None or r["type"] == t)]
        return {"n": len(rs), "correct": sum(r["correct"] for r in rs),
                "acc": round(sum(r["correct"] for r in rs) / max(1, len(rs)), 3)}

    summary = {"total_items": len(picked)}
    for arm in ("bare", "constrained"):
        summary[arm] = rate(arm)
        summary[arm + "_by_type"] = {t: rate(arm, t) for t in quota}
    summary["improvement"] = round(summary["constrained"]["acc"] - summary["bare"]["acc"], 3)

    (OUT_DIR / "consistency.json").write_text(
        json.dumps({"summary": summary, "detail": results}, ensure_ascii=False, indent=1),
        encoding="utf-8")

    lines = ["# 一致性主实验：图谱约束 vs 裸 LLM", "",
             f"样本 {len(picked)} 题（规则判分，可复现）", "",
             "| 臂 | 样本 | 正确 | 准确率 |", "|---|---|---|---|"]
    for arm, label in (("bare", "裸 LLM"), ("constrained", "图谱约束")):
        s = summary[arm]
        lines.append(f"| {label} | {s['n']} | {s['correct']} | {s['acc']*100:.1f}% |")
    lines += ["", f"**提升：{summary['improvement']*100:+.1f} 个百分点**", "", "## 分类型", "",
              "| 类型 | 裸LLM | 约束臂 |", "|---|---|---|"]
    for t in quota:
        b, c = summary["bare_by_type"][t], summary["constrained_by_type"][t]
        lines.append(f"| {t} | {b['acc']*100:.0f}%({b['n']}) | {c['acc']*100:.0f}%({c['n']}) |")
    (OUT_DIR / "consistency.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
