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
    if settings.openai_base_url:
        # LiteLLM rozwiazuje endpoint z OPENAI_BASE_URL (w drugiej
        # kolejnosci OPENAI_API_BASE) — bez tego projekt za firmowa
        # brama i tak poleci na api.openai.com.
        os.environ.setdefault("OPENAI_BASE_URL", settings.openai_base_url)
    if settings.anthropic_api_key:
        os.environ.setdefault("ANTHROPIC_API_KEY", settings.anthropic_api_key)
    os.environ.setdefault("OLLAMA_API_BASE", settings.local_api_base)


def _langfuse_major() -> int | None:
    """Główny numer wersji zainstalowanego Langfuse, albo None."""
    try:
        import langfuse

        return int(str(getattr(langfuse, "__version__", "")).split(".")[0])
    except (ImportError, ValueError, IndexError):
        return None


def _litellm_langfuse_callback() -> str | None:
    """Nazwa callbacku LiteLLM pasujaca do zainstalowanego Langfuse.

    LiteLLM ma dwie integracje: "langfuse" (SDK 2.x) i "langfuse_otel"
    (SDK 3.x+). Wpiecie starej pod nowym SDK wywala sie na
    langfuse.version.__version__ przy PIERWSZYM wywolaniu modelu — czyli
    psuje generowanie, nie tylko telemetrie.

    Zwraca None, gdy nie da sie dobrac bezpiecznie: wtedy lepiej stracic
    automatyczny trace wywolan LiteLLM niz wywolania jako takie.
    Ewaluacja i record_score dzialaja niezaleznie od tego.
    """
    major = _langfuse_major()
    if major is None:
        return None
    if major < 3:
        return "langfuse"

    try:
        import litellm

        known = set(getattr(litellm, "_known_custom_logger_compatible_callbacks", []) or [])
        if "langfuse_otel" in known:
            return "langfuse_otel"
    except ImportError:
        pass

    log.warning(
        "observability.litellm_langfuse_callback_off",
        langfuse_major=major,
        hint="ta wersja LiteLLM nie zna langfuse_otel; auto-trace wywolan "
        "LiteLLM wylaczony, oceny i tak beda zapisywane",
    )
    return None


def _warn_if_langfuse_incompatible() -> None:
    """Sprawdź przy starcie, czy zainstalowany Langfuse umie to, czego używamy.

    Bez tego niezgodna wersja objawia się dopiero jako brak ocen w dashboardzie
    — przy działającej aplikacji i czystych logach. Lepiej powiedzieć to raz,
    głośno, w momencie startu.
    """
    try:
        import langfuse

        from langfuse import Langfuse  # noqa: F401

        version = getattr(langfuse, "__version__", "?")
        missing = []
        if not (hasattr(Langfuse, "score") or hasattr(Langfuse, "create_score")):
            missing.append("score/create_score")
        if not (hasattr(Langfuse, "generation") or hasattr(Langfuse, "start_observation")):
            missing.append("generation/start_observation")
        if missing:
            log.error(
                "observability.langfuse_incompatible",
                version=version,
                missing=missing,
                hint="oceny i generacje NIE beda zapisywane; sprawdz wersje langfuse",
            )
        else:
            log.debug("observability.langfuse_compatible", version=version)
    except ImportError:
        log.error(
            "observability.langfuse_missing",
            hint="backend=langfuse, ale pakiet nie jest zainstalowany "
            "(pip install 'ai-core[langfuse]')",
        )


def init_observability() -> None:
    """Ustaw callback LiteLLM + env dla wybranego backendu. Wołane raz przy imporcie."""
    _set_provider_keys()

    if _BACKEND == "langfuse":
        if settings.langfuse_public_key:
            os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key)
        if settings.langfuse_secret_key:
            os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key)
        os.environ.setdefault("LANGFUSE_HOST", settings.langfuse_host)
        callback = _litellm_langfuse_callback()
        if callback:
            litellm.success_callback = [callback]
            litellm.failure_callback = [callback]
        log.info(
            "observability.init",
            backend="langfuse",
            host=settings.langfuse_host,
            litellm_callback=callback or "wylaczony",
        )
        _warn_if_langfuse_incompatible()

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


