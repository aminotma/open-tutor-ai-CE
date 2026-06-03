# Protocole de test — OpenTutorAI

## Approche retenue : automatisation Python + validation humaine

Le protocole repose sur deux couches complémentaires :

- **Python** exécute les scénarios, mesure les métriques et génère un rapport structuré.
- **L'humain** lit le rapport et confirme la qualité pédagogique sur les cas non réductibles à une métrique.

---

## Principe général

```
Code Python                    Observation humaine
──────────────────────────────────────────────────
Exécute le scénario            Lit le rapport généré
Mesure les métriques           Confirme la qualité
Génère un rapport HTML/JSON    Note les réponses (1–5)
Signale les anomalies          Décide si c'est acceptable
```

---

## Répartition par scénario

| Scénario | Python automatise | Humain confirme |
|---|---|---|
| S1 — Acquisition | Appel API, mesure latence, Faithfulness, vérifie que la mémoire est écrite | Response Appropriateness (1–5), Learning Gain qualitatif |
| S2 — Mémoire | Lit la base mémoire, vérifie les 3 champs + Memory Precision + Memory Freshness | Rien — 100% automatisable |
| S3 — Adaptation | Lance 2 appels (débutant vs avancé), compare complexité lexicale, Difficulty Calibration | Pertinence pédagogique de la simplification (1–5) |
| S4 — RAG | Calcule Precision@k, Recall@k, MRR, NDCG@k, Faithfulness, Context Relevance, Answer Relevance | Rien — 100% automatisable |
| S5 — Compression | Compte les tokens avant/après, calcule Compression Ratio | Rien — 100% automatisable |
| S6 — Longitudinal | Enchaîne les 4 sessions, vérifie mémoire + Learning Gain (pré/post test) | Cohérence du fil pédagogique (1–5) |
| S7 — Routage | Parse les logs, vérifie séquence, Task Completion Rate, Agent Efficiency, Fallback Rate | Rien — 100% automatisable |
| S8 — Conflit mémoire | Vérifie mise à jour `niveau`, Memory Conflict Rate, Memory Freshness | Rien — 100% automatisable |
| S9 — Post-compression | Mesure Information Retention + Compression Ratio | Cohérence réponse post-compression (1–5) |
| S10 — BKT | Vérifie évolution P(maîtrise), BKT Calibration, Threshold Detection | Rien — 100% automatisable |

**6 scénarios sont 100% automatisables. 4 nécessitent une confirmation humaine.**

---

## Structure des fichiers de tests

```
tests/
├── automated/
│   ├── test_rag.py          # S4 — Precision, Recall, MRR
│   ├── test_memory.py       # S2, S8 — lecture/écriture mémoire
│   ├── test_compression.py  # S5, S9 — ratio + rétention
│   ├── test_routing.py      # S7 — séquence d'agents via logs
│   └── test_bkt.py          # S10 — évolution P(maîtrise)
└── manual/
    └── evaluation_grid.md   # S1, S3, S6, S9 — grille de notation humaine (1–5)
```

---

## Format du rapport généré

Le code Python produit un rapport que l'humain lit en une fois, sans relancer les tests :

```
RAPPORT — OpenTutorAI Test Suite
═══════════════════════════════════════════════════════════
S2  Mémoire          ✅ PASS   Accuracy=100%
S4  RAG              ✅ PASS   Recall=1.0  Faithfulness=0.91
S5  Compression      ✅ PASS   Retention=82%
S7  Routage          ✅ PASS   TCR=100%  Latence=1.8s
S8  Conflit mémoire  ✅ PASS   Accuracy=100%
S10 BKT              ✅ PASS   Calibration=OK  P(maîtrise)=0.65

─── Validation humaine requise ──────────────────────────────
S1  Acquisition      ⚠️  REVIEW  LearningGain=0.38  [noter 1–5]
S3  Adaptation       ⚠️  REVIEW  [comparer les 2 réponses]
S6  Longitudinal     ⚠️  REVIEW  LearningGain=0.42  [noter 1–5]
S9  Post-compression ⚠️  REVIEW  Retention=82%  [noter 1–5]
═══════════════════════════════════════════════════════════
```

L'humain intervient uniquement sur les 4 lignes `REVIEW`, avec les réponses déjà affichées dans le rapport.

---

## Fréquence d'exécution recommandée

| Quand | Quoi |
|---|---|
| À chaque commit (CI) | Tests automatisés uniquement |
| Avant chaque démo | Suite complète + validation humaine |
| Une fois par sprint | Relecture de la grille manuelle |

---

## Critères de succès globaux

### v1 — 8 métriques essentielles

| Dimension | Métrique | Seuil | Automatisable |
|---|---|---|:---:|
| RAG retrieval | `Recall@k` | ≥ 0.80 | ✅ |
| RAG qualité | `Faithfulness` | ≥ 0.85 | ✅ |
| Mémoire | `Memory Retrieval Accuracy` | 100% | ✅ |
| Agentique | `Task Completion Rate` | 100% | ✅ |
| Compression | `Information Retention` | ≥ 80% | ✅ |
| Pédagogie | `Learning Gain` | ≥ 0.30 | ✅ |
| BKT | `BKT Calibration` | Cohérent | ✅ |
| Système | `Latence end-to-end` | < 3s | ✅ |

### v2 — métriques à ajouter une fois la v1 stable

| Dimension | Métriques |
|---|---|
| RAG | `Precision@k`, `NDCG@k`, `Context Relevance`, `Answer Relevance` |
| Mémoire | `Memory Precision`, `Memory Freshness`, `Memory Conflict Rate` |
| Agentique | `Agent Efficiency`, `Fallback Rate` |
| Pédagogie | `Difficulty Calibration`, `Response Appropriateness` (humain) |

### Métriques humaines (v1)

| Métrique | Seuil |
|---|---|
| Note humaine moyenne (S1, S3, S6, S9) | ≥ 4 / 5 |
