"""Two-stage memo pipeline (ADR-0005), with structural citation integrity (ADR-0003).

Stage 1 (extract):   per evidence record, Claude extracts relevant quotes with a
                     structured schema keyed by the record's ID.
Stage 2 (synthesize): Claude writes the three-section memo (ADR-0001) from the
                     Stage-1 extracts ONLY — it never sees raw archives, so it
                     can only cite extracted, ID-bearing evidence.
Renderer validation: any claim citing an unknown evidence ID is dropped and flagged.

Requires ANTHROPIC_API_KEY in the environment.
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import anthropic
from pydantic import BaseModel

from app.schema import (
    EvidenceKind,
    EvidenceRecord,
    ExtractedQuote,
    Memo,
    MemoClaim,
    MemoSection,
)

MODEL = os.environ.get("ORIGINALISM_MODEL", "claude-opus-4-8")
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

client = anthropic.Anthropic()


# ---------- corpus ----------

def load_corpus() -> dict[str, EvidenceRecord]:
    corpus: dict[str, EvidenceRecord] = {}
    for f in (DATA_DIR / "corpus").glob("*.jsonl"):
        for line in f.read_text().splitlines():
            r = EvidenceRecord.model_validate_json(line)
            corpus[r.id] = r
    return corpus


def relevant_records(corpus: dict[str, EvidenceRecord], terms: list[str],
                     limit: int = 40) -> list[EvidenceRecord]:
    """Cheap relevance pass: keep records whose text matches any query term."""
    lowered = [t.lower().strip('"') for t in terms]
    hits = []
    for r in corpus.values():
        text = r.text.lower()
        score = sum(text.count(t) for t in lowered)
        if score:
            hits.append((score, r))
    hits.sort(key=lambda x: -x[0])
    return [r for _, r in hits[:limit]]


# ---------- stage 1: per-document extraction ----------

class Extraction(BaseModel):
    relevant: bool
    quotes: list[ExtractedQuote]


EXTRACT_SYSTEM = """You are a rigorous legal-history research assistant working on the
original public meaning of the Texas Constitution of 1876, Art. I, § 17:
"No person's property shall be taken, damaged or destroyed for or applied to
public use without adequate compensation being made..."

You will be given ONE primary-source document (often rough OCR of an 1870s
newspaper, the 1875 convention debates, or an era dictionary) and an
interpretive question. Extract quotes that bear on the question.

Rules:
- quote must be VERBATIM from the document text (OCR errors included). Never fix,
  paraphrase, or reconstruct text.
- evidence_kind: "semantic" = shows what words like "damaged" meant in ordinary or
  legal usage; "tradition" = shows law/regulation/enforcement practice; "sentiment" =
  shows attitudes/political mood about the provision.
- stance: "supporting" if it supports the proposition in the question, "adverse" if it
  cuts against it, "neutral" otherwise. Report adverse evidence faithfully — the lawyer
  needs the bad news too.
- evidence_id must be exactly the ID given.
- If the document is irrelevant (e.g., "damage" appears only in a storm report with no
  bearing on legal meaning), set relevant=false and quotes=[]. A storm report CAN be
  relevant to semantic usage if it shows how "damage to property" was ordinarily used —
  use judgment: ordinary usage evidence is the heart of a semantic claim.
"""


def extract_one(record: EvidenceRecord, question: str) -> Extraction | None:
    prompt = (
        f"Interpretive question: {question}\n\n"
        f"Document ID: {record.id}\n"
        f"Source: {record.source_name} ({record.date})\n"
        f"Document text:\n<document>\n{record.text[:24000]}\n</document>"
    )
    try:
        response = client.messages.parse(
            model=MODEL,
            max_tokens=4000,
            system=EXTRACT_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            output_format=Extraction,
        )
        return response.parsed_output
    except anthropic.APIStatusError as e:
        print(f"extract failed for {record.id}: {e.status_code}")
        return None


def run_extraction(records: list[EvidenceRecord], question: str,
                   max_workers: int = 4) -> list[ExtractedQuote]:
    quotes: list[ExtractedQuote] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(extract_one, r, question): r for r in records}
        for fut in as_completed(futures):
            rec = futures[fut]
            result = fut.result()
            if result and result.relevant:
                # enforce ID integrity at the boundary
                for q in result.quotes:
                    if q.evidence_id == rec.id:
                        quotes.append(q)
                    else:
                        print(f"DROPPED: extraction cited wrong ID {q.evidence_id}")
            print(f"  extracted {rec.id}: "
                  f"{len(result.quotes) if result and result.relevant else 0} quotes")
    return quotes


# ---------- stage 2: memo synthesis ----------

class MemoDraft(BaseModel):
    summary: str
    sections: list[MemoSection]


SYNTH_SYSTEM = """You are drafting a legal research memo for an appellate lawyer on the
original public meaning of Tex. Const. art. I, § 17 (1876).

