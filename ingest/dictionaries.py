"""Era-dictionary ingest: Bouvier's Law Dictionary (1880 printing) and
Webster's (1864-base text) from Internet Archive djvu.txt files.

Full dictionary parsing of 3-column OCR is a rabbit hole; instead we extract
the text around specific ALL-CAPS headwords we care about, one EvidenceRecord
per (dictionary, headword) hit. Good enough for pinpoint-cited definitions.

Prereq: data/raw/bouvier.txt and data/raw/webster.txt downloaded (see docs/SOURCES.md).

Usage:
    uv run python -m ingest.dictionaries
"""

from __future__ import annotations

import re
from pathlib import Path

from app.schema import EvidenceRecord, Locator, SourceKind

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CORPUS_FILE = DATA_DIR / "corpus" / "dictionaries.jsonl"

# §17 terms. Headword regexes are matched at line start in the OCR.
HEADWORDS = [
    "DAMAGE", "DAMAGES", "DAMAGED GOODS", "DAMNUM ABSQUE INJURIA",
    "EMINENT DOMAIN", "COMPENSATION", "PUBLIC USE", "TAKING", "DESTROY",
    "CONSEQUENTIAL DAMAGES",
]

SOURCES = {
    "bouvier": {
        "file": DATA_DIR / "raw" / "bouvier.txt",
        "name": "Bouvier's Law Dictionary (14th ed., 1880 printing)",
        "url": "https://archive.org/details/lawdictionaryada01bouvuoft",
    },
    "webster": {
        "file": DATA_DIR / "raw" / "webster.txt",
        "name": "Webster's American Dictionary (1864-base text)",
        "url": "https://archive.org/details/webstersinternat00port",
    },
}

CONTEXT_LINES = 40  # lines of entry text to capture after the headword


def _norm(s: str) -> str:
    # OCR renders spaces between letters inconsistently; collapse runs of spaces
    return re.sub(r"\s+", " ", s).strip()


def extract(source_key: str) -> list[EvidenceRecord]:
    src = SOURCES[source_key]
    if not src["file"].exists():
        print(f"missing {src['file']} — download it first (docs/SOURCES.md)")
        return []
    lines = src["file"].read_text(errors="replace").splitlines()
    records: list[EvidenceRecord] = []
    for hw in HEADWORDS:
        if source_key == "webster":
            # Webster headwords: Title-case with syllable apostrophes at line
            # start, e.g. "Dam'age (dam'aj ; 48), n."
            word = hw.split()[0]
            pat = re.compile(
                r"^\s{0,3}" + r"['‘’]?".join(re.escape(c) for c in word.capitalize())
                + r"['‘’]?\s*[(,]"
            )
        else:
            # Bouvier entries are typeset in CAPS at line start.
            pat = None
        for i, line in enumerate(lines):
            if pat is not None:
                if not pat.match(line):
                    continue
            else:
                head = _norm(line)
                if not head.startswith(hw):
                    continue
                # reject mid-word matches like DAMAGES when looking for DAMAGE
                rest = head[len(hw):]
                if rest[:1].isalpha():
                    continue
            chunk = "\n".join(lines[i:i + CONTEXT_LINES])
            records.append(EvidenceRecord(
                id=f"dict:{source_key}:{hw.lower().replace(' ', '-')}:l{i+1}",
                source_kind=SourceKind.DICTIONARY,
                source_name=src["name"],
                date="1880" if source_key == "bouvier" else "1864",
                locator=Locator(url=src["url"], detail=f"headword {hw}, djvu.txt line {i+1}"),
                text=_norm(chunk)[:4000],
                query_matched=[hw],
                ocr_quality_note="OCR of multi-column dictionary; verify against scan",
            ))
    return records


def main() -> None:
    CORPUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    records: list[EvidenceRecord] = []
    for key in SOURCES:
        recs = extract(key)
        print(f"{key}: {len(recs)} headword hits")
        records.extend(recs)
    with CORPUS_FILE.open("w") as f:
        for r in records:
            f.write(r.model_dump_json() + "\n")
    print(f"done: {len(records)} dictionary records in {CORPUS_FILE}")


if __name__ == "__main__":
    main()
