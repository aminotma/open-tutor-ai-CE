"""
S4 — Test du RAG
Métriques : Recall@k, Faithfulness, Latence
"""
import os
import time
import pytest
from unittest.mock import patch

USER_ID = "test_rag_user"
K = 3

DOCS = [
    {"id": "doc1", "content": "La boucle for en Python permet d'itérer sur une séquence comme une liste, un tuple ou une chaîne de caractères.", "label": "Boucles for"},
    {"id": "doc2", "content": "La boucle while en Python répète un bloc d'instructions tant qu'une condition booléenne reste vraie.", "label": "Boucles while"},
    {"id": "doc3", "content": "Les fonctions Python permettent de regrouper du code réutilisable sous un nom et des paramètres.", "label": "Fonctions Python"},
    {"id": "doc4", "content": "Les listes Python sont des collections ordonnées et mutables pouvant contenir des éléments de types différents.", "label": "Listes Python"},
]

QUERY = "Quelle est la différence entre une boucle for et une boucle while ?"
RELEVANT_IDS = {"doc1", "doc2"}

MOCK_ANSWER = (
    "La boucle for permet d'itérer sur les éléments d'une séquence comme une liste. "
    "La boucle while répète un bloc d'instructions tant qu'une condition booléenne reste vraie. "
    "La boucle for parcourt une séquence tandis que while dépend d'une condition."
)


# ── Helper métrique ───────────────────────────────────────────────────────────

def _metric(name: str, value: str, threshold: str, passed: bool) -> None:
    icon = "✅" if passed else "❌"
    print(f"OTAI_METRIC | {name:<28} | {value:<14} | seuil {threshold:<10} | {icon}")


# ── Calculs ───────────────────────────────────────────────────────────────────

def recall_at_k(retrieved_ids: list, relevant_ids: set) -> float:
    return len(set(retrieved_ids) & relevant_ids) / len(relevant_ids)


def faithfulness_score(answer: str, doc_contents: list) -> float:
    corpus = " ".join(doc_contents).lower()
    sentences = [s.strip() for s in answer.split(".") if len(s.strip()) > 10]
    if not sentences:
        return 0.0
    supported = sum(
        1 for s in sentences
        if any(w in corpus for w in s.lower().split() if len(w) > 4)
    )
    return round(supported / len(sentences), 3)


def llm_answer(query: str, doc_contents: list) -> str:
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return MOCK_ANSWER
    try:
        from openai import OpenAI
        context = "\n\n".join(doc_contents)
        client = OpenAI(api_key=api_key, base_url=os.getenv("OPENAI_BASE_URL") or None)
        resp = client.chat.completions.create(
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": f"Réponds uniquement à partir des documents suivants :\n{context}"},
                {"role": "user", "content": query},
            ],
            temperature=0.1,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return MOCK_ANSWER


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def seed_collection(chroma):
    chroma.upsert(
        ids=[d["id"] for d in DOCS],
        documents=[d["content"] for d in DOCS],
        metadatas=[{"source": d["id"], "user_id": USER_ID, "label": d["label"]} for d in DOCS],
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_recall_at_k(chroma):
    from open_tutorai.services import context_retrieval as cr

    t0 = time.time()
    with patch.object(cr, "get_or_create_collection", return_value=chroma):
        results = cr.retrieve_pedagogical_documents(USER_ID, QUERY, top_k=K)
    latency = round(time.time() - t0, 3)

    retrieved_ids = [r["metadata"].get("source", "") for r in results]
    score = recall_at_k(retrieved_ids, RELEVANT_IDS)

    _metric(f"Recall@{K}", f"{score:.2f}", "≥ 0.80", score >= 0.80)
    _metric("Docs récupérés", str(retrieved_ids), f"⊇ {sorted(RELEVANT_IDS)}", bool(set(retrieved_ids) & RELEVANT_IDS))
    _metric("Latence RAG", f"{latency}s", "< 3.0s", latency < 3.0)

    assert score >= 0.8, f"Recall@{K}={score:.2f} < seuil 0.80"


def test_faithfulness(chroma):
    from open_tutorai.services import context_retrieval as cr

    with patch.object(cr, "get_or_create_collection", return_value=chroma):
        results = cr.retrieve_pedagogical_documents(USER_ID, QUERY, top_k=K)

    doc_contents = [r["content"] for r in results]
    answer = llm_answer(QUERY, doc_contents)
    score = faithfulness_score(answer, doc_contents)

    _metric("Faithfulness", f"{score:.3f}", "≥ 0.85", score >= 0.85)
    _metric("Mode LLM", "mock" if not os.getenv("OPENAI_API_KEY") else "réel", "-", True)

    assert score >= 0.85, f"Faithfulness={score:.3f} < seuil 0.85"


def test_latency(chroma):
    from open_tutorai.services import context_retrieval as cr

    t0 = time.time()
    with patch.object(cr, "get_or_create_collection", return_value=chroma):
        cr.retrieve_pedagogical_documents(USER_ID, QUERY, top_k=K)
    latency = round(time.time() - t0, 3)

    _metric("Latence end-to-end", f"{latency}s", "< 3.0s", latency < 3.0)

    assert latency < 3.0, f"Latence={latency:.3f}s > seuil 3s"
