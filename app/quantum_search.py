"""Quantum-inspired corpus retrieval with O(log n) per-query complexity (ADR-0007).

Motivation
----------
The two hot paths in this tool both do a *linear* O(n) scan over the whole
corpus (see docs the ADR references):

  * ``pipeline.relevant_records`` — term-count scan that gates the expensive
    Stage-1 LLM extraction (one Claude call per surviving record);
  * ``search.concordance`` — term scan behind ``GET /api/search``.

This module replaces the scan with a **quantum-inspired retrieval index** whose
per-query cost is O(log n) in the corpus size n. It is built on two ideas from
the attached literature, combined and then improved on:

1. Complex amplitude/phase (Hilbert-space) text embeddings with *interference*
   between latent concepts — the "sememe" superposition of Mishra et al.,
   *QuanTaxo* (AAAI-26) §3.1, and the amplitude/phase split of Shi et al.,
   *Pretrained Quantum-Inspired DNN for NLP* (IEEE TCYB 2024). A word is a
   complex superposition ``A(x) ⊙ e^{iΦ(x)}``; two words landing on the same
   latent concept combine as ``a1²+a2²+2·a1·a2·cos(φ1−φ2)`` — the double-slit
   interference term. Similarity is the pure-state trace inner product
   ``Tr(ρ_q ρ_d) = |⟨q|d⟩|²`` (QuanTaxo §3.3–3.4).

2. **Dequantization by length-squared (ℓ²) sampling.** QuanTaxo itself notes
   its inference is ``O(|N|)`` per query — a full brute-force pass over every
   node. We remove that bottleneck the classical quantum-inspired way: a
   "sample-and-query" (SQ) segment-tree data structure supports drawing an
   index i ∝ |amplitude_i|² in O(log n). Concentrating a *constant* number of
   such samples on the query-aligned latent concepts yields the high-overlap
   documents without ever touching all n — the same dequantization pattern that
   turns quantum recommendation/search speedups into classical O(polylog n)
   algorithms. Exact interference re-scoring runs only on the O(1) sampled
   candidates.

Improvement over the sources
----------------------------
  * QuanTaxo/QPFE score every candidate (O(n) or O(|N|)) on a GPU with BERT/
    ERNIE. Here retrieval is **O(log n)** in n and needs no GPU, no pretrained
    transformer, and no quantum-computing library — the complex embedding is a
    deterministic hashed projection, so the whole thing runs offline.
  * The interference similarity that QuanTaxo computes densely is computed here
    only on the sampled candidate set.

Complexity (honest statement)
-----------------------------
  * Index build: O(n · d) one-time — every document is embedded once (you cannot
    do better than reading the corpus once). d is the fixed latent dimension.
  * Per query: O(S · (log d + log n) + S · d) = **O(log n)** in the corpus size,
    where S (sample budget) and d (latent dim) are fixed constants.

No third-party dependencies (pure-Python ``complex``); no quantum libraries.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # keeps this module dependency-free at runtime (no pydantic)
    from app.schema import EvidenceRecord

# ---------- tokenisation ----------

_TOKEN_RE = re.compile(r"[a-z]+")
_MIN_TOKEN = 3  # matches the concordance's len<3 skip


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if len(t) >= _MIN_TOKEN]


# ---------- complex sememe embedding (QuanTaxo §3.1 / QPFE amplitude+phase) ----------

class _Hashes:
    """Stable, salt-free token hashing (Python's ``hash`` is per-process salted).

    Each token maps to a (latent-concept index, unit phasor e^{iφ}) pair. The map
    is memoised because the same tokens recur across many documents, so hashing
    dominates build time otherwise.
    """

    __slots__ = ("dim", "_cache")

    def __init__(self, dim: int):
        self.dim = dim
        self._cache: dict[str, tuple[int, complex]] = {}

    def project(self, token: str) -> tuple[int, complex]:
        hit = self._cache.get(token)
        if hit is not None:
            return hit
        hd = hashlib.blake2b(token.encode(), digest_size=8, person=b"sememe").digest()
        j = int.from_bytes(hd, "big") % self.dim
        hp = hashlib.blake2b(token.encode(), digest_size=8, person=b"phase00").digest()
        # phase Φ(x) ∈ [-pi, pi) carries inter-concept interference
        phi = (int.from_bytes(hp, "big") / 2**64) * (2 * math.pi) - math.pi
        out = (j, complex(math.cos(phi), math.sin(phi)))
        self._cache[token] = out
        return out


def embed(tokens: list[str], dim: int, hashes: _Hashes,
          idf: dict[str, float] | None = None) -> tuple[list[complex], float]:
    """Text -> (unit complex state vector |ψ⟩, length-squared mass ‖raw‖²).

    Each token contributes a complex amplitude ``a·e^{iφ}`` to its latent concept
    (sememe) coordinate. Tokens sharing a coordinate *interfere* (their complex
    amplitudes add), reproducing QuanTaxo's superposition term. ``a`` is a
    sublinear tf weight, optionally scaled by idf; ``φ`` is the token's phase.
    The returned mass is the pre-normalisation ℓ² weight used for SQ sampling.
    """
    vec = [0j] * dim
    counts: dict[str, int] = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1
    for t, c in counts.items():
        a = 1.0 + math.log(c)                       # sublinear tf
        if idf is not None:
            a *= idf.get(t, 0.0)
        if a == 0.0:
            continue
        j, phasor = hashes.project(t)               # amplitude a, phase e^{iφ}
        vec[j] += a * phasor
    mass = sum((z.real * z.real + z.imag * z.imag) for z in vec)
    if mass <= 0.0:
        return vec, 0.0
    norm = math.sqrt(mass)
    return [z / norm for z in vec], mass


def interference_similarity(q: list[complex], d: list[complex]) -> float:
    """Pure-state trace inner product Tr(ρ_q ρ_d) = |⟨q|d⟩|² (QuanTaxo §3.4).

    ⟨q|d⟩ = Σ_j conj(q_j)·d_j is complex; its squared magnitude includes the
    cross-concept cos(Δφ) interference terms, which real cosine similarity drops.
    """
    acc = 0j
    for qj, dj in zip(q, d):
        acc += qj.conjugate() * dj
    return acc.real * acc.real + acc.imag * acc.imag


# ---------- segment tree: O(log n) length-squared sampling (the SQ structure) ----------

class SegmentTree:
    """Array-backed segment tree over non-negative weights.

    Supports ``sample(u)`` — return index i with probability w_i/Σw in O(log n)
    by descending on a prefix sum — and ``total()``. This is the classical
    "sample-and-query" access primitive that makes ℓ²-sampling O(log n).
    """

    __slots__ = ("n", "size", "tree")

    def __init__(self, weights: list[float]):
        self.n = len(weights)
        self.size = 1
        while self.size < max(self.n, 1):
            self.size *= 2
        self.tree = [0.0] * (2 * self.size)
        for i, w in enumerate(weights):
            self.tree[self.size + i] = w
        for i in range(self.size - 1, 0, -1):
            self.tree[i] = self.tree[2 * i] + self.tree[2 * i + 1]

    def total(self) -> float:
        return self.tree[1]

    def sample(self, u: float) -> int:
        """u ∈ [0,1): return an index drawn ∝ weight. O(log n)."""
        target = u * self.tree[1]
        node = 1
        while node < self.size:
            left = self.tree[2 * node]
            if target < left:
                node = 2 * node
            else:
                target -= left
                node = 2 * node + 1
        return node - self.size


# ---------- the quantum-inspired index ----------

@dataclass
class QuantumIndex:
    # dim (latent concepts) must be sized to the vocabulary: hash collisions scale
    # as vocab/dim, and a collided concept lets off-topic docs steal ℓ²-sampling
    # mass from on-topic ones. 768 mirrors QuanTaxo's density-matrix dimension.
    dim: int = 768
    sample_budget: int = 256         # S: number of ℓ²-samples per query (constant)
    seed: int = 0x51D
    ids: list[str] = field(default_factory=list)
    vectors: list[list[complex]] = field(default_factory=list)
    idf: dict[str, float] = field(default_factory=dict)
    _hashes: _Hashes = field(init=False)
    _dim_trees: list[SegmentTree] = field(default_factory=list)
    _query_dim: int = field(default=0)

    def __post_init__(self) -> None:
        self._hashes = _Hashes(self.dim)

    # ---- build (O(n·d), one-time) ----

    @classmethod
    def from_corpus(cls, corpus: dict[str, EvidenceRecord], **kw) -> "QuantumIndex":
        idx = cls(**kw)
        idx.build([(r.id, r.text) for r in corpus.values()])
        return idx

    def build(self, docs: list[tuple[str, str]]) -> "QuantumIndex":
        toks = [(rid, _tokens(text)) for rid, text in docs]
        # idf over the corpus (used for both docs and queries)
        df: dict[str, int] = {}
        for _, ts in toks:
            for t in set(ts):
                df[t] = df.get(t, 0) + 1
        n = max(len(toks), 1)
        self.idf = {t: math.log(1.0 + n / c) for t, c in df.items()}

        self.ids, self.vectors = [], []
        for rid, ts in toks:
            vec, mass = embed(ts, self.dim, self._hashes, self.idf)
            if mass <= 0.0:
                continue
            self.ids.append(rid)
            self.vectors.append(vec)

        # one segment tree per latent concept j over {|d_{i,j}|²}: lets us sample a
        # document ∝ its squared amplitude on concept j in O(log n) (SQ(A) access).
        m = len(self.vectors)
        self._dim_trees = []
        for j in range(self.dim):
            col = [0.0] * m
            for i in range(m):
                z = self.vectors[i][j]
                col[i] = z.real * z.real + z.imag * z.imag
            self._dim_trees.append(SegmentTree(col))
        return self

    # ---- query (O(log n) in corpus size) ----

    def _rng(self):
        # tiny deterministic LCG so results are reproducible without global state
        state = self.seed | 1

        def nxt() -> float:
            nonlocal state
            state = (1103515245 * state + 12345) & 0x7FFFFFFF
            return state / 0x7FFFFFFF

        return nxt

    def search(self, query_text: str, k: int = 40) -> list[tuple[str, float]]:
        """Return up to k (evidence_id, similarity) pairs, best first. O(log n)."""
        if not self.vectors:
            return []
        q, qmass = embed(_tokens(query_text), self.dim, self._hashes, self.idf)
        if qmass <= 0.0:
            return []

        # query concept-importance tree over {|q_j|²}: sample the concepts the query
        # actually excites, ∝ their squared amplitude, in O(log d).
        qcol = [z.real * z.real + z.imag * z.imag for z in q]
        qtree = SegmentTree(qcol)
        rng = self._rng()

        # length-squared sampling: pick a concept j ∝ |q_j|², then a doc i ∝ |d_{i,j}|².
        # This concentrates the O(S) samples on query-aligned documents (dequantized
        # inner-product / recommendation primitive) without scanning the corpus.
        candidates: set[int] = set()
        for _ in range(self.sample_budget):
            j = qtree.sample(rng())
            tree = self._dim_trees[j]
            if tree.total() <= 0.0:
                continue
            candidates.add(tree.sample(rng()))

        # exact interference re-scoring on the O(S) candidates only (O(S·d)).
        scored = [(self.ids[i], interference_similarity(q, self.vectors[i]))
                  for i in candidates]
        scored.sort(key=lambda x: -x[1])
        return scored[:k]

    # ---- reference O(n) scorer, for tests/benchmark parity ----

    def search_exact(self, query_text: str, k: int = 40) -> list[tuple[str, float]]:
        """Brute-force top-k over all n docs (the QuanTaxo O(|N|) baseline)."""
        q, qmass = embed(_tokens(query_text), self.dim, self._hashes, self.idf)
        if qmass <= 0.0:
            return []
        scored = [(self.ids[i], interference_similarity(q, self.vectors[i]))
                  for i in range(len(self.vectors))]
        scored.sort(key=lambda x: -x[1])
        return scored[:k]
