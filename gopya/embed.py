"""Local dense embeddings: TF-IDF over words and character n-grams, reduced with SVD (LSA).

This keeps the project runnable with no model download and no API key. Character n-grams make it
robust to spelling variants of Nepali names and places (Ashwin/Asoj, Gongar/Gonggar). The
Embedder interface is one method, so a hosted model (Azure OpenAI, Bedrock, bge-m3) can replace
it without touching retrieval.
"""

from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
from scipy.sparse import hstack
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize


class LsaEmbedder:
    name = "lsa-local"

    def __init__(self, dims: int = 96, seed: int = 0):
        self.dims = dims
        self.seed = seed
        self.words = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1, stop_words="english")
        self.chars = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=1)
        self.svd: TruncatedSVD | None = None

    def fit(self, texts: list[str]) -> "LsaEmbedder":
        x = hstack([self.words.fit_transform(texts), self.chars.fit_transform(texts)]).tocsr()
        dims = max(2, min(self.dims, x.shape[0] - 1, x.shape[1] - 1))
        self.svd = TruncatedSVD(n_components=dims, random_state=self.seed).fit(x)
        return self

    def embed(self, texts: list[str]) -> np.ndarray:
        if self.svd is None:
            raise RuntimeError("embedder is not fitted")
        x = hstack([self.words.transform(texts), self.chars.transform(texts)]).tocsr()
        return normalize(self.svd.transform(x)).astype(np.float32)

    def save(self, path: Path) -> None:
        path.write_bytes(pickle.dumps(self))

    @staticmethod
    def load(path: Path) -> "LsaEmbedder":
        return pickle.loads(path.read_bytes())
