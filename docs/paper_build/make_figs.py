# -*- coding: utf-8 -*-
"""论文插图生成（真实实验数据）→ figs/*.png"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False
OUT = Path(__file__).parent / "figs"
OUT.mkdir(exist_ok=True)
INK = "#2b2b30"
ACCENT = "#8a5a2b"
GREY = "#b9a77f"

# ---------- 图3-1 系统总体架构（分层） ----------
fig, ax = plt.subplots(figsize=(8.6, 5.2))
ax.axis("off")
layers = [
    ("应用层   智能问答（证据链） · 图谱探索（pyvis） · 诗人对话（persona）", "#efe7d8"),
    ("生成层   DeepSeek API 答案组织 ｜ persona 时间锚与护栏（事实以图谱为准，LLM 仅组织语言）", "#f7f1e3"),
    ("路由层   意图路由（规则优先）：事实/关系型 → 图查询；赏析/原文型 → 语义检索", "#efe7d8"),
    ("检索层   Neo4j 图查询（Cypher 参数化模板，JsonlGraph 兜底） ◇ FAISS/bge 向量检索（关键词兜底）", "#f7f1e3"),
    ("数据层   chinese-poetry 全唐诗 57,607 首 · 诗题模式挖掘 · BERT NER 小传抽取 · 别名消歧与人工复核", "#efe7d8"),
]
for i, (txt, color) in enumerate(layers):
    y = len(layers) - 1 - i
    ax.add_patch(plt.Rectangle((0.02, y * 0.185 + 0.03), 0.96, 0.14, facecolor=color,
                               edgecolor="#c9bda2", linewidth=1.2))
    ax.text(0.5, y * 0.185 + 0.10, txt, ha="center", va="center", fontsize=10.5, color=INK)
for i in range(len(layers) - 1):
    y = len(layers) - 1 - i
    ax.annotate("", xy=(0.5, y * 0.185 - 0.012), xytext=(0.5, y * 0.185 + 0.03),
                arrowprops=dict(arrowstyle="-|>", color=ACCENT, lw=1.6))
ax.set_xlim(0, 1); ax.set_ylim(0, 1)
plt.tight_layout()
plt.savefig(OUT / "fig3-1_arch.png", dpi=300, bbox_inches="tight")
plt.close()

# ---------- 图4-1 数据构建管线 ----------
fig, ax = plt.subplots(figsize=(9.2, 3.0))
ax.axis("off")
boxes = [
    ("chinese-poetry\n58 卷 JSON", "#efe7d8"),
    ("01 底表\npoets/poems\n繁简归一", "#f7f1e3"),
    ("02 诗题挖掘\n动词+别名\n相邻匹配", "#efe7d8"),
    ("03 消歧审计\n置信分层\n人工复核", "#f7f1e3"),
    ("05 Neo4j\nCSV 导入\n138 关系对", "#efe7d8"),
    ("06 bge 向量化\nFAISS/numpy\n57,607 首", "#f7f1e3"),
    ("04 BERT NER\n小传实体\n6,096 个", "#efe7d8"),
]
w, gap = 0.125, 0.018
for i, (txt, color) in enumerate(boxes):
    x = 0.01 + i * (w + gap)
    ax.add_patch(plt.Rectangle((x, 0.3), w, 0.44, facecolor=color, edgecolor="#c9bda2", lw=1.2))
    ax.text(x + w / 2, 0.52, txt, ha="center", va="center", fontsize=9.5, color=INK)
    if i < len(boxes) - 1:
        ax.annotate("", xy=(x + w + gap - 0.004, 0.52), xytext=(x + w + 0.004, 0.52),
                    arrowprops=dict(arrowstyle="-|>", color=ACCENT, lw=1.4))
ax.text(0.5, 0.12, "（04/06 产物分别并入图谱节点属性与语义检索索引）", ha="center", fontsize=9, color="#6b6b70")
ax.set_xlim(0, 1); ax.set_ylim(0, 1)
plt.tight_layout()
plt.savefig(OUT / "fig4-1_pipeline.png", dpi=300, bbox_inches="tight")
plt.close()

# ---------- 图4-2 交游关系度数 TOP10（真实数据） ----------
names = ["白居易", "刘禹锡", "元稹", "贾岛", "杜甫", "韩愈", "李白", "孟浩然", "孟郊", "王维"]
deg = [31, 27, 15, 15, 12, 12, 11, 7, 7, 6]
fig, ax = plt.subplots(figsize=(7.4, 4.2))
y = range(len(names))[::-1]
colors = [ACCENT if i < 2 else GREY for i in range(len(names))]
ax.barh(list(y), deg, color=colors, height=0.62)
for yi, v in zip(y, deg):
    ax.text(v + 0.3, yi, str(v), va="center", fontsize=10, color=INK)
ax.set_yticks(list(y)); ax.set_yticklabels(names, fontsize=11)
ax.set_xlabel("图谱度数（直接交游关系对数）", fontsize=11)
ax.spines[["top", "right"]].set_visible(False)
ax.set_xlim(0, 35)
plt.tight_layout()
plt.savefig(OUT / "fig4-2_degree.png", dpi=300, bbox_inches="tight")
plt.close()

# ---------- 图6-1 主实验分类型对比 ----------
cats = ["生卒年\nlife", "交游关系\nrelation", "朝代\ndynasty", "存诗量\nn_poems", "意象之最\nimagery"]
bare = [63, 77, 100, 0, 90]
cons = [100, 100, 100, 100, 100]
x = range(len(cats))
w = 0.36
fig, ax = plt.subplots(figsize=(8.2, 4.4))
b1 = ax.bar([i - w / 2 for i in x], bare, w, label="裸 LLM（无图谱约束）", color=GREY, edgecolor="#a2916c")
b2 = ax.bar([i + w / 2 for i in x], cons, w, label="图谱约束（本系统）", color=ACCENT)
for rect in list(b1) + list(b2):
    h = rect.get_height()
    ax.text(rect.get_x() + rect.get_width() / 2, h + 1.5, f"{h:.0f}%", ha="center", fontsize=9.5, color=INK)
ax.set_xticks(list(x)); ax.set_xticklabels(cats, fontsize=10.5)
ax.set_ylabel("事实一致性准确率（%）", fontsize=11)
ax.set_ylim(0, 112)
ax.legend(fontsize=10.5, frameon=False, loc="lower left")
ax.spines[["top", "right"]].set_visible(False)
plt.tight_layout()
plt.savefig(OUT / "fig6-1_consistency.png", dpi=300, bbox_inches="tight")
plt.close()

# ---------- 图6-2 检索消融 ----------
fig, ax = plt.subplots(figsize=(5.6, 3.8))
modes = ["向量检索\n(bge-small-zh)", "关键词扫描\n（无向量）"]
vals = [80.0, 13.3]
bars = ax.bar(modes, vals, width=0.5, color=[ACCENT, GREY])
for rect, v in zip(bars, vals):
    ax.text(rect.get_x() + rect.get_width() / 2, v + 1.6, f"{v:.1f}%", ha="center", fontsize=12, color=INK)
ax.set_ylabel("hit@3 命中率（%）", fontsize=11)
ax.set_ylim(0, 92)
ax.spines[["top", "right"]].set_visible(False)
plt.tight_layout()
plt.savefig(OUT / "fig6-2_ablation.png", dpi=300, bbox_inches="tight")
plt.close()

print("figs:", sorted(p.name for p in OUT.glob("*.png")))
