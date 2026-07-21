# ai_core

Wspólna biblioteka AI dla projektów (Antkwariat-BJB, rarerat-e, local-agents, …).
Jedno miejsce na: unifikację providerów LLM, obserwowalność, koszty i evaluatory —
zamiast implementować to od nowa w każdym projekcie.

## Co daje

- **Unifikacja providerów** — OpenAI / Anthropic / modele lokalne (Ollama) przez
  jedno API oparte na [LiteLLM](https://docs.litellm.ai). Zmiana modelu = zmiana aliasu.
- **Obserwowalność + koszty** — automatyczny tracing każdego zapytania (koszt, tokeny,
  czas, wejście/wyjście) do **Langfuse** albo **Opik**. Przełącznik = jedna zmienna env.
- **Evaluatory** — gotowe (NonEmpty, JsonFormat, Groundedness/halucynacje) + interfejs
  do własnych, domenowych ocen.

## Instalacja

W projekcie docelowym (pinuj wersję przez tag):

```
pip install "ai-core[langfuse] @ git+https://github.com/JurekChleb/ai_core.git@v0.1.0"
# lub backend Opik:
pip install "ai-core[opik] @ git+https://github.com/JurekChleb/ai_core.git@v0.1.0"
```

## Konfiguracja

Skopiuj `.env.example` do `.env` i uzupełnij. Najważniejsze:

```bash
AI_CORE_OBSERVABILITY_BACKEND=langfuse   # langfuse | opik | none
AI_CORE_ANTHROPIC_API_KEY=...
AI_CORE_LANGFUSE_PUBLIC_KEY=...
AI_CORE_LANGFUSE_SECRET_KEY=...
```

## Użycie

```python
from ai_core import get_llm, traced

@traced("book_description")
def generate(book: dict) -> str:
    llm = get_llm("smart", project="Antkwariat-BJB", feature="book_description",
                  session_id=book["id"])
    return llm.complete([{"role": "user", "content": build_prompt(book)}])
```

Koszt, tokeny i pełne wejście/wyjście pojawią się w dashboardzie automatycznie.

### Ewaluacja (przykład: halucynacje)

```python
from ai_core import Groundedness, record_score

desc = generate(book)
res = Groundedness(project="Antkwariat-BJB").evaluate(
    output=desc, context=str(book),           # rekord książki = źródło prawdy
)
record_score(name="hallucination", value=res.score, comment=res.comment)
if not res.passed:
    print("Zmyślone fakty:", res.details["unsupported_claims"])
```

## Aliasy modeli

Zdefiniowane w `ai_core/models.py` — projekty używają aliasów, nie pełnych nazw:

| alias   | model (edytowalne)              |
|---------|---------------------------------|
| `fast`  | `anthropic/claude-haiku-4-5`    |
| `smart` | `anthropic/claude-sonnet-4-5`   |
| `gpt`   | `openai/gpt-4o`                 |
| `local` | `ollama/llama3`                 |

## Backendy obserwowalności

| Zmienna env | Efekt |
|---|---|
| `langfuse` | tracing → Langfuse (`langfuse` extra) |
| `opik`     | tracing → Opik (`opik` extra) |
| `none`     | bez tracingu — dev/testy |

Kod projektu jest **identyczny** dla każdego backendu.

## Rozwój

```bash
pip install -e ".[dev,langfuse,opik]"
AI_CORE_OBSERVABILITY_BACKEND=none pytest
ruff check .
```

## Status

`v0.1.0` — rdzeń: `get_llm`, `traced`, przełącznik Langfuse/Opik, evaluatory.
Świadomie poza v0.1 (dodawane, gdy realny projekt tego potrzebuje): cache
odpowiedzi, rate-limiting per projekt, async/streaming API.
