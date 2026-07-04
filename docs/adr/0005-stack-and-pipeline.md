# ADR-0005: Python + web UI; pre-fetched §17 corpus; staged LLM pipeline

Status: accepted
Date: 2026-07-03

## Decision

1. **Stack:** Python backend (FastAPI), `requests`/`httpx` for archive APIs, Claude API for analysis, a simple HTML/JS front end for the memo + side-by-side source viewer (ADR-0003 §2).
2. **Corpus:** Pre-fetch a local corpus for the deep provision (Art. I, § 17): bulk-pull 1874–1878 hits for the § 17 term list into local JSON — text, locators, page-image URLs. The demo runs fast and offline-safe. Live archive search is the thin-path fallback for other provisions.
3. **LLM shape — staged pipeline:**
   - **Stage 1 (extract):** per retrieved document, a structured-output call extracts relevant quotes + characterization, keyed by the document's ID. Parallelizable.
   - **Stage 2 (synthesize):** builds the three-section memo (ADR-0001) from Stage-1 outputs *only* — it never sees raw archives, so it can only cite extracted, ID-bearing evidence (enforces ADR-0003 §1 naturally).

## Consequences

- An `ingest/` script layer (one per source) and a `data/corpus/` directory of normalized JSON records become the first build targets.
- Evidence record schema is the contract everything shares: `{id, source, title, date, locator{page, url, image_url}, text, query_matched}`.
- Claude structured outputs (tool-use / JSON schema) used in both stages; renderer validates every cited ID against the corpus before rendering.
