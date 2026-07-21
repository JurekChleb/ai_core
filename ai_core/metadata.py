"""Wspólny, neutralny format metadanych zapytania.

Ten zestaw pól to KONTRAKT — decyduje o tym, jak filtrujesz i grupujesz dane
w dashboardzie obserwowalności. Warstwa observability mapuje go na format
konkretnego backendu (Langfuse/Opik).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .config import settings


@dataclass
class RequestMeta:
    project: str
    feature: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    git_sha: str | None = None

    def to_common(self) -> dict:
        """Neutralny słownik metadanych (bez pustych pól), z dodanym środowiskiem."""
        d = asdict(self)
        d["environment"] = settings.environment
        return {k: v for k, v in d.items() if v is not None}
