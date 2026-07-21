"""Zgodność z API Langfuse 2.x i 3.x+ — bez sieci i bez pakietu langfuse.

Regresja: biblioteka wołała tylko Langfuse().score() i .generation(), czyli
API 2.x. Od 3.x te metody nie istnieją, a ponieważ wywołanie jest opakowane
w try/except, oceny przepadały po cichu — aplikacja działała, logi były
czyste, a dashboard pusty. Te testy pilnują, że wybór metody idzie po
możliwościach klienta, a nie po założeniu o wersji.
"""
import os

os.environ.setdefault("AI_CORE_OBSERVABILITY_BACKEND", "langfuse")

import ai_core.observability as obs


class FakeV2:
    """Klient jak w langfuse 2.x: score() + generation()."""

    def __init__(self):
        self.calls = []

    def score(self, **kwargs):
        self.calls.append(("score", kwargs))

    def generation(self, **kwargs):
        self.calls.append(("generation", kwargs))


class FakeObservation:
    def __init__(self, parent):
        self.parent = parent

    def end(self):
        self.parent.calls.append(("end", {}))


class FakeV3:
    """Klient jak w langfuse 3.x/4.x: create_score() + start_observation()."""

    def __init__(self):
        self.calls = []

    def create_score(self, **kwargs):
        self.calls.append(("create_score", kwargs))

    def start_observation(self, **kwargs):
        self.calls.append(("start_observation", kwargs))
        return FakeObservation(self)


class FakeUnsupported:
    """Klient bez żadnego znanego API — nie wolno rzucić wyjątkiem."""


def _use(monkeypatch, client):
    monkeypatch.setattr(obs, "_BACKEND", "langfuse")
    monkeypatch.setattr(obs, "_langfuse_client", lambda: client)
    return client


def test_record_score_uses_v2_api(monkeypatch):
    client = _use(monkeypatch, FakeV2())
    obs.record_score(name="groundedness", value=0.5, trace_id="t1", comment="c")
    assert [c[0] for c in client.calls] == ["score"]
    assert client.calls[0][1]["value"] == 0.5
    assert client.calls[0][1]["trace_id"] == "t1"


def test_record_score_uses_v3_api(monkeypatch):
    client = _use(monkeypatch, FakeV3())
    obs.record_score(name="groundedness", value=0.5, trace_id="t1", comment="c")
    # To jest ta regresja: na 3.x+ musi polecieć create_score, nie cisza.
    assert [c[0] for c in client.calls] == ["create_score"]
    assert client.calls[0][1]["value"] == 0.5


def test_record_generation_uses_v2_api(monkeypatch):
    client = _use(monkeypatch, FakeV2())
    obs.record_generation(name="g", model="m", input="i", output="o",
                          usage={"input": 3, "output": 4})
    assert [c[0] for c in client.calls] == ["generation"]
    assert client.calls[0][1]["usage"] == {"input": 3, "output": 4, "unit": "TOKENS"}


def test_record_generation_uses_v3_api(monkeypatch):
    client = _use(monkeypatch, FakeV3())
    obs.record_generation(name="g", model="m", input="i", output="o",
                          usage={"input": 3, "output": 4})
    # Obserwację trzeba domknąć, inaczej nigdy nie zostanie wysłana.
    assert [c[0] for c in client.calls] == ["start_observation", "end"]
    assert client.calls[0][1]["as_type"] == "generation"
    assert client.calls[0][1]["usage_details"] == {"input": 3, "output": 4}


def test_unknown_client_does_not_raise(monkeypatch):
    _use(monkeypatch, FakeUnsupported())
    obs.record_score(name="x", value=1.0)
    obs.record_generation(name="g", model="m", input="i", output="o")
