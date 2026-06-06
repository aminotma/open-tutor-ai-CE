"""Tool: evaluate a mathematical expression or equation symbolically via sympy.

Subjects: mathematics, physics (numerical formulas)
Exercise types: computation, equation, simplification, result verification
"""
from __future__ import annotations

from langchain_core.tools import tool


@tool
def math_evaluator(expression: str, expected: str = "") -> dict:
    """
    Evaluate a mathematical expression or verify an equation using sympy.

    Accepts standard math notation: '2**3', 'sqrt(16)', 'solve(x**2 - 4, x)',
    'diff(x**2, x)', 'integrate(x, x)', 'simplify((x**2-1)/(x-1))'.

    Args:
        expression: Math expression or equation string (sympy-compatible syntax).
        expected:   Optional expected result string. When provided, the tool checks
                    if the evaluated result matches it symbolically.

    Returns:
        dict with keys:
            success  (bool)  — True if evaluation succeeded (and matched expected, if given)
            result   (str)   — String representation of the computed result
            matched  (bool)  — True if result == expected symbolically (None when no expected)
            error    (str)   — Error message if evaluation failed
    """
    try:
        import sympy  # noqa: PLC0415
        from sympy.parsing.sympy_parser import (  # noqa: PLC0415
            parse_expr,
            standard_transformations,
            implicit_multiplication_application,
        )
    except ImportError:
        return _fallback_eval(expression, expected)

    transformations = standard_transformations + (implicit_multiplication_application,)

    try:
        parsed = parse_expr(expression, transformations=transformations)
        result_str = str(sympy.simplify(parsed))

        matched: bool | None = None
        if expected:
            try:
                expected_parsed = parse_expr(expected, transformations=transformations)
                matched = sympy.simplify(parsed - expected_parsed) == 0
            except Exception:
                matched = result_str.strip() == expected.strip()

        return {
            "success": True,
            "result": result_str,
            "matched": matched,
            "error": "",
        }

    except Exception as exc:
        return {
            "success": False,
            "result": "",
            "matched": None,
            "error": str(exc),
        }


# ── Fallback when sympy is not installed ─────────────────────────────────────

_SAFE_NAMES = {
    "abs": abs, "round": round, "min": min, "max": max,
    "sum": sum, "pow": pow, "len": len,
}

try:
    import math as _math
    _SAFE_NAMES.update({k: getattr(_math, k) for k in dir(_math) if not k.startswith("_")})
except ImportError:
    pass


def _fallback_eval(expression: str, expected: str) -> dict:
    """Numeric-only eval() fallback used when sympy is absent."""
    try:
        result = eval(expression, {"__builtins__": {}}, _SAFE_NAMES)  # noqa: S307
        result_str = str(result)
        matched: bool | None = None
        if expected:
            try:
                matched = abs(float(result) - float(expected)) < 1e-9
            except ValueError:
                matched = result_str.strip() == expected.strip()
        return {"success": True, "result": result_str, "matched": matched, "error": ""}
    except Exception as exc:
        return {"success": False, "result": "", "matched": None, "error": str(exc)}
