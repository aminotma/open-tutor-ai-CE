"""
S5 — Compression de contexte    → Compression Ratio
S9 — Résistance perte contexte  → Information Retention
"""
import pytest
from unittest.mock import MagicMock

USER_ID = "test_compression_user"
TOPIC   = "python_listes_fonctions"

KEY_CONCEPTS = ["listes", "fonctions", "Python", "débutant", "difficulté"]

LONG_EXCHANGES = [
    {"role": "user",      "content": "Je veux apprendre les listes Python."},
    {"role": "assistant", "content": "Les listes Python sont des collections ordonnées et mutables. On les crée avec des crochets : `[1, 2, 3]`."},
    {"role": "user",      "content": "Comment ajouter un élément à une liste ?"},
    {"role": "assistant", "content": "Utilisez `append()` pour ajouter à la fin ou `insert(i, val)` pour insérer à une position donnée."},
    {"role": "user",      "content": "C'est difficile pour moi. Peux-tu donner un exemple plus simple ?"},
    {"role": "assistant", "content": "Bien sûr. `ma_liste = []; ma_liste.append(1)` — la liste contient maintenant `[1]`."},
    {"role": "user",      "content": "D'accord. Maintenant parle-moi des fonctions Python."},
    {"role": "assistant", "content": "Une fonction Python se définit avec `def nom_fonction():`. Elle regroupe du code réutilisable."},
    {"role": "user",      "content": "Quelle est la différence entre paramètre et argument ?"},
    {"role": "assistant", "content": "Le paramètre est le nom dans la définition (`def f(x)`). L'argument est la valeur passée lors de l'appel (`f(5)`)."},
    {"role": "user",      "content": "Je suis débutant, les fonctions avec plusieurs paramètres me semblent complexes."},
    {"role": "assistant", "content": "Commençons avec une seule : `def saluer(nom): print('Bonjour', nom)`. Essayez d'appeler `saluer('Alice')`."},
    {"role": "user",      "content": "Ça marche ! Peut-on retourner une valeur ?"},
    {"role": "assistant", "content": "Oui, avec `return`. Exemple : `def addition(a, b): return a + b`. L'appel `addition(2, 3)` renvoie `5`."},
    {"role": "user",      "content": "Super. Récapitule ce qu'on a vu aujourd'hui."},
]

SUMMARY_TEXT = (
    "L'utilisateur, débutant en Python, a étudié les listes (création, append, insert) "
    "et les fonctions (définition, paramètres, return). "
    "Il a exprimé une difficulté avec les fonctions multi-paramètres. "
    "Progression positive après simplification des exemples."
)


# ── Helper métrique ───────────────────────────────────────────────────────────

def _metric(name: str, value: str, threshold: str, passed: bool) -> None:
    icon = "✅" if passed else "❌"
    print(f"OTAI_METRIC | {name:<28} | {value:<14} | seuil {threshold:<10} | {icon}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def count_tokens(text: str) -> int:
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return len(text.split())


def mock_llm(summary_text: str):
    llm = MagicMock()
    response = MagicMock()
    response.content = summary_text
    llm.invoke.return_value = response
    return llm


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_compression_ratio(db):
    from open_tutorai.services.summarization import SummarizationService

    raw_text = " ".join(ex["content"] for ex in LONG_EXCHANGES)
    tokens_before = count_tokens(raw_text)

    llm = mock_llm(SUMMARY_TEXT)
    summary = SummarizationService.summarize_session(
        user_id=USER_ID, topic=TOPIC,
        exchanges=LONG_EXCHANGES, llm=llm, db=db, force=True,
    )

    tokens_after = count_tokens(summary)
    ratio = round(tokens_after / tokens_before, 3)

    _metric("Tokens bruts", str(tokens_before), "-", True)
    _metric("Tokens résumé", str(tokens_after), "-", True)
    _metric("Compression Ratio", f"{ratio:.3f}", "≤ 0.30", ratio <= 0.30)

    assert ratio <= 0.30, f"Compression Ratio={ratio:.3f} > seuil 0.30"


def test_information_retention(db):
    from open_tutorai.services.summarization import SummarizationService

    llm = mock_llm(SUMMARY_TEXT)
    summary = SummarizationService.summarize_session(
        user_id=USER_ID + "_retention", topic=TOPIC,
        exchanges=LONG_EXCHANGES, llm=llm, db=db, force=True,
    )

    summary_lower = summary.lower()
    found    = [c for c in KEY_CONCEPTS if c.lower() in summary_lower]
    missing  = [c for c in KEY_CONCEPTS if c.lower() not in summary_lower]
    score    = len(found) / len(KEY_CONCEPTS)

    _metric("Information Retention", f"{score:.0%}", "≥ 80%", score >= 0.80)
    _metric("Concepts conservés", str(found), f"tous {KEY_CONCEPTS}", score == 1.0)
    if missing:
        _metric("Concepts manquants", str(missing), "aucun", False)

    assert score >= 0.80, f"Information Retention={score:.0%} < seuil 80%"


def test_should_summarize_triggers():
    from open_tutorai.services.summarization import SummarizationService

    short      = LONG_EXCHANGES[:3]
    long_enough = LONG_EXCHANGES[:6]

    no_trigger = not SummarizationService.should_summarize(short)
    trigger    = SummarizationService.should_summarize(long_enough)

    _metric("Trigger sur 3 échanges", "False", "= False", no_trigger)
    _metric("Trigger sur 6 échanges", "True",  "= True",  trigger)

    assert no_trigger, "Ne doit pas se déclencher sur 3 échanges"
    assert trigger,    "Doit se déclencher sur 6 échanges (≥ 5)"


def test_summary_cached(db):
    from open_tutorai.services.summarization import SummarizationService

    llm         = mock_llm(SUMMARY_TEXT)
    CACHE_TOPIC = TOPIC + "_cache_test"

    SummarizationService.summarize_session(
        user_id=USER_ID, topic=CACHE_TOPIC,
        exchanges=LONG_EXCHANGES, llm=llm, db=db, force=True,
    )
    calls_after_first = llm.invoke.call_count

    SummarizationService.summarize_session(
        user_id=USER_ID, topic=CACHE_TOPIC,
        exchanges=LONG_EXCHANGES, llm=llm, db=db, force=False,
    )
    calls_after_second = llm.invoke.call_count

    cached = calls_after_second == calls_after_first
    _metric("LLM rappelé sur cache", str(not cached), "= False", cached)
    _metric("Appels LLM total", str(calls_after_second), f"= {calls_after_first}", cached)

    assert cached, "Le LLM ne doit pas être rappelé si le cache est valide"
