"""
Lanceur de la suite de tests OpenTutorAI.
Génère le rapport détaillé avec valeur mesurée vs contrainte.

Usage :
    cd backend
    /home/hadoop/miniconda3/envs/tutorai-env/bin/python tests/run_tests.py
"""
import subprocess
import sys
import time
from pathlib import Path

TESTS_DIR = Path(__file__).parent / "automated"

TEST_FILES = {
    "S2/S8 — Mémoire":    "test_memory.py",
    "S4    — RAG":         "test_rag.py",
    "S5/S9 — Compression": "test_compression.py",
    "S7    — Routage":     "test_routing.py",
    "S10   — BKT":         "test_bkt.py",
}

REVIEW_SCENARIOS = [
    ("S1",  "Acquisition",       "La réponse est-elle adaptée à un débutant ?"),
    ("S3",  "Adaptation péda.",  "La simplification est-elle pédagogiquement pertinente ?"),
    ("S6",  "Longitudinal",      "Le fil pédagogique est-il cohérent sur 4 sessions ?"),
    ("S9h", "Post-compression",  "La réponse post-compression est-elle cohérente ?"),
]


def run_file(filename: str) -> tuple[bool, list[str], list[str], float]:
    """Lance un fichier de test pytest. Retourne (passed, metric_lines, error_lines, duration)."""
    t0 = time.time()
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(TESTS_DIR / filename),
         "-v", "-s", "--tb=short", "--no-header", "-q"],
        capture_output=True, text=True,
        cwd=Path(__file__).parent.parent,
    )
    duration = round(time.time() - t0, 2)
    passed = result.returncode == 0
    output = result.stdout + result.stderr

    metric_lines = [
        line.strip() for line in output.splitlines()
        if line.strip().startswith("OTAI_METRIC")
    ]
    error_lines = [
        line for line in output.splitlines()
        if any(kw in line for kw in ("FAILED", "AssertionError", "Error", "assert"))
        and "warnings" not in line.lower()
    ]

    return passed, metric_lines, error_lines, duration


def format_metric(line: str) -> str:
    """Transforme 'OTAI_METRIC | name | value | seuil X | icon' en ligne affichable."""
    parts = [p.strip() for p in line.split("|")]
    if len(parts) < 5:
        return f"    {line}"
    _, name, value, threshold, icon = parts[0], parts[1], parts[2], parts[3], parts[4]
    return f"    {icon}  {name:<28} {value:<16} {threshold}"


def main():
    print()
    print("═" * 70)
    print("  RAPPORT — OpenTutorAI Test Suite")
    print("═" * 70)

    all_passed   = True
    all_metrics  = {}
    all_errors   = {}
    all_durations = {}

    # ── Exécution ─────────────────────────────────────────────────────────────
    for label, filename in TEST_FILES.items():
        passed, metrics, errors, duration = run_file(filename)
        all_passed = all_passed and passed
        all_metrics[label]   = metrics
        all_errors[label]    = errors
        all_durations[label] = duration

        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"\n  {status}  {label}  ({duration}s)")
        print("  " + "─" * 66)

        if metrics:
            for m in metrics:
                print(format_metric(m))
        else:
            print("    (aucune métrique capturée)")

        if not passed and errors:
            print()
            print("    ── Erreurs ──")
            seen = set()
            for e in errors:
                e = e.strip()
                if e and e not in seen:
                    seen.add(e)
                    print(f"    ⚠  {e[:90]}")

    # ── Résumé automatisé ─────────────────────────────────────────────────────
    n_pass = sum(1 for label in TEST_FILES if all_metrics.get(label) is not None and
                 all_errors.get(label) == [] or
                 label in [l for l, f in TEST_FILES.items() if all_errors.get(l) == []])
    n_total = len(TEST_FILES)
    n_pass  = sum(1 for label in TEST_FILES if not all_errors.get(label) or
                  all([m.endswith("✅") for m in (all_metrics.get(label) or [])]))

    print()
    print("═" * 70)
    print(f"  Suites automatisées : {sum(1 for l in TEST_FILES if not all_errors.get(l))}/{n_total} PASS")
    print()

    # ── Validation humaine ────────────────────────────────────────────────────
    print("  ── Validation humaine requise (noter 1–5) ─────────────────────────")
    for sid, label, question in REVIEW_SCENARIOS:
        print(f"  ⚠  {sid:<5}  {label:<22}  {question}")

    print()
    print("═" * 70)
    verdict = "✅  SUITE VERTE — tous les tests automatisés passent" if all_passed \
              else "❌  DES TESTS ÉCHOUENT — voir détails ci-dessus"
    print(f"  {verdict}")
    print("═" * 70)
    print()

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
