import json
from collections.abc import Iterable
from pathlib import Path

from app.schemas.analysis import CodeDiagnostic


PYTHON_LANGUAGE_NAMES = {"py", "python", "python3"}
JSON_LANGUAGE_NAMES = {"json"}


def collect_diagnostics(
    code: str,
    language: str | None = None,
    filename: str | None = None,
) -> list[CodeDiagnostic]:
    detected_language = _detect_language(language=language, filename=filename)

    if detected_language == "python":
        return _python_diagnostics(code=code, filename=filename)
    if detected_language == "json":
        return _json_diagnostics(code)

    return []


def format_diagnostics_for_prompt(diagnostics: Iterable[CodeDiagnostic]) -> str:
    diagnostics = list(diagnostics)
    if not diagnostics:
        return "No local compiler or linter diagnostics were collected for this input."

    lines = []
    for index, diagnostic in enumerate(diagnostics, start=1):
        location = ""
        if diagnostic.line is not None:
            location = f" line {diagnostic.line}"
            if diagnostic.column is not None:
                location += f", column {diagnostic.column}"
        lines.append(
            f"{index}. [{diagnostic.severity}] {diagnostic.source}{location}: {diagnostic.message}"
        )
    return "\n".join(lines)


def _detect_language(language: str | None, filename: str | None) -> str | None:
    if language:
        normalized_language = language.strip().lower()
        if normalized_language in PYTHON_LANGUAGE_NAMES:
            return "python"
        if normalized_language in JSON_LANGUAGE_NAMES:
            return "json"

    if filename:
        extension = Path(filename).suffix.lower()
        if extension == ".py":
            return "python"
        if extension == ".json":
            return "json"

    return None


def _python_diagnostics(code: str, filename: str | None) -> list[CodeDiagnostic]:
    try:
        compile(code, filename or "<source>", "exec")
    except SyntaxError as exc:
        return [
            CodeDiagnostic(
                source="python-compiler",
                severity="error",
                message=exc.msg,
                line=exc.lineno,
                column=exc.offset,
                end_line=exc.end_lineno,
                end_column=exc.end_offset,
            )
        ]

    return []


def _json_diagnostics(code: str) -> list[CodeDiagnostic]:
    try:
        json.loads(code)
    except json.JSONDecodeError as exc:
        return [
            CodeDiagnostic(
                source="json-parser",
                severity="error",
                message=exc.msg,
                line=exc.lineno,
                column=exc.colno,
            )
        ]

    return []
