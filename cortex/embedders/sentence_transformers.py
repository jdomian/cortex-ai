"""Default embedder: all-MiniLM-L6-v2 via sentence-transformers (384-dim).

sentence_transformers is imported lazily inside __init__ to avoid cold-start
cost in environments that do not use this embedder.
"""
from typing import List

from .base import Embedder


class SentenceTransformersEmbedder(Embedder):
    """Wraps sentence_transformers.SentenceTransformer.

    Preserves v0.6.x behavior exactly -- drop-in replacement for the
    direct SentenceTransformer('all-MiniLM-L6-v2') calls that patterns.py used.
    """

    _DEFAULT_MODEL = "all-MiniLM-L6-v2"
    _DEFAULT_DIMENSION = 384

    def __init__(self, model_id: str = None):
        self._model_id = model_id or self._DEFAULT_MODEL
        self._model = None  # lazy

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415
            self._model = SentenceTransformer(self._model_id)
        return self._model

    def embed_one(self, text: str) -> List[float]:
        return self._get_model().encode(text).tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [v.tolist() for v in self._get_model().encode(texts)]

    @property
    def dimension(self) -> int:
        return self._DEFAULT_DIMENSION

    @property
    def model_id(self) -> str:
        return self._model_id


def factory(cfg: dict = None) -> SentenceTransformersEmbedder:
    cfg = cfg or {}
    return SentenceTransformersEmbedder(model_id=cfg.get("model_id"))
