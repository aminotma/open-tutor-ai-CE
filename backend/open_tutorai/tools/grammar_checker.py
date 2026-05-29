"""Tool: check grammar and orthography of a text via an LLM call.

Subjects : langues vivantes (français, anglais, arabe, espagnol, …)
Exercise types : dictation, writing, translation, fill_in_blank (text)
"""
from __future__ import annotations

import os

from langchain_core.tools import tool

_SYSTEM_PROMPT = (
    "You are a strict grammar and orthography corrector. "
    "Given a text and its expected language, return a JSON object with these exact keys:\n"
    "  correct (bool): true if there are no errors\n"
    "  errors (list of strings): each error described concisely (empty list if correct)\n"
    "  corrected_text (string): the fully corrected version of the input\n"
    "  explanation (string): a brief, pedagogical explanation in the same language as the input\n"
    "Return ONLY the JSON object, no markdown fences."
)


@tool
def grammar_checker(text: str, language: str = "fr") -> dict:
    """
    Check grammar and orthography of a student's text using an LLM.

    Args:
        text:     The student's written text to check.
        language: BCP-47 language code of the text ('fr', 'en', 'ar', 'es', …).

    Returns:
        dict with keys:
            success         (bool)       — True if the check completed
            correct         (bool)       — True if no errors found
            errors          (list[str])  — List of error descriptions
            corrected_text  (str)        — Corrected version of the input
            explanation     (str)        — Pedagogical explanation in target language
            error           (str)        — Error message if the tool itself failed
    """
    try:
        from openai import OpenAI  # noqa: PLC0415
    except ImportError:
        return _error_result("openai package is not installed. Run: pip install openai")

    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL") or None

    if not api_key:
        return _error_result("OPENAI_API_KEY environment variable is not set.")

    client_kwargs: dict = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url

    try:
        client = OpenAI(**client_kwargs)
        response = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0.0,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Language: {language}\n"
                        f"Text to check:\n{text}"
                    ),
                },
            ],
        )

        import json  # noqa: PLC0415
        raw = response.choices[0].message.content or "{}"
        parsed = json.loads(raw)

        return {
            "success":        True,
            "correct":        bool(parsed.get("correct", False)),
            "errors":         parsed.get("errors", []),
            "corrected_text": parsed.get("corrected_text", text),
            "explanation":    parsed.get("explanation", ""),
            "error":          "",
        }

    except Exception as exc:
        return _error_result(str(exc))


def _error_result(msg: str) -> dict:
    return {
        "success":        False,
        "correct":        False,
        "errors":         [],
        "corrected_text": "",
        "explanation":    "",
        "error":          msg,
    }
