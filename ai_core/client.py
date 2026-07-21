"""Fabryka klienta LLM — jedyny punkt, przez który projekty wołają modele.

Cienki wrapper na LiteLLM: unifikacja providerów + automatyczny tracing i
metadane. Projekt nie wie, jaki backend obserwowalności jest aktywny.
"""
from __future__ import annotations

from typing import Any

from litellm import completion

from .metadata import RequestMeta
from .models import resolve
from .observability import backend_metadata


class LLM:
    def __init__(self, model: str, meta: RequestMeta) -> None:
        self.model = resolve(model)
        self.meta = meta

    def complete(self, messages: list[dict], **kwargs: Any) -> str:
        """Zwróć treść odpowiedzi modelu (string). Tracing/koszty lecą automatycznie."""
        resp = self.raw(messages, **kwargs)
        return resp.choices[0].message.content

    def raw(self, messages: list[dict], **kwargs: Any):
        """Pełny obiekt odpowiedzi LiteLLM (gdy potrzebujesz tokenów, tool-calls itd.)."""
        return completion(
            model=self.model,
            messages=messages,
            metadata=backend_metadata(self.meta.to_common()),
            **kwargs,
        )


def get_llm(model: str, project: str, **meta_kwargs: Any) -> LLM:
    """Utwórz klienta LLM z aliasem modelu i metadanymi projektu.

    Przykład:
        llm = get_llm("smart", project="Antkwariat-BJB", feature="book_description")
        text = llm.complete([{"role": "user", "content": prompt}])
    """
    return LLM(model, RequestMeta(project=project, **meta_kwargs))