def _langfuse_client() -> Any:
    """Klient Langfuse. Osobno, żeby obie funkcje niżej miały jedno źródło."""
    from langfuse import Langfuse

    return Langfuse()


def record_score(
    *, name: str, value: float, trace_id: str | None = None, comment: str = ""
) -> None:
    """Zapisz wynik ewaluacji (0..1) do backendu obserwowalności (best-effort).

    Nie rzuca wyjątków — jeśli backend/wersja nie wspiera API, tylko loguje.
    Powiąż wynik z konkretnym zapytaniem przez trace_id (jeśli masz).

    API Langfuse zmieniło nazwę tej operacji w 3.x (score -> create_score),
    dlatego wybieramy ją po realnych możliwościach klienta, a nie po numerze
    wersji — sam numer nie mówi, co pakiet faktycznie wystawia.
    """
    try:
        if _BACKEND == "langfuse":
            client = _langfuse_client()
            if hasattr(client, "score"):  # langfuse 2.x
                client.score(name=name, value=value, comment=comment, trace_id=trace_id)
            elif hasattr(client, "create_score"):  # langfuse 3.x / 4.x
                client.create_score(name=name, value=value, comment=comment, trace_id=trace_id)
            else:
                log.error(
                    "record_score.unsupported_langfuse",
                    hint="klient nie ma ani score(), ani create_score() — ocena PRZEPADA",
                )
                return
        elif _BACKEND == "opik":
            from opik import Opik

            client = Opik()
            if trace_id:
                client.log_traces_feedback_scores(
                    [{"id": trace_id, "name": name, "value": value, "reason": comment}]
                )
    except Exception as exc:
        # error, nie warning: cicho przepadająca ocena wygląda jak działająca
        # integracja i potrafi zostać niezauważona tygodniami.
        log.error("record_score.failed", backend=_BACKEND, name=name, error=str(exc))


def record_generation(
    *,
    name: str,
    model: str,
    input: Any,
    output: str,
    usage: dict | None = None,
    metadata: dict | None = None,
) -> None:
    """Zaloguj pojedynczą "generację" (koszt/tokeny) do backendu obserwowalności.

    Dla wywołań wykonywanych POZA LiteLLM — np. surowym SDK Anthropic z web
    search / prompt caching / streamingiem — gdzie automatyczny callback
    LiteLLM nie zadziała. Przekaż `usage` w formie {"input": tokeny_wejscia,
    "output": tokeny_wyjscia}; backend policzy koszt na podstawie `model`.

    Best-effort — nie rzuca wyjątków, żeby telemetria nigdy nie wywaliła apki.
    """
    try:
        if _BACKEND == "langfuse":
            lf = _langfuse_client()

            if hasattr(lf, "generation"):  # langfuse 2.x
                lf_usage = None
                if usage:
                    lf_usage = {
                        "input": usage.get("input"),
                        "output": usage.get("output"),
                        "unit": "TOKENS",
                    }
                lf.generation(
                    name=name,
                    model=model,
                    input=input,
                    output=output,
                    usage=lf_usage,
                    metadata=metadata,
                )
            elif hasattr(lf, "start_observation"):  # langfuse 3.x / 4.x
                # 3.x przeszło na model OTel: generacja to obserwacja, którą
                # trzeba domknąć, żeby została wysłana.
                generation = lf.start_observation(
                    name=name,
                    as_type="generation",
                    model=model,
                    input=input,
                    output=output,
                    usage_details={
                        "input": usage.get("input"),
                        "output": usage.get("output"),
                    }
                    if usage
                    else None,
                    metadata=metadata,
                )
                generation.end()
            else:
                log.error(
                    "record_generation.unsupported_langfuse",
                    hint="brak generation() i start_observation() — generacja PRZEPADA",
                )
                return
        elif _BACKEND == "opik":
            from opik import Opik

            client = Opik()
            trace = client.trace(name=name, input={"prompt": input}, output={"completion": output},
                                 metadata=metadata)
            trace.span(
                name=name,
                type="llm",
                model=model,
                input={"prompt": input},
                output={"completion": output},
                usage=usage,
            )
    except Exception as exc:
        log.error("record_generation.failed", backend=_BACKEND, name=name, error=str(exc))


init_observability()
