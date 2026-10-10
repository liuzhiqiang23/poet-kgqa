# Poet Knowledge Q&A and Dialogue System (poet-kgqa)

**[中文](./README.md) | English**

An undergraduate capstone project that combines a knowledge graph and a large language model to answer questions and support conversations about Tang dynasty poets. The data foundation is [chinese-poetry](https://github.com/chinese-poetry/chinese-poetry) (MIT): 57,607 poems in 58 volumes and 3,662 poets.

**Neo4j graph retrieval + FAISS semantic retrieval + BERT NER disambiguation + evidence-grounded generation with DeepSeek.** The components can run on an ordinary laptop CPU and degrade gracefully when an optional component is unavailable.

> **[Try the live system](https://movie.jszzbinfo.cn/poet/)** — all three pages are interactive. For screenshots and a project overview, see the [showcase page](https://liuzhiqiang23.github.io/poet-kgqa/).

| Evidence-based Q&A | Social graph exploration | Poet dialogue with a timeline guard |
|---|---|---|
| ![](docs/paper_build/figs/shot5-1_qa.png) | ![](docs/paper_build/figs/shot5-2_graph.png) | ![](docs/paper_build/figs/shot5-3_dialog.png) |

## Features

### 1. Question answering

Graph and semantic retrieval are routed by rules before generation:

- **Relationship questions:** “What was the relationship between Du Fu and Li Bai?” returns their social connection and supporting poems, which can be opened to inspect the source text.
- **Path questions:** “How are Li Bai and Han Yu connected?” returns the shortest path through the graph.
- **Statistics:** questions such as “Which Tang poet wrote the most about the moon?” use poem counts and imagery rankings.
- **Poem analysis:** BGE vector retrieval, simplified/traditional Chinese recall, reciprocal-rank fusion, and title boosting surface source poems.
- Factual answers include traceable evidence cards. The LLM organizes the response; it does not write database queries.

### 2. Graph exploration

Explore one- and two-hop social subgraphs with pyvis, or query the shortest path between two poets. The 138 confirmed ASSOC edges were mined from poem titles and manually reviewed. Disconnected pairs are reported as disconnected rather than invented.

### 3. Poet dialogue

Thirty poets have dialogue profiles built from graph data. Responses use first person, while factual claims are constrained by the profile. A birth/death timeline guard refuses anachronistic questions, such as asking Li Bai about Su Shi.

### Interface

An ink-painting-inspired design uses rice-paper colors, vermilion seals, calligraphy, and vertical evidence cards. The three pages feature public-domain details from *A Thousand Li of Rivers and Mountains*, *Dwelling in the Fuchun Mountains*, and *The Elegant Gathering*. Traditional Chinese source text is normalized to simplified Chinese for display.

## Evaluation results

| Experiment | Result |
|---|---|
| Consistency test (n=100, five question types) | Plain LLM: **66%**; graph-constrained system: **100%** (+34 percentage points) |
| Retrieval ablation (15 famous-line anchors, hit@3) | Vector retrieval with dual-form enhancement: **80.0%**; keyword scan: **13.3%** |
| Social-edge review | 443 poem-level evidence items → 143 candidate pairs → 43 isolated during disambiguation → 39 accepted and 4 rejected after manual review; **138 pairs finalized** |

Interpretation boundary: for relationship, imagery, and poem-count questions, the constrained answers are constructed from graph facts. The 100% result measures whether the language layer preserves injected facts, not an increase in general model ability. Birth/death questions are the direct measure of hallucination suppression; see the thesis chapter on evaluation limits.

## Quick start

Requirements: Python 3.10+. Semantic retrieval uses a Python environment with PyTorch. Neo4j is optional; without it, the JSONL graph backend is used.

~~~bash
pip install flask zhconv faiss-cpu sentence_transformers
pip install neo4j  # Optional Neo4j backend

# Build the corpus and graph (run in order; safe to repeat)
python scripts/00_download_corpus.py
python scripts/01_load_corpus.py
python scripts/02_mine_title_edges.py
python scripts/03_disambiguate.py
python scripts/04_ner_bios.py       # Optional
python scripts/05_build_neo4j.py    # Optional
python scripts/06_build_faiss.py

# Start the web app
python web/app.py
~~~

Set POET_KGQA_USE_NEO4J=1 to enable Neo4j and provide NEO4J_PASSWORD through the environment. Set DEEPSEEK_API_KEY for generated dialogue; graph queries can still return summaries without it. The local app is available at http://127.0.0.1:5000.

## Graceful fallback

- If Neo4j is unavailable, the app uses JsonlGraph with the same interface and output format.
- If FAISS or the vector index is unavailable, it falls back to keyword scanning.
- The corpus and alias tables support simplified/traditional name forms; the display layer converts to simplified Chinese.

## Architecture

~~~text
Offline build: Chinese Poetry JSON → normalized tables → title-based edge mining → disambiguation and review → Neo4j / JSONL graph → BGE + FAISS / NumPy
Online: question → rule-first intent routing → graph or semantic retrieval → evidence-grounded response
~~~

| Layer | Technology |
|---|---|
| Graph database | Neo4j Community 5.26, with JsonlGraph fallback |
| Semantic retrieval | bge-small-zh-v1.5 + FAISS, with NumPy fallback; simplified/traditional recall and title boosting |
| Information extraction | Poem-title rules and CLUENER BERT NER |
| Generation | DeepSeek API; factual context is injected and Cypher is parameterized |
| Front end | Flask, vanilla JavaScript, and pyvis |

## Repository layout

- **scripts/** — numbered build pipeline and image/banner tools
- **kg/** — shared query layer for Neo4jGraph and JsonlGraph
- **rag/** — vector-first retrieval with keyword fallback
- **chat/** — intent routing, entity linking, Q&A, persona, and generation
- **web/** — Flask app and single-file, three-page interface
- **eval/** — 190-question evaluation set, consistency and ablation scripts/results
- **docs/** — reports and thesis-generation pipeline
- **data/** — aliases, manually reviewed names, graph tables; raw data and models are not committed

The full build steps are documented in the script headers. Portraits are public-domain classical images where available; otherwise the project creates a quote card. Interface banners use details from public-domain paintings.

## License

Code: MIT. The chinese-poetry corpus is MIT. Paintings and portraits used here are public domain. For study and discussion.
