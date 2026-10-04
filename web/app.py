# -*- coding: utf-8 -*-
"""
web/app.py — 毕设系统 Web 服务（Flask）
三个页面：智能问答（图谱/语义双轨+证据链）、图谱探索（pyvis）、诗人对话（persona+时间锚）
启动: python web/app.py  →  http://127.0.0.1:5000
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from flask import Flask, jsonify, render_template, request  # noqa: E402

from chat.entity_link import EntityLinker  # noqa: E402
from chat.generator import organize_answer, persona_answer  # noqa: E402
from chat.persona import build_system_prompt  # noqa: E402
from chat.qa import answer_graph  # noqa: E402
from chat.router import route  # noqa: E402
from kg.graph_service import get_graph  # noqa: E402
from rag.retriever import Retriever  # noqa: E402

app = Flask(__name__)
graph = get_graph()
linker = EntityLinker()
retriever = Retriever()

try:
    from zhconv import convert as _zconv
except ImportError:  # 无 zhconv 时退化为原样显示（检索不受影响）
    _zconv = None


def to_hans(s):
    """语料底本为繁体《全唐诗》，显示层统一转简体（索引与检索不动）。"""
    if not isinstance(s, str) or not _zconv:
        return s
    return _zconv(s, "zh-hans")


def _clean_title(t):
    t = to_hans(t)
    if "（" in t and t.split("（")[0].strip():
        t = t.split("（")[0].strip()  # 去掉"（六首。以下詞已見《全唐詩》…）"式编者注
    return t if len(t) <= 24 else t[:23] + "…"


def _hans_evidence(ev):
    out = []
    for e in ev or []:
        if isinstance(e, str):
            out.append(to_hans(e))
        elif isinstance(e, dict):
            e = dict(e)
            if isinstance(e.get("title"), str):
                e["title"] = _clean_title(e["title"])
            for k in ("author", "preview", "summary", "text", "poem"):
                if isinstance(e.get(k), str):
                    e[k] = to_hans(e[k])
            out.append(e)
        else:
            out.append(e)
    return out


@app.route("/")
def index():
    return render_template("index.html", poets=sorted(linker.dates.keys()),
                           groups=graph.all_groups())


# 今日诗句（语料繁体原貌，全唐诗名家名句；按日期确定性轮换）
DAILY_LINES = [
    ("牀前看月光，疑是地上霜。", "靜夜思", "李白"),
    ("舉頭望山月，低頭思故鄉。", "靜夜思", "李白"),
    ("慈母手中線，遊子身上衣。", "遊子吟", "孟郊"),
    ("誰言寸草心，報得三春暉。", "遊子吟", "孟郊"),
    ("欲窮千里目，更上一層樓。", "登鸛雀樓", "王之渙"),
    ("白日依山盡，黃河入海流。", "登鸛雀樓", "王之渙"),
    ("會當凌絕頂，一覽眾山小。", "望嶽", "杜甫"),
    ("感時花濺淚，恨別鳥驚心。", "春望", "杜甫"),
    ("露從今夜白，月是故鄉明。", "月夜憶舍弟", "杜甫"),
    ("隨風潛入夜，潤物細無聲。", "春夜喜雨", "杜甫"),
    ("春眠不覺曉，處處聞啼鳥。", "春曉", "孟浩然"),
    ("海上生明月，天涯共此時。", "望月懷遠", "張九齡"),
    ("海內存知己，天涯若比鄰。", "送杜少府之任蜀州", "王勃"),
    ("前不見古人，後不見來者。", "登幽州臺歌", "陳子昂"),
    ("洛陽親友如相問，一片冰心在玉壺。", "芙蓉樓送辛漸", "王昌齡"),
    ("秦時明月漢時關，萬里長征人未還。", "出塞", "王昌齡"),
    ("勸君更盡一杯酒，西出陽關無故人。", "送元二使安西", "王維"),
    ("大漠孤煙直，長河落日圓。", "使至塞上", "王維"),
    ("野火燒不盡，春風吹又生。", "賦得古原草送別", "白居易"),
    ("同是天涯淪落人，相逢何必曾相識。", "琵琶行", "白居易"),
    ("沉舟側畔千帆過，病樹前頭萬木春。", "酬樂天揚州初逢席上見贈", "劉禹錫"),
    ("舊時王謝堂前燕，飛入尋常百姓家。", "烏衣巷", "劉禹錫"),
    ("身無綵鳳雙飛翼，心有靈犀一點通。", "無題", "李商隱"),
    ("春蠶到死絲方盡，蠟炬成灰淚始乾。", "無題", "李商隱"),
    ("夕陽無限好，只是近黃昏。", "樂遊原", "李商隱"),
    ("停車坐愛楓林晚，霜葉紅於二月花。", "山行", "杜牧"),
    ("二十四橋明月夜，玉人何處教吹簫。", "寄揚州韓綽判官", "杜牧"),
    ("春潮帶雨晚來急，野渡無人舟自橫。", "滁州西澗", "韋應物"),
    ("孤帆遠影碧空盡，唯見長江天際流。", "黃鶴樓送孟浩然之廣陵", "李白"),
]


@app.get("/api/daily")
def api_daily():
    """今日诗句：日期哈希做确定性种子，同一天内刷新不变。"""
    import datetime
    import hashlib
    today = datetime.date.today().isoformat()
    idx = int(hashlib.md5(today.encode()).hexdigest(), 16) % len(DAILY_LINES)
    line, poem, poet = DAILY_LINES[idx]
    return jsonify({"line": to_hans(line), "poem": to_hans(poem),
                    "poet": to_hans(poet), "date": today})


@app.post("/api/qa")
def api_qa():
    q = (request.json or {}).get("q", "").strip()
    if not q:
        return jsonify({"error": "empty question"}), 400
    mode = route(q)
    g = None  # answer_graph 自身抛异常时 except 里也要能安全取 summary
    try:
        if mode == "semantic":
            hits = retriever.search(q, 5)
            ctx = "\n\n".join(f"《{h['title']}》（{h['author']}）：{h['preview']}" for h in hits)
            answer = organize_answer(q, {"检索结果(含原文节选)": ctx}, temperature=0.4)
            return jsonify({"route": "semantic", "retriever_mode": retriever.mode,
                            "answer": to_hans(answer), "evidence": _hans_evidence([
                                {"title": h["title"], "author": h["author"],
                                 "preview": h["preview"], "score": h.get("score")}
                                for h in hits])})
        # graph / unknown 都先试图谱；图谱查不到实体时降级语义检索兜底
        g = answer_graph(q, graph, linker)
        if g["type"] == "no_entity" and mode != "semantic":
            hits = retriever.search(q, 3)
            if hits:
                return jsonify({"route": "semantic-fallback", "retriever_mode": retriever.mode,
                                "answer": f"（语义检索）最相关的作品：《{_clean_title(hits[0]['title'])}》——{to_hans(hits[0]['author'])}。"
                                          f"如需图谱查询请点名诗人，例如「杜甫和李白是什么关系」。",
                                "evidence": _hans_evidence([{"title": h["title"], "author": h["author"],
                                              "preview": h["preview"]} for h in hits])})
        answer = organize_answer(q, g["facts"], temperature=0.2)
        return jsonify({"route": "graph", "query_type": g["type"],
                        "summary": to_hans(g["summary"]), "answer": to_hans(answer),
                        "evidence": _hans_evidence(g["evidence"]), "facts": g["facts"]})
    except Exception as e:
        return jsonify({"error": f"{type(e).__name__}: {e}",
                        "summary": to_hans((g or {}).get("summary", "")) if mode != "semantic" else ""}), 500


@app.get("/api/ego")
def api_ego():
    name = request.args.get("name", "").strip()
    depth = int(request.args.get("depth", 1))
    return jsonify(graph.ego(name, depth))


@app.get("/api/path")
def api_path():
    a, b = request.args.get("a", ""), request.args.get("b", "")
    p = graph.shortest_path(a, b)
    return jsonify({"path": p})


@app.post("/api/dialog")
def api_dialog():
    d = request.json or {}
    poet, q = d.get("poet", "").strip(), d.get("q", "").strip()
    history = d.get("history", [])[-8:]
    if not poet or not q:
        return jsonify({"error": "poet and q required"}), 400
    sys_prompt = build_system_prompt(poet, graph, linker)
    try:
        ans = persona_answer(poet, sys_prompt, history, q)
    except Exception as e:
        ans = f"[生成失败 {type(e).__name__}]"
    return jsonify({"poet": poet, "answer": ans})


if __name__ == "__main__":
    print(f"graph backend: {type(graph).__name__} | retriever: {retriever.mode}")
    app.run(host="127.0.0.1", port=5000, debug=False)
