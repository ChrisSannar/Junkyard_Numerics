"""Selection-first research: era term expansion + corpus concordance search (ADR-0006).

- expand_terms(): one cheap LLM call turning a selected phrase into toggleable
  1870s-vocabulary search terms. The LLM shapes the QUERY only — it never touches
  the results list (ADR-0003 posture).
- concordance(): plain keyword search over the local corpus, returning KWIC
  snippets grouped by source kind. Instant, no API cost.
"""

from __future__ import annotations

import os
import re

import anthropic
from pydantic import BaseModel

from app.schema import EvidenceRecord, SourceKind

EXPAND_MODEL = os.environ.get("ORIGINALISM_EXPAND_MODEL", "claude-opus-4-8")

client = anthropic.Anthropic()


# ---------- term expansion ----------

class TermExpansion(BaseModel):
    terms: list[str]           # era-appropriate search terms/phrases, most useful first
    rationale: str             # one short sentence per line explaining the choices


EXPAND_SYSTEM = """You generate corpus search terms for research into the original public
meaning of the Texas Constitution of 1876. The corpus is 1870s Texas newspapers (rough OCR),
the 1875 constitutional convention debates, and era legal/general dictionaries.

Given a phrase a lawyer selected from the constitution (plus its section for context),
produce 4-8 additional search terms that 1870s sources would actually use when discussing
this concept. Favor:
- period vocabulary and legal terms of art (e.g. "internal improvements", "right of way",
  "eminent domain", "condemnation")
- short concrete phrases over abstractions (2-3 words; single words only if distinctive)
- variants a newspaper compositor would set, not modern doctrinal labels

Do NOT include the verbatim selected phrase itself (it is always searched first), and do
not include terms so generic they match everything ("law", "property", "state")."""


def expand_terms(phrase: str, section_context: str) -> TermExpansion:
    prompt = (f"Selected phrase: \"{phrase}\"\n\n"
              f"Section it appears in:\n{section_context[:2000]}")
    response = client.messages.parse(
        model=EXPAND_MODEL,
        max_tokens=1000,
        system=EXPAND_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        output_format=TermExpansion,
    )
    return response.parsed_output


# ---------- concordance search ----------

class Hit(BaseModel):
    evidence_id: str
    source_kind: str
    source_name: str
    date: str | None
    term: str                  # which search term matched
    snippet: str               # KWIC excerpt around the match
    url: str


KWIC_CHARS = 220


def _kwic(text: str, term: str) -> str | None:
    i = text.lower().find(term.lower())
    if i < 0:
        return None
    start = max(0, i - KWIC_CHARS // 2)
    end = min(len(text), i + len(term) + KWIC_CHARS // 2)
    snippet = re.sub(r"\s+", " ", text[start:end]).strip()
    return ("…" if start > 0 else "") + snippet + ("…" if end < len(text) else "")


def concordance(corpus: dict[str, EvidenceRecord], terms: list[str],
                per_kind_limit: int = 12) -> dict[str, list[Hit]]:
    """Search all terms; return hits grouped by source kind, best-term-first."""
    grouped: dict[str, list[Hit]] = {k.value: [] for k in SourceKind}
    seen: set[tuple[str, str]] = set()  # (record, term) pairs
    for term in terms:
        t = term.strip().strip('"')
        if len(t) < 3:
            continue
        for rec in corpus.values():
            if (rec.id, t) in seen:
                continue
            snippet = _kwic(rec.text, t)
            if snippet is None:
                continue
            seen.add((rec.id, t))
            grouped[rec.source_kind.value].append(Hit(
                evidence_id=rec.id,
                source_kind=rec.source_kind.value,
                source_name=rec.source_name,
                date=rec.date,
                term=t,
                snippet=snippet,
                url=rec.locator.url,
            ))
    # cap per group, keep insertion order (terms were given most-useful-first)
    return {k: v[:per_kind_limit] for k, v in grouped.items() if v}
