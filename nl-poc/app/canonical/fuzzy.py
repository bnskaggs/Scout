"""Lightweight fuzzy string matching utilities."""
from __future__ import annotations

from collections import Counter
import re
from dataclasses import dataclass
from math import sqrt
from typing import Iterable, List, Sequence, Tuple


def _normalise(text: str) -> str:
    return text.strip().lower()


def _trigrams(text: str) -> Counter[str]:
    if not text:
        return Counter()
    padded = f"  {_normalise(text)}  "
    return Counter(padded[i : i + 3] for i in range(len(padded) - 2))


def cosine_similarity(a: str, b: str) -> float:
    """Return cosine similarity between two strings using trigram vectors."""

    vec_a = _trigrams(a)
    vec_b = _trigrams(b)
    if not vec_a or not vec_b:
        return 0.0
    dot = 0.0
    for token, weight in vec_a.items():
        dot += float(weight * vec_b.get(token, 0))
    norm_a = sqrt(sum(float(weight * weight) for weight in vec_a.values()))
    norm_b = sqrt(sum(float(weight * weight) for weight in vec_b.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


@dataclass
class FuzzyMatch:
    candidate: str
    score: float


@dataclass
class FuzzyMatcher:
    """Search helper that ranks candidates using trigram cosine similarity."""

    threshold: float = 0.75
    limit: int = 10

    def rank(self, query: str, candidates: Sequence[str]) -> List[FuzzyMatch]:
        scored: List[Tuple[float, str]] = []
        query_norm = _normalise(query)
        for candidate in candidates:
            score = cosine_similarity(query, candidate)
            candidate_norm = _normalise(candidate)
            if candidate_norm.startswith(query_norm):
                score = max(score, 0.9)
            elif query_norm and len(query_norm) >= 3 and query_norm in candidate_norm:
                fraction = min(len(query_norm) / max(len(candidate_norm), 1), 1.0)
                score = max(score, 0.75 + 0.2 * fraction)
            acronym = _acronym(candidate)
            if acronym and _normalise(acronym).startswith(query_norm):
                fraction = min(len(query_norm) / len(acronym), 1.0)
                score = max(score, 0.85 + 0.15 * fraction)
            if score < self.threshold:
                continue
            scored.append((score, candidate))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [FuzzyMatch(candidate=cand, score=score) for score, cand in scored[: self.limit]]

    def search(self, query: str, candidates: Iterable[str]) -> List[FuzzyMatch]:
        return self.rank(query, list(candidates))


def _acronym(text: str) -> str:
    parts = re.findall(r"[A-Za-z0-9]+", text)
    return "".join(part[0] for part in parts if part)
