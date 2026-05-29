"""Tool: generate a chart image (PNG base64) from data or a math function.

Subjects : mathématiques, sciences (physique, chimie), histoire (timeline)
Exercise types : chart, timeline, function_plot
"""
from __future__ import annotations

import base64
import io
import json

from langchain_core.tools import tool


@tool
def generate_chart(chart_type: str, payload: str) -> dict:
    """
    Generate a chart image encoded as base64 PNG.

    Args:
        chart_type: One of 'line', 'bar', 'scatter', 'function', 'timeline'.
        payload:    JSON string describing the chart data. See schemas below.

            line / scatter:
                {"x": [1,2,3], "y": [4,5,6], "xlabel": "x", "ylabel": "y", "title": "..."}

            bar:
                {"labels": ["A","B"], "values": [10,20], "xlabel": "...", "ylabel": "...", "title": "..."}

            function:
                {"expr": "x**2 - 2*x + 1", "x_min": -5, "x_max": 5, "title": "..."}
                (uses sympy lambdify when available, otherwise eval)

            timeline:
                {"events": [{"year": 1789, "label": "Révolution française"}, ...], "title": "..."}

    Returns:
        dict with keys:
            success  (bool)  — True if chart was generated
            image_b64 (str)  — Base64-encoded PNG (empty string on failure)
            mime_type (str)  — 'image/png'
            error    (str)   — Error message on failure
    """
    try:
        import matplotlib  # noqa: PLC0415
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # noqa: PLC0415
    except ImportError:
        return {
            "success": False,
            "image_b64": "",
            "mime_type": "image/png",
            "error": "matplotlib is not installed. Run: pip install matplotlib",
        }

    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        return {"success": False, "image_b64": "", "mime_type": "image/png", "error": f"Invalid JSON payload: {exc}"}

    try:
        fig, ax = plt.subplots(figsize=(8, 4))

        if chart_type in ("line", "scatter"):
            plot_fn = ax.plot if chart_type == "line" else ax.scatter
            plot_fn(data["x"], data["y"])
            ax.set_xlabel(data.get("xlabel", "x"))
            ax.set_ylabel(data.get("ylabel", "y"))

        elif chart_type == "bar":
            ax.bar(data["labels"], data["values"])
            ax.set_xlabel(data.get("xlabel", ""))
            ax.set_ylabel(data.get("ylabel", ""))

        elif chart_type == "function":
            x_min = float(data.get("x_min", -10))
            x_max = float(data.get("x_max", 10))
            xs = [x_min + i * (x_max - x_min) / 300 for i in range(301)]
            ys = _eval_function(data["expr"], xs)
            ax.plot(xs, ys)
            ax.set_xlabel("x")
            ax.set_ylabel("f(x)")
            ax.axhline(0, color="black", linewidth=0.8)
            ax.axvline(0, color="black", linewidth=0.8)

        elif chart_type == "timeline":
            fig.set_size_inches(12, 4)
            events = sorted(data["events"], key=lambda e: e["year"])
            years = [e["year"] for e in events]
            labels = [e["label"] for e in events]
            span = max(years) - min(years) or 1
            ax.set_xlim(min(years) - span * 0.05, max(years) + span * 0.05)
            ax.set_ylim(-1.2, 1.2)
            ax.hlines(0, min(years) - span * 0.05, max(years) + span * 0.05,
                      colors="steelblue", linewidth=2, alpha=0.5)
            ax.scatter(years, [0] * len(years), zorder=5, color="steelblue", s=100)
            for i, (yr, lbl) in enumerate(zip(years, labels)):
                above = i % 2 == 0
                y_text = 0.35 if above else -0.35
                y_line = 0.05 if above else -0.05
                va = "bottom" if above else "top"
                ax.vlines(yr, y_line, y_text * 0.85, colors="grey",
                          linewidth=1, linestyle="dashed", alpha=0.6)
                ax.text(yr, y_text, f"{yr}\n{lbl}",
                        ha="center", va=va, fontsize=8,
                        bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="steelblue", alpha=0.8))
            ax.set_yticks([])
            ax.spines[["left", "right", "top"]].set_visible(False)
            ax.set_xlabel("Année")

        else:
            plt.close(fig)
            return {"success": False, "image_b64": "", "mime_type": "image/png", "error": f"Unknown chart_type '{chart_type}'"}

        ax.set_title(data.get("title", ""))
        fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=100)
        plt.close(fig)
        buf.seek(0)
        image_b64 = base64.b64encode(buf.read()).decode("utf-8")

        return {"success": True, "image_b64": image_b64, "mime_type": "image/png", "error": ""}

    except Exception as exc:
        try:
            plt.close("all")
        except Exception:
            pass
        return {"success": False, "image_b64": "", "mime_type": "image/png", "error": str(exc)}


# ── Helper: evaluate a math expression string over a list of x values ────────

def _eval_function(expr: str, xs: list[float]) -> list[float]:
    try:
        import sympy  # noqa: PLC0415
        x_sym = sympy.Symbol("x")
        fn = sympy.lambdify(x_sym, sympy.sympify(expr), modules="math")
        return [fn(x) for x in xs]
    except ImportError:
        pass

    import math as _math  # noqa: PLC0415
    safe = {k: getattr(_math, k) for k in dir(_math) if not k.startswith("_")}
    safe["__builtins__"] = {}
    return [eval(expr, safe, {"x": x}) for x in xs]  # noqa: S307
