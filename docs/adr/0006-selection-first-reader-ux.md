# ADR-0006: Selection-first reader UX

Status: accepted
Date: 2026-07-03

## Context

The original entry point (browse sidebar + prebuilt memo) had no natural way to ask
about a specific phrase. A free-text LLM search box was considered and rejected in
favor of grounding the interaction in the document itself.

## Decision

The entry point is a **searchable reader view of the full 1876 Texas Constitution**.
Research starts from a text selection:

1. **Selection unit:** any text span, snapped to word boundaries; the enclosing
   article/section rides along as context.
2. **Trigger:** selection arms a popover with a **"Research" button** — nothing runs
   (and no API cost is incurred) until the user clicks it.
3. **Term derivation:** the verbatim phrase is searched first; an LLM call expands
   era-appropriate 1870s variants. Both appear as **toggleable term chips** above the
   results — the lawyer sees and controls exactly what was searched.
4. **Side panel:** a corpus evidence feed **grouped by the three evidence sources**
   (dictionaries / convention debates / newspapers), each hit expandable into the
   existing source viewer (OCR + archive link + scan). A **"Build research memo"**
   button at the top runs the full two-stage pipeline for the selection — evidence
   first, expensive artifact on demand.

## Consequences

- New endpoints: term expansion (`POST /api/research/terms`), corpus concordance
  search (`GET /api/search`), both cheap; the memo pipeline is reused for the upgrade.
- Concordance search is plain keyword matching over the local corpus — instant and
  free; the LLM only shapes the query, never the results list (consistent with
  ADR-0003 integrity posture).
- The prebuilt § 17 demo memo remains reachable (linked when the selection falls in
  Art. I § 17) so the demo doesn't depend on live pipeline runs.
