"""
S10 — BKT (Bayesian Knowledge Tracing)
Métrique : BKT Calibration — P(maîtrise) évolue de façon cohérente avec les résultats.
"""
import pytest

USER_ID             = "test_bkt_user"
TOPIC               = "Python"
CONCEPT             = "boucles_for"
PROMOTION_THRESHOLD = 0.65
DELTA_CORRECT       = 0.15
DELTA_INCORRECT     = -0.08


# ── Helper métrique ───────────────────────────────────────────────────────────

def _metric(name: str, value: str, threshold: str, passed: bool) -> None:
    icon = "✅" if passed else "❌"
    print(f"OTAI_METRIC | {name:<28} | {value:<14} | seuil {threshold:<10} | {icon}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mastery(db, user_id: str, concept: str, topic: str) -> float:
    from open_tutorai.models.database import KGUserMastery, KGConcept
    c = db.query(KGConcept).filter_by(name=concept, topic=topic).first()
    if not c:
        return 0.0
    row = db.query(KGUserMastery).filter_by(user_id=user_id, concept_id=c.id).first()
    return row.mastery if row else 0.0


def _attempt(db, user_id: str, correct: bool) -> float:
    from open_tutorai.services.knowledge_graph import KnowledgeGraphService
    delta = DELTA_CORRECT if correct else DELTA_INCORRECT
    row = KnowledgeGraphService.update_mastery(
        db=db, user_id=user_id, concept_name=CONCEPT, topic=TOPIC, delta=delta
    )
    db.commit()
    return row.mastery


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_correct_answer_increases_mastery(db):
    uid    = USER_ID + "_correct"
    before = _mastery(db, uid, CONCEPT, TOPIC)
    after  = _attempt(db, uid, correct=True)
    ok     = after > before

    _metric("P(maîtrise) avant", f"{before:.3f}", "-", True)
    _metric("P(maîtrise) après ✅", f"{after:.3f}", f"> {before:.3f}", ok)

    assert ok, "P(maîtrise) doit augmenter après une bonne réponse"


def test_incorrect_answer_decreases_mastery(db):
    uid = USER_ID + "_incorrect"
    _attempt(db, uid, correct=True)
    before = _mastery(db, uid, CONCEPT, TOPIC)
    after  = _attempt(db, uid, correct=False)
    ok     = after < before

    _metric("P(maîtrise) avant", f"{before:.3f}", "-", True)
    _metric("P(maîtrise) après ❌", f"{after:.3f}", f"< {before:.3f}", ok)
    _metric("P(maîtrise) ≥ 0", f"{after:.3f}", "≥ 0.0", after >= 0.0)

    assert ok,        "P(maîtrise) doit diminuer après une mauvaise réponse"
    assert after >= 0.0


def test_mastery_never_exceeds_1(db):
    uid = USER_ID + "_bounds"
    for _ in range(20):
        _attempt(db, uid, correct=True)
    mastery = _mastery(db, uid, CONCEPT, TOPIC)

    _metric("P(maîtrise) après 20 ✅", f"{mastery:.3f}", "∈ [0, 1]", 0.0 <= mastery <= 1.0)

    assert mastery <= 1.0
    assert mastery >= 0.0


def test_promotion_threshold_reached(db):
    uid      = USER_ID + "_scenario"
    SEQUENCE = [True, True, False, True]
    masteries = [_attempt(db, uid, correct=c) for c in SEQUENCE]

    grows_1  = masteries[1] > masteries[0]
    drops    = masteries[2] < masteries[1]
    grows_2  = masteries[3] > masteries[2]
    values   = [round(m, 3) for m in masteries]

    _metric("Évolution ✅✅❌✅", str(values), "↑ ↑ ↓ ↑", grows_1 and drops and grows_2)
    _metric("Croît après ✅✅", f"{values[0]}→{values[1]}", "↑", grows_1)
    _metric("Baisse après ❌",  f"{values[1]}→{values[2]}", "↓", drops)
    _metric("Remonte après ✅", f"{values[2]}→{values[3]}", "↑", grows_2)

    assert grows_1, "Après 2 bonnes réponses, maîtrise doit croître"
    assert drops,   "Après une erreur, maîtrise doit baisser"
    assert grows_2, "Après correction, maîtrise doit remonter"
    assert masteries[-1] >= DELTA_CORRECT


def test_bkt_calibration(db):
    uid    = USER_ID + "_calibration"
    needed = int(PROMOTION_THRESHOLD / DELTA_CORRECT) + 1

    for _ in range(needed):
        _attempt(db, uid, correct=True)

    mastery = _mastery(db, uid, CONCEPT, TOPIC)
    ok = mastery >= PROMOTION_THRESHOLD

    _metric("Nb réponses correctes", str(needed), "-", True)
    _metric("P(maîtrise) finale", f"{mastery:.3f}", f"≥ {PROMOTION_THRESHOLD}", ok)
    _metric("Seuil promotion atteint", str(ok), "= True", ok)

    assert ok, f"Seuil non atteint après {needed} bonnes réponses : {mastery:.3f} < {PROMOTION_THRESHOLD}"


def test_attempts_counter_increments(db):
    from open_tutorai.models.database import KGUserMastery, KGConcept
    uid = USER_ID + "_attempts"

    for i in range(3):
        _attempt(db, uid, correct=(i % 2 == 0))

    c   = db.query(KGConcept).filter_by(name=CONCEPT, topic=TOPIC).first()
    row = db.query(KGUserMastery).filter_by(user_id=uid, concept_id=c.id).first()
    ok  = row.attempts == 3

    _metric("Attempts enregistrés", str(row.attempts), "= 3", ok)

    assert ok, f"Attendu 3 attempts, obtenu {row.attempts}"
