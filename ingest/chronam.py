"""Chronicling America ingest via the loc.gov JSON API (see docs/SOURCES.md).

Gotchas (verified live):
- use q= — the documented qs= param redirect-loops as of 2026-07;
- searchType=advanced is still required or date/state filters are ignored;
- text-services JSON nests under a segment-path key: {seg: {full_text, height, width}};
- search results already carry image_url (list of sizes);
- throttle ~1 req/4s with retries or you get 403s; send a User-Agent.

Usage:
    uv run python -m ingest.chronam --terms-file ingest/terms_art1_sec17.txt
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import httpx

from app.schema import EvidenceRecord, Locator, SourceKind

BASE = "https://www.loc.gov/collections/chronicling-america/"
HEADERS = {"User-Agent": "Mozilla/5.0 originalism-searcher-hackathon"}
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CORPUS_FILE = DATA_DIR / "corpus" / "chronam.jsonl"

START_DATE = "1874-01-01"
END_DATE = "1878-12-31"
THROTTLE_S = 4.0


def _get(client: httpx.Client, url: str, params: dict | None = None, tries: int = 5) -> dict:
    for attempt in range(tries):
        try:
            resp = client.get(url, params=params, headers=HEADERS, timeout=60)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (403, 429, 500, 502, 503, 520, 521, 522, 524):
                wait = THROTTLE_S * (attempt + 2)
                print(f"  {resp.status_code} — backing off {wait:.0f}s", file=sys.stderr)
                time.sleep(wait)
                continue
            resp.raise_for_status()
        except (httpx.TransportError, ValueError) as e:
            print(f"  error {e} — retrying", file=sys.stderr)
            time.sleep(THROTTLE_S * (attempt + 2))
    raise RuntimeError(f"gave up on {url}")


def search_pages(client: httpx.Client, term: str, max_pages: int = 3) -> list[dict]:
    """Search TX newspaper pages 1874-1878 for a term. Returns raw result dicts."""
    results: list[dict] = []
    for page_no in range(1, max_pages + 1):
        params = {
            "q": term,
            "dl": "page",
            "location_state": "texas",
            "start_date": START_DATE,
            "end_date": END_DATE,
            "searchType": "advanced",
            "fo": "json",
            "c": 100,
            "sp": page_no,
        }
        data = _get(client, BASE, params)
        batch = data.get("results", [])
        results.extend(batch)
        total = data.get("pagination", {}).get("total", 0)
        print(f"  '{term}' page {page_no}: {len(batch)} results (total {total})")
        if page_no * 100 >= total or not batch:
            break
        time.sleep(THROTTLE_S)
    return results


def fetch_full_text(client: httpx.Client, item_url: str) -> str | None:
    """Given a result's resource URL, return the page OCR text."""
    # item_url looks like https://www.loc.gov/resource/{lccn}/{date}/ed-1/?sp=N
    data = _get(client, item_url, {"fo": "json"})
    resources = data.get("resources") or [{}]
    ft_url = resources[0].get("fulltext_file")
    if not ft_url:
        return None
    time.sleep(THROTTLE_S)
    ft = _get(client, ft_url)
    # {segment_path: {full_text, height, width}} (verified)
    for v in ft.values():
        if isinstance(v, dict) and "full_text" in v:
            return v["full_text"]
    return None


def _stable_id(raw: dict) -> str:
    rid = (raw.get("id") or "").rstrip("/")
    return "chronam:" + rid.split("loc.gov/")[-1].replace("/", ":").replace("?", ":")


def result_to_record(raw: dict, text: str, term: str) -> EvidenceRecord:
    title = raw.get("partof_title") or raw.get("title") or "unknown paper"
    if isinstance(title, list):
        title = title[0]
    image_url = None
    imgs = raw.get("image_url") or []
    if imgs:
        image_url = imgs[-1]  # largest size last
        if image_url.startswith("//"):
            image_url = "https:" + image_url
    return EvidenceRecord(
        id=_stable_id(raw),
        source_kind=SourceKind.NEWSPAPER,
        source_name=str(title).title(),
        date=raw.get("date"),
        locator=Locator(url=raw.get("url") or raw.get("id", ""), image_url=image_url),
        text=text,
        query_matched=[term],
        ocr_quality_note="raw 1870s archive OCR; verify against page image",
    )


def load_corpus() -> dict[str, EvidenceRecord]:
    seen: dict[str, EvidenceRecord] = {}
    if CORPUS_FILE.exists():
        for line in CORPUS_FILE.read_text().splitlines():
            r = EvidenceRecord.model_validate_json(line)
            seen[r.id] = r
    return seen


def save_corpus(seen: dict[str, EvidenceRecord]) -> None:
    CORPUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with CORPUS_FILE.open("w") as f:
        for r in seen.values():
            f.write(r.model_dump_json() + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--terms-file", required=True)
    ap.add_argument("--max-search-pages", type=int, default=2)
    ap.add_argument("--max-fetch-per-term", type=int, default=20,
                    help="cap full-text fetches per term (each costs ~8s of throttle)")
    args = ap.parse_args()

    terms = [t.strip() for t in Path(args.terms_file).read_text().splitlines()
             if t.strip() and not t.startswith("#")]

    seen = load_corpus()
    if seen:
        print(f"resuming: {len(seen)} records already in corpus")

    with httpx.Client(follow_redirects=True) as client:
        for term in terms:
            print(f"searching: {term!r}")
            raws = search_pages(client, term, args.max_search_pages)
            time.sleep(THROTTLE_S)
            fetched = 0
            for raw in raws:
                rid = _stable_id(raw)
                if rid in seen:
                    if term not in seen[rid].query_matched:
                        seen[rid].query_matched.append(term)
                    continue
                if fetched >= args.max_fetch_per_term:
                    break
                item_url = raw.get("id")
                if not item_url:
                    continue
                try:
                    text = fetch_full_text(client, item_url)
                except (RuntimeError, httpx.HTTPError) as e:
                    print(f"  skip {item_url}: {e}", file=sys.stderr)
                    time.sleep(THROTTLE_S)
                    continue
                if not text:
                    continue
                seen[rid] = result_to_record(raw, text, term)
                fetched += 1
                print(f"  + {rid} ({len(text)} chars)")
                time.sleep(THROTTLE_S)
            save_corpus(seen)
            print(f"checkpoint: {len(seen)} records total")

    print(f"done: {len(seen)} records in {CORPUS_FILE}")


if __name__ == "__main__":
    main()
