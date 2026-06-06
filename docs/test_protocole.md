# Test Protocol — OpenTutorAI

## Chosen approach: Python automation + human validation

The protocol relies on two complementary layers:

- **Python** executes the scenarios, measures the metrics, and generates a structured report.
- **The human** reads the report and confirms pedagogical quality on cases that cannot be reduced to a metric.

---

## General principle

```
Python code                    Human observation
──────────────────────────────────────────────────
Executes the scenario          Reads the generated report
Measures the metrics           Confirms quality
Generates an HTML/JSON report  Rates the responses (1–5)
Flags anomalies                Decides if it is acceptable
```

---

## Breakdown by scenario

| Scenario | Python automates | Human confirms |
|---|---|---|
| S1 — Acquisition | API call, latency measurement, Faithfulness, verifies memory is written | Response Appropriateness (1–5), qualitative Learning Gain |
| S2 — Memory | Reads memory store, verifies 3 fields + Memory Precision + Memory Freshness | Nothing — 100% automatable |
| S3 — Adaptation | Launches 2 calls (beginner vs advanced), compares lexical complexity, Difficulty Calibration | Pedagogical relevance of simplification (1–5) |
| S4 — RAG | Computes Precision@k, Recall@k, MRR, NDCG@k, Faithfulness, Context Relevance, Answer Relevance | Nothing — 100% automatable |
| S5 — Compression | Counts tokens before/after, computes Compression Ratio | Nothing — 100% automatable |
| S6 — Longitudinal | Chains the 4 sessions, verifies memory + Learning Gain (pre/post test) | Pedagogical thread coherence (1–5) |
| S7 — Routing | Parses logs, verifies sequence, Task Completion Rate, Agent Efficiency, Fallback Rate | Nothing — 100% automatable |
| S8 — Memory conflict | Verifies `level` update, Memory Conflict Rate, Memory Freshness | Nothing — 100% automatable |
| S9 — Post-compression | Measures Information Retention + Compression Ratio | Post-compression response coherence (1–5) |
| S10 — BKT | Verifies P(mastery) evolution, BKT Calibration, Threshold Detection | Nothing — 100% automatable |

**6 scenarios are 100% automatable. 4 require human confirmation.**

---

## Test file structure

```
tests/
├── automated/
│   ├── test_rag.py          # S4 — Precision, Recall, MRR
│   ├── test_memory.py       # S2, S8 — memory read/write
│   ├── test_compression.py  # S5, S9 — ratio + retention
│   ├── test_routing.py      # S7 — agent sequence via logs
│   └── test_bkt.py          # S10 — P(mastery) evolution
└── manual/
    └── evaluation_grid.md   # S1, S3, S6, S9 — human rating grid (1–5)
```

---

## Generated report format

The Python code produces a report that the human reads in one pass, without re-running the tests:

```
REPORT — OpenTutorAI Test Suite
═══════════════════════════════════════════════════════════
S2  Memory           ✅ PASS   Accuracy=100%
S4  RAG              ✅ PASS   Recall=1.0  Faithfulness=0.91
S5  Compression      ✅ PASS   Retention=82%
S7  Routing          ✅ PASS   TCR=100%  Latency=1.8s
S8  Memory conflict  ✅ PASS   Accuracy=100%
S10 BKT              ✅ PASS   Calibration=OK  P(mastery)=0.65

─── Human validation required ───────────────────────────────
S1  Acquisition      ⚠️  REVIEW  LearningGain=0.38  [rate 1–5]
S3  Adaptation       ⚠️  REVIEW  [compare the 2 responses]
S6  Longitudinal     ⚠️  REVIEW  LearningGain=0.42  [rate 1–5]
S9  Post-compression ⚠️  REVIEW  Retention=82%  [rate 1–5]
═══════════════════════════════════════════════════════════
```

The human intervenes only on the 4 `REVIEW` lines, with the responses already displayed in the report.

---

## Recommended execution frequency

| When | What |
|---|---|
| On every commit (CI) | Automated tests only |
| Before each demo | Full suite + human validation |
| Once per sprint | Manual grid review |

---

## Global success criteria

### v1 — 8 essential metrics

| Dimension | Metric | Threshold | Automatable |
|---|---|---|:---:|
| RAG retrieval | `Recall@k` | ≥ 0.80 | ✅ |
| RAG quality | `Faithfulness` | ≥ 0.85 | ✅ |
| Memory | `Memory Retrieval Accuracy` | 100% | ✅ |
| Agentic | `Task Completion Rate` | 100% | ✅ |
| Compression | `Information Retention` | ≥ 80% | ✅ |
| Pedagogy | `Learning Gain` | ≥ 0.30 | ✅ |
| BKT | `BKT Calibration` | Consistent | ✅ |
| System | `End-to-end latency` | < 3s | ✅ |

### v2 — metrics to add once v1 is stable

| Dimension | Metrics |
|---|---|
| RAG | `Precision@k`, `NDCG@k`, `Context Relevance`, `Answer Relevance` |
| Memory | `Memory Precision`, `Memory Freshness`, `Memory Conflict Rate` |
| Agentic | `Agent Efficiency`, `Fallback Rate` |
| Pedagogy | `Difficulty Calibration`, `Response Appropriateness` (human) |

### Human metrics (v1)

| Metric | Threshold |
|---|---|
| Average human rating (S1, S3, S6, S9) | ≥ 4 / 5 |
