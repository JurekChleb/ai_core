"""ai_core — wspólna biblioteka AI.

Publiczne API:
    get_llm(model, project, **meta)  -> klient LLM z auto-tracingiem i kosztami
    traced(name)                     -> dekorator do owijania własnej logiki
    record_score(...)                -> zapis wyniku ewaluacji do dashboardu
    Evaluator, EvalResult            -> interfejs evaluatorów
    NonEmpty, JsonFormat, Groundedness -> gotowe evaluatory
"""
from __future__ import annotations

from .client import LLM, get_llm
from .evals import EvalResult, Evaluator, Groundedness, JsonFormat, NonEmpty
from .metadata import RequestMeta
from .observability import record_score, traced

__version__ = "0.1.0"

__all__ = [
    "LLM",
    "get_llm",
    "traced",
    "record_score",
    "RequestMeta",
    "Evaluator",
    "EvalResult",
    "NonEmpty",
    "JsonFormat",
    "Groundedness",
    "__version__",
]
