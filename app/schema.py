"""Shared evidence-record schema (ADR-0005).

Every ingest script produces EvidenceRecords; the LLM pipeline may only cite
records that exist in the corpus (ADR-0003: structural citation integrity).
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SourceKind(str, Enum):
    NEWSPAPER = "newspaper"          # Chronicling America / Portal pages
    CONVENTION_DEBATE = "debate"     # McKay Debates (1875 convention floor)
    CONVENTION_JOURNAL = "journal"   # Official journal (image-tier, link-only)
    DICTIONARY = "dictionary"        # Bouvier / Webster entries
    STATUTE = "statute"              # Gammel's Laws of Texas
    CASE = "case"                    # Era case law (stretch)


class EvidenceKind(str, Enum):
    """The three evidence types of ADR-0001. Assigned during extraction,
    describing what a piece of evidence is probative OF — never blended."""

    SEMANTIC = "semantic"        # contemporaneous usage/definition of the terms
    TRADITION = "tradition"      # law/regulation/enforcement practice
    SENTIMENT = "sentiment"      # attitudes, editorials, political mood


class Locator(BaseModel):
    """Pinpoint citation data. Must resolve to something a human can view."""

    url: str                              # canonical archive URL for the item/page
    image_url: Optional[str] = None       # page-image URL for side-by-side display
    page: Optional[str] = None            # page number / sequence within the item
    detail: Optional[str] = None          # column, PDF page, dictionary headword, etc.


class EvidenceRecord(BaseModel):
    """One retrievable primary-source excerpt. The atomic unit of the corpus."""

    id: str                               # stable, e.g. "chronam:sn83025733:1875-10-06:p2"
    source_kind: SourceKind
    source_name: str                      # e.g. "Dallas Daily Herald"
    date: Optional[str] = None            # ISO date (or year) of the source
    locator: Locator
    text: str                             # OCR/extracted text (verbatim; may be rough)
    query_matched: list[str] = Field(default_factory=list)  # which search terms hit
    ocr_quality_note: Optional[str] = None


class ExtractedQuote(BaseModel):
    """Stage-1 output: one quote lifted from one EvidenceRecord."""

    evidence_id: str                      # MUST match an EvidenceRecord.id in corpus
    quote: str                            # verbatim from record.text
    evidence_kind: EvidenceKind
    stance: str                           # "supporting" | "adverse" | "neutral"
    characterization: str                 # one-sentence: what this shows about the question


class MemoClaim(BaseModel):
    """Stage-2 output: one claim in the memo, backed by evidence IDs only."""

    text: str
    evidence_ids: list[str]               # renderer drops the claim if any ID is unknown
    stance: str


class MemoSection(BaseModel):
    kind: EvidenceKind
    heading: str
    claims: list[MemoClaim]


class Memo(BaseModel):
    """The output artifact: three labeled sections + methodology (ADR-0001/0003)."""

    provision: str                        # e.g. "Tex. Const. art. I, § 17 (1876)"
    question: str
    summary: str
    sections: list[MemoSection]
    methodology: str                      # what was searched, hit counts, limitations
