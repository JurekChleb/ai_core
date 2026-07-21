"""Gotowe, generyczne evaluatory wielokrotnego użytku.

Zasada: najpierw tanie i deterministyczne (NonEmpty, JsonFormat), potem
kosztowny LLM-as-judge (Groundedness) tylko tam, gdzie naprawdę trzeba.
Evaluatory specyficzne dla domeny (np. opisy książek antykwarycznych) żyją
w projekcie, a nie tu.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .base import EvalResult, Evaluator


class NonEmpty(Evaluator):
    """Wyjście nie jest puste ani samymi białymi znakami."""

    name = "non_empty"

    def evaluate(self, *, input: str = "", output: str = "", **_: Any) -> EvalResult:
        ok = bool(output and output.strip())
        return EvalResult(self.name, score=1.0 if ok else 0.0, passed=ok,
                          comment="" if ok else "Puste wyjście")


class JsonFormat(Evaluator):
    """Wyjście jest poprawnym JSON-em (opcjonalnie z wymaganymi kluczami)."""

    name = "json_format"

    def __init__(self, required_keys: list[str] | None = None) -> None:
        self.required_keys = required_keys or []

    def evaluate(self, *, input: str = "", output: str = "", **_: Any) -> EvalResult:
        try:
            data = json.loads(output)
        except (json.JSONDecodeError, TypeError) as exc:
            return EvalResult(self.name, 0.0, False, comment=f"Niepoprawny JSON: {exc}")
        missing = [k for k in self.required_keys if k not in data]
        ok = not missing
        return EvalResult(self.name, 1.0 if ok else 0.0, ok,
                          comment="" if ok else f"Brak kluczy: {missing}")


def _extract_json(text: str) -> dict:
    """Wyciągnij pierwszy obiekt JSON z odpowiedzi modelu (tolerancyjnie)."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


_GROUNDEDNESS_PROMPT = """Jesteś rygorystycznym recenzentem faktów.

KONTEKST ŹRÓDŁOWY (jedyne dozwolone fakty):
{context}

TEKST DO OCENY:
{output}

Wypisz KAŻDE stwierdzenie z tekstu, którego NIE MA w kontekście źródłowym
lub które mu PRZECZY (zmyślone fakty = halucynacje). Zwróć wyłącznie JSON:
{{"unsupported_claims": ["..."], "score": <0.0-1.0>}}
score = 1.0 gdy wszystko poparte kontekstem, 0.0 gdy pełno zmyśleń."""


class Groundedness(Evaluator):
    """LLM-as-judge: czy wyjście opiera się wyłącznie na podanym kontekście.

    Generyczny detektor halucynacji. Sędzia to osobny (tani) model — domyślnie
    alias "fast" — z temperature=0 dla powtarzalności.
    """

    name = "groundedness"

    def __init__(self, judge_model: str = "fast", project: str = "ai_core") -> None:
        self.judge_model = judge_model
        self.project = project

    def evaluate(self, *, input: str = "", output: str = "", context: str = "", **_: Any) -> EvalResult:
        from ..client import get_llm  # import leniwy — unika cyklu

        judge = get_llm(self.judge_model, project=self.project, feature="eval_groundedness")
        raw = judge.complete(
            [{"role": "user", "content": _GROUNDEDNESS_PROMPT.format(context=context, output=output)}],
            temperature=0,
        )
        try:
            data = _extract_json(raw)
        except (json.JSONDecodeError, TypeError):
            return EvalResult(self.name, 0.0, False, comment="Sędzia nie zwrócił poprawnego JSON")

        claims = data.get("unsupported_claims", [])
        score = float(data.get("score", 1.0 if not claims else 0.0))
        passed = len(claims) == 0
        return EvalResult(
            self.name, score, passed,
            comment="OK" if passed else f"Niepoparte/sprzeczne: {claims}",
            details={"unsupported_claims": claims},
        )
