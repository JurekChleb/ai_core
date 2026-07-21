"""Tracing dla projektów na LangChain / LangGraph.

Reszta ai_core zakłada, że model woła się przez `get_llm()` (LiteLLM), a
tracing dokleja callback LiteLLM. Projekt zbudowany na LangChainie tak nie
działa: modele są obiektami `ChatOpenAI`, które framework sam wstrzykuje do
łańcuchów i grafów, a LiteLLM nigdy ich nie widzi.

Ten moduł zamyka tę lukę. LangChain rozprowadza callbacki w dół, do każdego
węzła, więc jeden handler wpięty przy `invoke()`/`stream()` obejmuje cały
graf — wejścia, wyjścia, tokeny, koszt i drzewo wywołań — bez wiedzy
poszczególnych agentów.

    from ai_core.langchain import start_run_trace, trace_config

    run_trace = start_run_trace("run-123", session="run-123")
    graph.stream(state, config={**trace_config(run_trace, session="run-123")})

Identyfikator trace'u wyprowadzany jest deterministycznie z `run_id`, więc
ten sam run zawsze mapuje się na ten sam trace: rekord w bazie projektu da
się powiązać z trace'em bez trzymania czegokolwiek dodatkowego, a oceny
można podpiąć przez `record_score(trace_id=...)` bez obserwowania runu.

Import jest opcjonalny — moduł wymaga zainstalowanego langfuse (3.x+) i
LangChaina. Bez nich `start_run_trace()` zwraca None i projekt działa
dalej, tylko bez tracingu.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import structlog

from .config import settings

log = structlog.get_logger("ai_core.langchain")


@dataclass(frozen=True)
class RunTrace:
    """Trace jednego runu: handler LangChaina i identyfikator trace'u."""

    trace_id: str
    handler: Any


@lru_cache
def _client() -> Any | None:
    """Wspólny klient Langfuse, albo None gdy tracing wyłączony.

    Cache'owany: klient trzyma wątki w tle, więc jeden na proces. Tworzenie
    handlera per run byłoby wyciekiem — każdy niesie własnego klienta.
    """
    if settings.observability_backend != "langfuse":
        return None
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        log.info("langchain.tracing_off", reason="brak kluczy Langfuse")
        return None
    try:
        from langfuse import Langfuse

        return Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
    except Exception as exc:  # noqa: BLE001 - telemetria nigdy nie wywala apki
        log.warning("langchain.client_unavailable", error=str(exc))
        return None


def trace_id_for(run_id: str) -> str | None:
    """Identyfikator trace'u dla danego runu. Stały między procesami."""
    client = _client()
    if client is None:
        return None
    try:
        return client.create_trace_id(seed=run_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("langchain.trace_id_failed", run_id=run_id, error=str(exc))
        return None


def start_run_trace(run_id: str) -> RunTrace | None:
    """Otwórz trace dla jednego runu. None, gdy tracing wyłączony."""
    if _client() is None:
        return None
    trace_id = trace_id_for(run_id)
    if trace_id is None:
        return None
    try:
        from langfuse.langchain import CallbackHandler

        # Handler zwiazany z ID, ktore sami wybralismy: rownolegle runy nie
        # moga podebrac sobie trace'u, nawet gdy leca w osobnych watkach.
        return RunTrace(trace_id=trace_id, handler=CallbackHandler(trace_context={"trace_id": trace_id}))
    except Exception as exc:  # noqa: BLE001
        log.warning("langchain.trace_start_failed", run_id=run_id, error=str(exc))
        return None


def trace_config(
    run_trace: RunTrace | None,
    *,
    session: str | None = None,
    tags: list[str] | None = None,
    metadata: dict | None = None,
) -> dict:
    """Callbacki i metadane do wmieszania w config LangChaina.

    Pola trace'owe jadą jako klucze `langfuse_*` w metadanych — tak ustawia
    je integracja LangChaina i dlatego nie trzeba tu żadnego root spanu.
    Zwraca {}, gdy tracing wyłączony, żeby wołający mógł to wstawić
    bezwarunkowo.
    """
    if run_trace is None:
        return {}

    meta: dict[str, Any] = {"environment": settings.environment}
    if session:
        meta["langfuse_session_id"] = session
    meta["langfuse_tags"] = tags or [settings.environment]
    if metadata:
        meta.update(metadata)
    return {"callbacks": [run_trace.handler], "metadata": meta}


def flush() -> None:
    """Wypchnij zbuforowane zdarzenia. Best-effort."""
    client = _client()
    if client is None:
        return
    try:
        client.flush()
    except Exception as exc:  # noqa: BLE001
        log.warning("langchain.flush_failed", error=str(exc))
