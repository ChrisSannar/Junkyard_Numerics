# ADR-0003: Structural citation integrity; image-beside-text; honest recall

Status: accepted
Date: 2026-07-03

## Context

The product's entire value is citations, and legal AI's most famous failure is fabricated ones (real sanctions cases). Separately, 1870s newspaper OCR is unreliable in two directions: displayed excerpts may be garbage, and misrecognized words silently break search recall.

## Decision

1. **The LLM is never the source of a citation.** Retrieval returns documents with stable IDs and locators (archive, paper, date, page, coordinates when available). The LLM's output schema may only reference retrieved doc IDs; the memo renderer resolves IDs to source links and refuses to render any claim whose ID does not resolve. Hallucinated citations are structurally unrenderable, not merely discouraged.
2. **Every excerpt is shown beside (or one click from) the page image.** The tool never asks to be trusted about what a source says; the human verifies with their eyes. This is the concrete form of the pinpoint-citation promise.
3. **Accept OCR-driven recall loss, and disclose methodology.** Search archive OCR as-is; each memo states what was searched (archives, date range, query variants, hit counts) and the known limitation. Variant/fuzzy query expansion is a stretch goal, not a dependency.

## Consequences

- Output schema design (claims referencing evidence IDs) is core architecture, not a nicety — build it first.
- Retrieval must carry locators end-to-end; any pipeline step that drops the locator is a bug.
- The memo gains a "Methodology & limitations" section — which is itself credibility-building for the legal audience.
- Silent evidence *absence* remains possible (a key 1876 article the OCR mangled); the memo's phrasing must claim "we found N instances," never "there were only N instances."
