"""Tool: execute a student code snippet in an isolated subprocess and return the result.

Subjects: computer science, algorithms, digital sciences
Exercise types: coding, debugging, fill_in_blank (when the answer is executable)
"""
from __future__ import annotations

import subprocess
import sys
import textwrap

from langchain_core.tools import tool


@tool
def live_code_evaluation(code: str, language: str = "python") -> dict:
    """
    Execute a code snippet in a sandboxed subprocess and return stdout, stderr, and success.

    Args:
        code: Source code to execute (already dedented is fine).
        language: Programming language. Only 'python' is supported for now.

    Returns:
        dict with keys:
            success (bool)   — True if exit code == 0
            stdout  (str)    — captured standard output (max 2 000 chars)
            stderr  (str)    — captured standard error (max 500 chars)
            language (str)   — language used
    """
    if language != "python":
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Language '{language}' is not supported yet. Only 'python' is available.",
            "language": language,
        }

    try:
        result = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(code)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[:2000],
            "stderr": result.stderr[:500],
            "language": language,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": "Execution timed out (limit: 5 s). Check for infinite loops.",
            "language": language,
        }
    except Exception as exc:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Execution error: {exc}",
            "language": language,
        }
