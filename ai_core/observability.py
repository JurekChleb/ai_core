"""Cała różnica Langfuse ↔ Opik ↔ brak zamknięta w jednym module.

Reszta biblioteki (client, evals) i projekty NIE wiedzą, jaki backend jest
aktywny. Przełączenie = jedna zmienna env: AI_CORE_OBSERVABILITY_BACKEND.
"""
from __future__ import annotations

import functools
import os
from typing import Any, Callable

import litellm
import structlog

from .config import settings

log = structlog.get_logger("ai_core.observability")

_BACKEND = settings.observability_backend


def _set_provider_keys() -> None:
    """Udostępnij klucze providerów LiteLLM przez env (jeśli podane w configu)."""
    if settings.openai_api_key:
        os.environ.setdefault("OPENAI_API_KEY", settings.openai_api_key)
    if settings.anthropic_api_key:
        os.environ.setdefault("ANTHROPIC_API_KEY", settings.anthropic_api_key)
    os.environ.setdefault("OLLAMA_API_BASE", settings.local_api_base)


def init_observability() -> None:
    """Ustaw callback LiteLLM + env dla wybranego backendu. Wołane raz przy imporcie."""
    _set_provider_keys()

    if _BACKEND == "langfuse":
        if settings.langfuse_public_key:
            os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key)
        if settings.langfuse_secret_key:
            os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key)
        os.environ.setdefault("LANGFUSE_HOST", settings.langfuse_host)
        litellm.success_callback = ["langfuse"]
        litellm.failure_callback = ["langfuse"]
        log.info("observability.init", backend="langfuse", host=settings.langfuse_host)

    elif _BACKEND == "opik":
        if settings.opik_api_key:
            os.environ.setdefault("OPIK_API_KEY", settings.opik_api_key)
        if settings.opik_workspace:
            os.environ.setdefault("OPIK_WORKSPACE", settings.opik_workspace)
        if settings.opik_url_override:
            os.environ.setdefault("OPIK_URL_OVERRIDE", settings.opik_url_override)
        litellm.callbacks = ["opik"]
        log.info("observability.init", backend="opik")

    else:
        log.info("observability.init", backend="none")


def backend_metadata(common: dict) -> dict:
    """Zmapuj neutralne metadane (RequestMeta.to_common()) na format backendu."""
    if _BACKEND == "langfuse":
        return {
            "trace_name": common.get("feature") or "completion",
            "session_id": common.get("session_id"),
            "user_id": common.get("user_id"),
            "tags": [common["project"], common["environment"]],
            **common,
        }
    if _BACKEND == "opik":
        return {
            "opik": {
                "project_name": common["project"],
                "tags": [common["environment"], common.get("feature") or "completion"],
                "metadata": common,
            }
        }
    return {}


def traced(name: str | None = None) -> Callable:
    """Wspólny dekorator do owijania własnej logiki (RAG, łańcuchy kroków).

    Pod spodem: Langfuse @observe albo Opik @track. Przy backendzie "none"
    to zwykły passthrough (wygodne w testach i lokalnym dev).
    """

    def decorator(fn: Callable) -> Callable:
        if _BACKEND == "langfuse":
            try:
                try:
                    from langfuse.decorators import observe  # langfuse v2
                except ImportError:
                    from langfuse import observe  # langfuse v3+
                return observe(name=name or fn.__name__)(fn)
            except Exception as exc:  # brak pakietu / niezgodna wersja — nie wywalaj apki
                log.warning("traced.langfuse_unavailable", error=str(exc))

        elif _BACKEND == "opik":
            try:
                from opik import track

                return track(name=name or fn.__name__)(fn)
            except Exception as exc:
                log.warning("traced.opik_unavailable", error=str(exc))

        @functools.wraps(fn)
        def passthrough(*args: Any, **kwargs: Any) -> Any:
            return fn(*args, **kwargs)

        return passthrough

    return decorator


def record_score(
    *, name: str, value: float, trace_id: str | None = None, comment: str = ""
) -> None:
    """Zapisz wynik ewaluacji (0..1) do backendu obserwowalności (best-effort).

    Nie rzuca wyjątków — jeśli backend/wersja nie wspiera API, tylko loguje.
    Powiąż wynik z konkretnym zapytaniem przez trace_id (jeśli masz).
    """
    try:
        if _BACKEND == "langfuse":
            from langfuse import Langfuse

            Langfuse().score(name=name, value=value, comment=comment, trace_id=trace_id)
        elif _BACKEND == "opik":
            from opik import Opik

            client = Opik()
            if trace_id:
                client.log_traces_feedback_scores(
                    [{"id": trace_id, "name": name, "value": value, "reason": comment}]
                )
    except Exception as exc:
        log.warning("record_score.failed", backend=_BACKEND, name=name, error=str(exc))


init_observability()