You will receive extracted quotes from primary sources, each tagged with an
evidence ID, evidence kind, and stance. Write a memo with EXACTLY three sections,
one per evidence kind, in this order:
1. kind "semantic",  heading "Semantic Meaning (contemporaneous usage)"
2. kind "tradition", heading "History & Tradition (era law and practice)"
3. kind "sentiment", heading "Sentiment Context (contemporary attitudes)"

Rules:
- Every claim must cite one or more evidence_ids FROM THE PROVIDED EXTRACTS ONLY.
  Never invent an ID. A claim without evidence must not be written.
- Assess the question both ways: include adverse evidence with stance "adverse" and
  frame it candidly ("opposing counsel will point to...").
- Never blend the three kinds into one narrative. Semantic-meaning claims are about
  what words meant; do not support them with sentiment evidence.
- Quote sparingly and precisely; characterize accurately. The lawyer will verify every
  quote against the page image.
- If a section has no evidence, include it with an honest claim like "The corpus
  search returned no usable evidence for this section" citing no IDs (empty list is
  allowed ONLY for this no-evidence disclaimer).
"""


def synthesize(question: str, provision_text: str,
               quotes: list[ExtractedQuote]) -> MemoDraft:
    extracts_json = json.dumps([q.model_dump() for q in quotes], indent=1)
    prompt = (
        f"Provision (Tex. Const. art. I, § 17 (1876)):\n{provision_text}\n\n"
        f"Interpretive question: {question}\n\n"
        f"Extracted evidence:\n{extracts_json}"
    )
    with client.messages.stream(
        model=MODEL,
        max_tokens=32000,
        system=SYNTH_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        output_format=MemoDraft,
    ) as stream:
        response = stream.get_final_message()
    return response.parsed_output


# ---------- renderer validation (ADR-0003 §1) ----------

def validate_memo(draft: MemoDraft, corpus: dict[str, EvidenceRecord],
                  question: str, provision: str,
                  methodology: str) -> tuple[Memo, list[str]]:
    """Drop any claim citing an unknown evidence ID. Returns (memo, dropped_claims)."""
    dropped: list[str] = []
    sections: list[MemoSection] = []
    for sec in draft.sections:
        kept: list[MemoClaim] = []
        for claim in sec.claims:
            unknown = [i for i in claim.evidence_ids if i not in corpus]
            if unknown:
                dropped.append(f"{claim.text[:80]}... (unknown IDs: {unknown})")
            else:
                kept.append(claim)
        sections.append(MemoSection(kind=sec.kind, heading=sec.heading, claims=kept))
    memo = Memo(
        provision=provision,
        question=question,
        summary=draft.summary,
        sections=sections,
        methodology=methodology,
    )
    return memo, dropped


# ---------- orchestration ----------

def build_memo(question: str, terms: list[str]) -> Memo:
    corpus = load_corpus()
    constitution = json.loads((DATA_DIR / "constitution.json").read_text())
    s17 = next(s["text"] for a in constitution["articles"] if a["key"] == "I"
               for s in a["sections"] if s["num"] == "17")

    records = relevant_records(corpus, terms)
    print(f"{len(records)} relevant records of {len(corpus)} in corpus")

    quotes = run_extraction(records, question)
    print(f"stage 1 complete: {len(quotes)} quotes extracted")

    by_source = {}
    for r in records:
        by_source[r.source_kind.value] = by_source.get(r.source_kind.value, 0) + 1
    methodology = (
        f"Corpus: {len(corpus)} primary-source records (Chronicling America TX newspapers "
        f"1874-1878; McKay Debates of the 1875 Convention; Bouvier's and Webster's era "
        f"dictionaries). Query terms: {', '.join(terms)}. {len(records)} records matched and "
        f"were reviewed ({by_source}); {len(quotes)} quotes extracted. Limitations: archive "
        f"OCR of 1870s newsprint is imperfect — searches report what was FOUND, not all that "
        f"existed; misrecognized words reduce recall. Every quote links to its source for "
        f"visual verification."
    )

    draft = synthesize(question, s17, quotes)
    memo, dropped = validate_memo(
        draft, corpus, question, "Tex. Const. art. I, § 17 (1876)", methodology)
    if dropped:
        print(f"renderer dropped {len(dropped)} claims with unresolvable citations:")
        for d in dropped:
            print(f"  - {d}")
    return memo


if __name__ == "__main__":
    QUESTION = ('Did "damaged" in Art. I, § 17 encompass consequential injury to '
                "property (impaired access, flooding) without physical appropriation?")
    TERMS = ["damaged", "damage to property", "consequential damages",
             "compensation", "public use", "right of way"]
    memo = build_memo(QUESTION, TERMS)
    out = DATA_DIR / "memo_art1_sec17.json"
    out.write_text(memo.model_dump_json(indent=1))
    print(f"memo written to {out}")
