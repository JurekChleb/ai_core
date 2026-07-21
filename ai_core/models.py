"""Rejestr aliasów modeli.

Projekty używają aliasów ("fast"/"smart"/"local"), a mapowanie na konkretne
modele żyje TU. Zmiana providera = jedna linijka, bez ruszania projektów.

Nazwy modeli są w formacie LiteLLM. Zweryfikuj dokładne identyfikatory pod
kątem swojego konta/providera — LiteLLM akceptuje formę z prefiksem providera
(np. "anthropic/...", "openai/...", "ollama/...").
"""
from __future__ import annotations

MODEL_ALIASES: dict[str, str] = {
    "fast": "anthropic/claude-haiku-4-5",
    "smart": "anthropic/claude-sonnet-4-5",
    "gpt": "openai/gpt-4o",
    "local": "ollama/llama3",
}


def resolve(alias_or_name: str) -> str:
    """Zamień alias na pełną nazwę modelu; nieznane nazwy przepuść bez zmian."""
    return MODEL_ALIASES.get(alias_or_name, alias_or_name)
