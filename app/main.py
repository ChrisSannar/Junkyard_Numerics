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
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.pipeline import build_memo, load_corpus

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


class MemoRequest(BaseModel):
    question: str
    terms: list[str]


@app.post("/api/memo")
def memo(req: MemoRequest):
    m = build_memo(req.question, req.terms)
    return m.model_dump()


app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")
