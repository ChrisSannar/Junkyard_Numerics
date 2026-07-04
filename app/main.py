"""Originalism Searcher — FastAPI backend.

Endpoints:
  GET  /api/constitution                 — full 1876 structure (browse path)
  GET  /api/provision/{art}/{sec}        — one provision's text
  GET  /api/evidence/{evidence_id}       — resolve a citation to its source record
  GET  /api/memo/demo                    — the pre-built §17 demo memo
  POST /api/memo                         — build a memo live (slow; demo fallback)
  /                                      — the web UI (static/index.html)

Run:  uv run uvicorn app.main:app --reload
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.pipeline import build_memo, load_corpus
from app.search import concordance, define_phrase, expand_terms

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

app = FastAPI(title="Originalism Searcher")

_corpus = None


def corpus():
    global _corpus
    if _corpus is None:
        _corpus = load_corpus()
    return _corpus


@app.get("/api/constitution")
def constitution():
    return json.loads((DATA_DIR / "constitution.json").read_text())


@app.get("/api/provision/{art}/{sec}")
def provision(art: str, sec: str):
    doc = json.loads((DATA_DIR / "constitution.json").read_text())
    for a in doc["articles"]:
        if a["key"].upper() == art.upper():
            for s in a["sections"]:
                if s["num"] == sec:
                    return {"article": a["key"], "title": a["title"],
                            "section": s["num"], "text": s["text"], "url": a["url"]}
    raise HTTPException(404, "provision not found")


@app.get("/api/evidence/{evidence_id:path}")
def evidence(evidence_id: str):
    rec = corpus().get(evidence_id)
    if not rec:
        raise HTTPException(404, "evidence record not found")
    return rec.model_dump()


@app.get("/api/memo/demo")
def demo_memo():
    path = DATA_DIR / "memo_art1_sec17.json"
    if not path.exists():
        raise HTTPException(404, "demo memo not built yet — run: uv run python -m app.pipeline")
    return json.loads(path.read_text())


_prior = None


def prior_constitutions():
    global _prior
    if _prior is None:
        _prior = json.loads((DATA_DIR / "prior_constitutions.json").read_text())
    return _prior


# covers "SEC. 9.", "SECTION XVI." (1869), "Section 4", "ART. 12." (1827),
# and the 1836 Declaration of Rights' ordinal clauses ("Seventh.")
_SEC_MARK = re.compile(
    r"\b(?:(?:SEC(?:TION)?|Section|ART)\.?\s+(\d+[a-z]?|[IVXL]+\b)|"
    r"(First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|Ninth|Tenth|Eleventh|"
    r"Twelfth|Thirteenth|Fourteenth|Fifteenth|Sixteenth|Seventeenth|Eighteenth|"
    r"Nineteenth|Twentieth|Twenty-\w+)\.)")

_ORDINALS = {
    "first": "1", "second": "2", "third": "3", "fourth": "4", "fifth": "5",
    "sixth": "6", "seventh": "7", "eighth": "8", "ninth": "9", "tenth": "10",
    "eleventh": "11", "twelfth": "12", "thirteenth": "13", "fourteenth": "14",
    "fifteenth": "15", "sixteenth": "16", "seventeenth": "17", "eighteenth": "18",
    "nineteenth": "19", "twentieth": "20",
}


def _nearest_section(text: str, pos: int) -> str | None:
    """Number of the last 'SEC. n.' (or 1836-style ordinal clause) before pos."""
    last = None
    for m in _SEC_MARK.finditer(text, 0, pos):
        last = m
    if last is None:
        return None
    if last.group(1):
        return _roman_to_arabic(last.group(1))
    word = last.group(2).lower()
    return _ORDINALS.get(word, last.group(2))


def _roman_to_arabic(s: str) -> str:
    if not re.fullmatch(r"[IVXL]+", s):
        return s
    vals = {"I": 1, "V": 5, "X": 10, "L": 50}
    total = 0
    for a, b in zip(s, s[1:] + " "):
        total += -vals[a] if b in vals and vals[a] < vals[b] else vals[a]
    return str(total)


@app.get("/api/prior")
def prior(phrase: str):
    """Which of the six pre-1876 Texas constitutions contain this exact phrase."""
    needle = re.sub(r"\s+", " ", phrase).strip().lower()
    if len(needle) < 4:
        raise HTTPException(400, "phrase too short")
    results = []
    for ed in prior_constitutions()["editions"]:
        locs = []
        for page in ed["pages"]:
            i = page["text"].lower().find(needle)
            if i < 0:
                continue
            sec = _nearest_section(page["text"], i)
            locs.append({"label": page["label"], "section": sec, "url": page["url"]})
        results.append({"year": ed["year"], "name": ed["name"], "url": ed["url"],
                        "found": bool(locs), "locations": locs})
    return {"phrase": phrase, "editions": results}


class TermsRequest(BaseModel):
    phrase: str
    section_context: str = ""


@app.post("/api/research/terms")
def research_terms(req: TermsRequest):
    """LLM era-expansion of a selected phrase into extra search terms."""
    exp = expand_terms(req.phrase, req.section_context)
    return {"phrase": req.phrase, "terms": exp.terms, "rationale": exp.rationale}


@app.post("/api/research/define")
def research_define(req: TermsRequest):
    """Plain-language definition of the selected phrase (short + extended)."""
    d = define_phrase(req.phrase, req.section_context)
    return {"phrase": req.phrase, "short": d.short, "extended": d.extended}


@app.get("/api/search")
def search(terms: str):
    """Keyword concordance over the corpus. `terms` = pipe-separated list."""
    term_list = [t for t in terms.split("|") if t.strip()]
    if not term_list:
        raise HTTPException(400, "no search terms")
    grouped = concordance(corpus(), term_list)
    return {k: [h.model_dump() for h in v] for k, v in grouped.items()}


class MemoRequest(BaseModel):
    question: str
    terms: list[str]


@app.post("/api/memo")
def memo(req: MemoRequest):
    m = build_memo(req.question, req.terms)
    return m.model_dump()


app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")
