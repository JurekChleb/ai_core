"""Testy dymne — nie wołają realnych modeli, sprawdzają montaż biblioteki.

Uruchom: AI_CORE_OBSERVABILITY_BACKEND=none pytest
"""
import os

os.environ.setdefault("AI_CORE_OBSERVABILITY_BACKEND", "none")


def test_imports_and_public_api():
    import ai_core

    for name in ("get_llm", "traced", "record_score", "Evaluator", "EvalResult",
                 "NonEmpty", "JsonFormat", "Groundedness"):
        assert hasattr(ai_core, name)


def test_model_alias_resolution():
    from ai_core.models import resolve

    assert resolve("smart") != "smart"          # alias się rozwija
    assert resolve("gpt-4o") == "gpt-4o"         # nieznana nazwa przechodzi bez zmian


def test_metadata_contract():
    from ai_core.metadata import RequestMeta

    common = RequestMeta(project="X", feature="f").to_common()
    assert common["project"] == "X"
    assert common["environment"]                 # zawsze dołożone
    assert "session_id" not in common            # puste pola odfiltrowane


def test_traced_passthrough_when_backend_none():
    from ai_core import traced

    @traced("noop")
    def add(a, b):
        return a + b

    assert add(2, 3) == 5


def test_non_empty_evaluator():
    from ai_core import NonEmpty

    assert NonEmpty().evaluate(output="opis").passed is True
    assert NonEmpty().evaluate(output="   ").passed is False


def test_json_format_evaluator():
    from ai_core import JsonFormat

    ok = JsonFormat(required_keys=["a"]).evaluate(output='{"a": 1}')
    assert ok.passed is True
    bad = JsonFormat(required_keys=["a"]).evaluate(output="nie-json")
    assert bad.passed is False
