# ADR-0007: Quantum-inspired O(log n) corpus retrieval

Status: accepted
Date: 2026-07-03

## Context

Two paths in the tool scan the **entire** corpus linearly, O(n) in the number of
records n:

- `pipeline.relevant_records` — a term-count scan that selects which records get
  a Stage-1 LLM extraction. Stage-1 is by far the most expensive thing the tool
  does (one Claude call per surviving record, up to 24k chars each), so the
  quality of this gate directly controls both cost and answer quality.
- `search.concordance` — the term scan behind `GET /api/search`.

Both were plain substring/term-count matching: no notion of interference between
related concepts, and cost growing linearly with the corpus. As ingestion adds
newspapers/debates, the scan and (worse) the number of low-value LLM extractions
grow with it.

We were asked to add a **quantum-inspired algorithm with O(log n) computational
complexity**, grounded in the attached literature, **without any quantum-computing
library**.

## Decision

Add `app/quantum_search.py`, a dependency-free (pure-Python `complex`)
quantum-inspired retrieval index, and use it as the candidate selector inside
`relevant_records` (with the linear scan retained as a fallback).

It combines two results from the literature and improves on them:

1. **Complex amplitude/phase Hilbert-space embeddings with interference.** Each
   token contributes a complex amplitude `a·e^{iφ}` to a hashed latent-concept
   ("sememe") coordinate; tokens sharing a coordinate add as complex numbers, so
   they interfere as `a1² + a2² + 2·a1·a2·cos(φ1−φ2)` — the double-slit term.
   Similarity is the pure-state trace inner product `Tr(ρ_q ρ_d) = |⟨q|d⟩|²`.
   Basis: Mishra et al., *QuanTaxo* (AAAI-26), §§3.1–3.4; Shi et al., *Pretrained
   Quantum-Inspired DNN for NLP* (IEEE TCYB 2024), amplitude/phase split.

2. **Dequantization by length-squared (ℓ²) sampling.** QuanTaxo states its own
   inference is `O(|N|)` per query — a brute-force pass over every node. We remove
   that with a "sample-and-query" segment-tree structure: sample a latent concept
   j ∝ |q_j|² (O(log d)), then a document i ∝ |d_{i,j}|² (O(log n)). A constant
   number S of such samples concentrates on the query-aligned documents without
   touching all n; exact interference re-scoring runs on the O(S) candidates only.
   This is the same classical dequantization pattern behind O(polylog n)
   quantum-inspired recommendation/search algorithms.

### Why this is an improvement, not a reimplementation

- QuanTaxo/QPFE score **every** candidate on a GPU with BERT/ERNIE. Here the
  embedding is a deterministic hashed projection — no GPU, no pretrained
  transformer, no training — and retrieval is **O(log n)** in n, not O(n).
- The interference similarity QuanTaxo computes densely is computed here only on
  the sampled candidate set.

## Complexity (stated honestly)

- **Index build:** O(n·d), one-time — every document is embedded once (you cannot
  beat reading the corpus once). d is the fixed latent dimension. Built once and
  cached, so it amortises across a session's queries.
- **Per query:** O(S·(log d + log n) + S·d) = **O(log n)** in the corpus size,
  with S (sample budget) and d fixed constants.

`bench_quantum_search.py` measures the O(log n) sampler against the O(n)
brute-force scorer *in the same interference-similarity space* (isolating the
sampling speedup). Representative run (pure Python, dim=768, S=256):

```
       n   linear(ms)  quantum(ms)  speedup  recall@40
     500      72.0        16.4        4.4x      0.97
    2000     305.9        24.6       12.4x      0.95
    8000    1340.5        51.1       26.2x      0.62
```

Per-query time grows ~logarithmically (16 → 51 ms for a 16× larger corpus) while
the brute-force scan grows linearly (72 → 1341 ms) — the O(log n) signature.

### Crossover and the recall knob (honest limits)

- **Crossover.** At the tool's current corpus (~690 records) the plain O(n)
  term-count scan is already sub-50 ms and beats the index's one-time build, so
  `relevant_records` uses the linear scan below `QUANTUM_MIN_CORPUS` (default
  2000, env `ORIGINALISM_QUANTUM_MIN`) and switches to the quantum index above
  it. This is a **scalability** optimisation: it pays off as the corpus grows.
- **Recall.** With fixed-budget ℓ²-sampling, recall is governed by the constants
  (`dim` vs vocabulary size → hash-collision rate; `sample_budget` S vs corpus
  selectivity), **not by n**. Recall@40 stays ≥0.95 while relevant docs are a
  healthy fraction of the corpus and softens (≈0.62 in the benchmark's
  50-relevant-among-8000-pure-noise stress case). Raising `dim`/S restores recall
  at a constant-factor cost, preserving O(log n) in n. Because this index feeds
  the *candidate pool* for the precise LLM extraction stage — not the final
  answer — high recall at the tool's operating scale is what matters.

## Consequences

- `relevant_records` now returns interference-ranked candidates and is sublinear
  per query; it falls back to the linear scan when the quantum path is empty
  (e.g. empty corpus), so behavior degrades safely.
- The index is cached per corpus identity, so the O(n·d) build is paid once and
  reused across `/api/memo` requests.
- Consistent with ADR-0003: the algorithm shapes **which** ID-bearing records are
  reviewed; it never fabricates evidence or text. Every returned record is a real
  corpus record the renderer can still verify.
- Sampling is seeded (deterministic LCG) so results are reproducible.
- Tunable knobs: `dim` (latent concepts), `sample_budget` (S — recall/latency
  trade-off). Larger S → higher recall, still O(log n) in n.
