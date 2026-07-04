# ADR-0001: Three evidence types, separately labeled, never blended

Status: accepted
Date: 2026-07-03

## Context

The pitch ("summarize public sentiment to support history-and-tradition arguments") conflates three things courts treat as distinct:

1. **Original public meaning** — semantic: what the text's words meant to an 1876 reader.
2. **History and tradition** — practice: the record of law and enforcement over time (Bruen/Dobbs style).
3. **Public sentiment** — attitudinal: what people felt/argued about the provision.

A blended narrative is rhetorically weaker and legally suspect: a judge (or opposing counsel) will discount a memo that presents editorial opinion as evidence of textual meaning.

## Decision

Every output memo has three separately labeled evidence sections — Semantic meaning, History & tradition, Sentiment context — and the system never merges them into one narrative. **Semantic meaning is the primary product claim** and gets the most engineering investment (corpus-linguistics-style usage evidence). Sentiment is explicitly framed as context, not proof.

## Consequences

- Retrieval and prompting are built per-evidence-type (different sources, different queries, different output schemas), not as one generic "search the archives" call.
- The demo story is honest to the legal domain, which is itself a differentiator.
- More prompt/pipeline surface to build than a single blended summarizer — mitigated by the deep-provision scoping (ADR-0002).
