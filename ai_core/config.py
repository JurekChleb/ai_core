"""Konfiguracja ai_core — wszystkie sekrety i przełączniki w jednym miejscu.

Wartości czytane są ze zmiennych środowiskowych z prefiksem AI_CORE_
oraz z pliku .env (patrz .env.example).
"""
from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AI_CORE_", env_file=".env", extra="ignore"
    )

    # --- providerzy LLM ---
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    local_api_base: str = "http://localhost:11434"  # Ollama / kompatybilne
    # Wlasny endpoint zgodny z OpenAI (firmowe proxy/gateway). Bez tego
    # kazde wywolanie idzie na api.openai.com — projekt za brama dostanie
    # 401 albo, gorzej, cicho ominie wlasna bramke.
    openai_base_url: str | None = None

    # --- wybór backendu obserwowalności (jedna zmienna env) ---
    observability_backend: Literal["langfuse", "opik", "none"] = "langfuse"

    # --- Langfuse ---
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    # --- Opik ---
    opik_api_key: str | None = None
    opik_workspace: str | None = None
    opik_url_override: str | None = None  # self-hosted, np. http://localhost:5173/api

    # dev | staging | prod — trafia do metadanych każdego zapytania
    environment: str = "dev"


settings = Settings()
