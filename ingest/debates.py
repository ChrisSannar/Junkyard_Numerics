"""McKay Debates (1875 Texas Constitutional Convention) ingest from Tarlton.

The McKay compilation PDFs have an excellent text layer (1930 typeset).
We download each day's PDF, pdftotext it, and store one EvidenceRecord per
PDF page so pinpoint cites resolve to a specific page of a specific day.

Usage:
    uv run python -m ingest.debates            # download + extract all 65 days
    uv run python -m ingest.debates --filter damag   # only keep pages matching a term
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx

from app.schema import EvidenceRecord, Locator, SourceKind

INDEX_URL = "https://tarlton.law.utexas.edu/constitutions/texas-1876-en/debates"
HEADERS = {"User-Agent": "Mozilla/5.0 originalism-searcher-hackathon"}
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "raw" / "debates"
CORPUS_FILE = DATA_DIR / "corpus" / "debates.jsonl"


def list_pdf_urls(client: httpx.Client) -> list[str]:
    html = client.get(INDEX_URL, headers=HEADERS, timeout=60).text
    urls = sorted(set(re.findall(r"https://tarltonapps[^\"]+debates1875[^\"]+\.pdf", html)))
    return urls


def download(client: httpx.Client, url: str, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        return
    resp = client.get(url, headers=HEADERS, timeout=120)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    time.sleep(1.0)


def pdf_pages(pdf: Path) -> list[str]:
    """Extract text per page (pdftotext with page breaks as form feeds)."""
    out = subprocess.run(
        ["pdftotext", "-layout", str(pdf), "-"],
        capture_output=True, text=True, check=True,
    ).stdout
    return out.split("\f")


def date_from_name(name: str) -> str:
    # 1875_09_22to23_dbt.pdf -> 1875-09-22
    m = re.match(r"(\d{4})_(\d{2})_(\d{2})", name)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else "1875"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--filter", default=None,
                    help="only keep pages whose text matches this regex (case-insensitive)")
    args = ap.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    CORPUS_FILE.parent.mkdir(parents=True, exist_ok=True)

    records: list[EvidenceRecord] = []
    with httpx.Client(follow_redirects=True) as client:
        urls = list_pdf_urls(client)
        print(f"{len(urls)} debate PDFs listed")
        for url in urls:
            name = url.rsplit("/", 1)[-1]
            dest = RAW_DIR / name
            try:
                download(client, url, dest)
            except httpx.HTTPError as e:
                print(f"  skip {name}: {e}", file=sys.stderr)
                continue
            date = date_from_name(name)
            for i, page_text in enumerate(pdf_pages(dest), start=1):
                text = page_text.strip()
                if len(text) < 100:
                    continue
                if args.filter and not re.search(args.filter, text, re.I):
                    continue
                records.append(EvidenceRecord(
                    id=f"debates:{name.removesuffix('.pdf')}:p{i}",
                    source_kind=SourceKind.CONVENTION_DEBATE,
                    source_name="McKay, Debates in the Texas Constitutional Convention of 1875",
                    date=date,
                    locator=Locator(url=url, page=str(i),
                                    detail=f"PDF page {i} of {name}"),
                    text=text,
                    query_matched=[args.filter] if args.filter else [],
                ))
            print(f"  {name}: corpus now {len(records)} pages")

    with CORPUS_FILE.open("w") as f:
        for r in records:
            f.write(r.model_dump_json() + "\n")
    print(f"done: {len(records)} debate pages in {CORPUS_FILE}")


if __name__ == "__main__":
    main()
