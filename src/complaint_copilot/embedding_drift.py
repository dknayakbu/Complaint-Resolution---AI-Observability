"""Local sentence-embedding centroid drift for complaint windows."""

from __future__ import annotations

import math
import os
from collections.abc import Sequence
from functools import lru_cache

from fastembed import TextEmbedding

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


class EmbeddingUnavailableError(RuntimeError):
    """The local embedding model could not be loaded or evaluated."""


@lru_cache(maxsize=1)
def _model() -> TextEmbedding:
    try:
        return TextEmbedding(
            model_name=MODEL_NAME,
            cache_dir=os.getenv("FASTEMBED_CACHE_PATH"),
            threads=2,
        )
    except (OSError, RuntimeError, ValueError) as error:
        raise EmbeddingUnavailableError(
            "Could not load the local embedding model"
        ) from error


def centroid_distance(
    baseline: Sequence[Sequence[float]], recent: Sequence[Sequence[float]]
) -> float:
    if not baseline or not recent or not baseline[0]:
        raise ValueError("embedding windows must not be empty")
    dimension = len(baseline[0])
    if any(len(vector) != dimension for vector in (*baseline, *recent)):
        raise ValueError("embedding dimensions must match")
    if any(
        not math.isfinite(value) for vector in (*baseline, *recent) for value in vector
    ):
        raise ValueError("embedding values must be finite")
    left = [
        sum(vector[i] for vector in baseline) / len(baseline) for i in range(dimension)
    ]
    right = [
        sum(vector[i] for vector in recent) / len(recent) for i in range(dimension)
    ]
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        raise ValueError("embedding centroids must not be zero")
    similarity = sum(a * b for a, b in zip(left, right, strict=True))
    return 1.0 - max(-1.0, min(1.0, similarity / (left_norm * right_norm)))


def embedding_distances(
    baseline: Sequence[str], windows: Sequence[Sequence[str]]
) -> list[float]:
    if len(baseline) < 30 or not windows or any(len(window) < 10 for window in windows):
        raise ValueError(
            "embedding drift requires 30 reference and 10 window complaints"
        )
    texts = list(baseline) + [text for window in windows for text in window]
    if any(not isinstance(text, str) or not text.strip() for text in texts):
        raise ValueError("embedding complaint text must be non-empty")
    try:
        vectors = [vector.tolist() for vector in _model().embed(texts)]
    except (OSError, RuntimeError, ValueError) as error:
        raise EmbeddingUnavailableError("Could not compute local embeddings") from error
    if len(vectors) != len(texts):
        raise EmbeddingUnavailableError("Embedding model returned an incomplete batch")
    reference = vectors[: len(baseline)]
    offset = len(baseline)
    scores = []
    for window in windows:
        scores.append(
            centroid_distance(reference, vectors[offset : offset + len(window)])
        )
        offset += len(window)
    return scores
