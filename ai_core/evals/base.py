"""Wspólny interfejs evaluatorów."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvalResult:
    name: str
    score: float  # 0.0 .. 1.0
    passed: bool
    comment: str = ""
    details: dict = field(default_factory=dict)


class Evaluator(ABC):
    name: str

    @abstractmethod
    def evaluate(self, *, input: str = "", output: str = "", **ctx: Any) -> EvalResult:
        """Oceń pojedynczą parę wejście/wyjście (plus dowolny kontekst w ctx)."""
        raise NotImplementedError
