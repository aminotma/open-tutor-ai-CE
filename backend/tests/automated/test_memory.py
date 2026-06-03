"""
S2 — Vérification de la mémoire         → Memory Retrieval Accuracy
S8 — Conflit mémoire                    → mise à jour du profil
"""
import pytest
from uuid import uuid4
from datetime import datetime, timezone


USER_S2 = "test_memory_s2_user"
USER_S8 = "test_memory_s8_user"

EXPECTED_FIELDS = {
    "sujet":   "Python",
    "concept": "boucles for",
    "niveau":  "débutant",
}


# ── Helper métrique ───────────────────────────────────────────────────────────

def _metric(name: str, value: str, threshold: str, passed: bool) -> None:
    icon = "✅" if passed else "❌"
    print(f"OTAI_METRIC | {name:<28} | {value:<14} | seuil {threshold:<10} | {icon}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _read_memories(db, user_id: str) -> list:
    from open_tutorai.services.context_retrieval import retrieve_internal_memory_sync
    return retrieve_internal_memory_sync(user_id=user_id, query="", db=db, limit=50)


# ── S2 : Memory Retrieval Accuracy ───────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def seed_s2_memory(db):
    from open_tutorai.models.database import Memory
    db.add(Memory(
        id=uuid4().hex, user_id=USER_S2, memory_type="episodic",
        content="L'utilisateur a étudié les boucles for en Python.",
        memory_metadata={"sujet": "Python", "concept": "boucles for", "niveau": "débutant"},
    ))
    db.commit()


def test_memory_retrieval_accuracy(db):
    memories = _read_memories(db, USER_S2)
    assert memories, "Aucune mémoire trouvée pour l'utilisateur S2"

    combined_meta = {}
    for m in memories:
        combined_meta.update(m.get("metadata", {}))

    retrieved = {k for k in EXPECTED_FIELDS if k in combined_meta}
    accuracy = len(retrieved) / len(EXPECTED_FIELDS)

    _metric("Memory Retrieval Accuracy", f"{accuracy:.0%}", "= 100%", accuracy == 1.0)
    _metric("Champs récupérés", str(sorted(retrieved)), f"{sorted(EXPECTED_FIELDS)}", accuracy == 1.0)

    assert accuracy == 1.0, f"Accuracy={accuracy:.0%} — champs manquants : {set(EXPECTED_FIELDS) - retrieved}"


def test_memory_values_correct(db):
    memories = _read_memories(db, USER_S2)
    combined_meta = {}
    for m in memories:
        combined_meta.update(m.get("metadata", {}))

    all_ok = True
    for field, expected in EXPECTED_FIELDS.items():
        actual = combined_meta.get(field)
        ok = actual == expected
        if not ok:
            all_ok = False
        _metric(f"Valeur [{field}]", f"'{actual}'", f"= '{expected}'", ok)

    assert all_ok, "Des valeurs mémoire ne correspondent pas aux attendus"


# ── S8 : Conflit mémoire ──────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def s8_conflict_setup(db):
    from open_tutorai.models.database import Memory

    t_old = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    t_new = datetime(2026, 1, 4, 10, 0, 0, tzinfo=timezone.utc)

    db.add(Memory(
        id=uuid4().hex, user_id=USER_S8, memory_type="behavioral",
        content="Profil utilisateur : débutant en Python.",
        memory_metadata={"niveau": "débutant", "session": "1"},
        created_at=t_old,
    ))
    db.add(Memory(
        id=uuid4().hex, user_id=USER_S8, memory_type="behavioral",
        content="Profil mis à jour : utilisateur avancé en Python (2 ans d'expérience).",
        memory_metadata={"niveau": "avancé", "session": "4"},
        created_at=t_new,
    ))
    db.commit()


def test_conflict_profile_updated(db, s8_conflict_setup):
    memories = _read_memories(db, USER_S8)
    assert memories, "Aucune mémoire trouvée pour l'utilisateur S8"

    latest_meta = memories[0].get("metadata", {})
    niveau = latest_meta.get("niveau")
    ok = niveau == "avancé"

    _metric("Profil le plus récent", f"niveau='{niveau}'", "= 'avancé'", ok)

    assert ok, f"Le profil n'a pas été mis à jour : niveau='{niveau}'"


def test_conflict_history_preserved(db, s8_conflict_setup):
    memories = _read_memories(db, USER_S8)
    niveaux = [m.get("metadata", {}).get("niveau") for m in memories if m.get("metadata", {}).get("niveau")]

    has_old = "débutant" in niveaux
    has_new = "avancé" in niveaux

    _metric("Historique conservé", str(niveaux), "débutant + avancé", has_old and has_new)
    _metric("Nb entrées mémoire", str(len(niveaux)), "≥ 2", len(niveaux) >= 2)

    assert has_old, "L'entrée 'débutant' devrait être conservée dans l'historique"
    assert has_new, "L'entrée 'avancé' devrait être présente"
