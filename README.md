# Junkyard Numerics — Originalism Searcher

AI-assisted research into the **original public meaning of the 1876 Texas Constitution**,
producing pinpoint-cited research memos for appellate lawyers writing history-and-tradition
arguments.

**Demo deep provision:** Art. I, § 17 — *"No person's property shall be **taken, damaged or
destroyed** for or applied to public use without adequate compensation…"* — Texas's famous
1876 addition of "damaged or destroyed" beyond the federal "taken", still litigated in
inverse-condemnation cases today.

## Design principles (see `docs/adr/`)

1. **Three evidence types, never blended** — semantic meaning (what words meant), history &
   tradition (era law/practice), sentiment (attitudes) are separately labeled sections.
2. **Structural citation integrity** — the LLM can only cite retrieved document IDs; the
   renderer refuses to render claims with unresolvable citations. Every excerpt links to the
   archive source for visual verification.
3. **Both-ways memos** — adverse evidence is reported ("opposing counsel will point to…").
4. **Honest methodology** — each memo states what was searched, hit counts, and OCR
   recall limitations.

## Sources (verified — see `docs/SOURCES.md`)

- Chronicling America (LoC) — TX newspapers 1874–1878, JSON API + OCR
- McKay, *Debates in the Texas Constitutional Convention of 1875* (Tarlton PDFs)
- Bouvier's Law Dictionary (1880) & Webster's (1864 text) — Internet Archive
- 1876 Constitution full text — Tarlton Law Library

## Run it

```bash
uv sync

# 1. Ingest (idempotent / resumable)
uv run python -m ingest.constitution      # full 1876 text, structured
uv run python -m ingest.debates           # 65 convention-debate PDFs → text
uv run python -m ingest.dictionaries      # era dictionary entries (needs data/raw/*.txt, see docs/SOURCES.md)
uv run python -m ingest.chronam --terms-file ingest/terms_art1_sec17.txt   # slow (throttled API)

# 2. Build the demo memo (needs ANTHROPIC_API_KEY)
uv run python -m app.pipeline

# 3. Serve the UI
uv run uvicorn app.main:app --reload
# open http://localhost:8000
```

## Layout

- `app/schema.py` — the evidence-record contract everything shares
- `ingest/` — one fetcher per source → `data/corpus/*.jsonl`
- `app/pipeline.py` — two-stage Claude pipeline (per-doc extract → synthesize)
- `app/quantum_search.py` — quantum-inspired O(log n) retrieval index (ADR-0007)
- `app/main.py` + `static/` — FastAPI + memo viewer with side-by-side source panel
- `docs/adr/`, `docs/GLOSSARY.md`, `docs/SOURCES.md` — decisions, terms, verified access patterns

## Quantum-inspired retrieval (ADR-0007)

The candidate selector that gates the expensive per-document LLM extraction used
to scan the whole corpus (O(n)). It is now a **quantum-inspired index**: complex
amplitude/phase (Hilbert-space) embeddings with concept *interference*, retrieved
by dequantized length-squared sampling over a segment-tree — **O(log n) per query**
in the corpus size, no GPU, no quantum-computing library. Basis: *QuanTaxo*
(AAAI-26) and *Pretrained Quantum-Inspired DNN for NLP* (IEEE TCYB 2024).

```bash
uv run python bench_quantum_search.py   # O(log n) vs linear scan + recall
```
