"""1876 Texas Constitution full text, structured by article/section, from
Tarlton's texas-1876-en pages. Powers the browse (thin) path (ADR-0002).

Output: data/constitution.json  {articles: [{key, title, url, sections: [{num, text}]}]}

Usage:
    uv run python -m ingest.constitution
"""

from __future__ import annotations

import html as htmllib
import json
import re
import time
from pathlib import Path

import httpx

BASE = "https://tarlton.law.utexas.edu/constitutions/texas-1876-en"
HEADERS = {"User-Agent": "Mozilla/5.0 originalism-searcher-hackathon"}
OUT = Path(__file__).resolve().parent.parent / "data" / "constitution.json"

# Roman numeral per Tarlton slug ordering
ARTICLE_PAGES = [
    ("I", "Bill of Rights", "preamble-article-1-bill-rights"),
    ("II", "Powers of Government", "article-2-powers-government"),
    ("III", "Legislative Department", "article-3-legislative-department"),
    ("IV", "Executive Department", "article-4-executive-department"),
    ("V", "Judicial Department", "article-5-judicial-department"),
    ("VI", "Suffrage", "article-6-suffrage"),
    ("VII", "Education — Public Free Schools", "article-7-education-public-free-schools"),
    ("VIII", "Taxation and Revenue", "article-8-taxation-revenue"),
    ("IX", "Counties", "article-9-counties"),
    ("X", "Railroads", "article-10-railroads"),
    ("XI", "Municipal Corporations", "article-11-municipal-corporations"),
    ("XII", "Private Companies", "article-12-private-companies"),
    ("XIII", "Spanish and Mexican Land Titles", "article-13-spanish-mexican-land-titles"),
    ("XIV", "Public Lands and Land Office", "article-14-public-lands-land-office"),
    ("XV", "Impeachment", "article-15-impeachment"),
    ("XVI", "General Provisions", "article-16-general-provisions"),
    ("XVII", "Mode of Amending the Constitution", "article-17-mode-amending-constitution-state"),
]

SEC_RE = re.compile(r"SEC(?:TION)?\.?\s+(\d+[a-z]?)\.\s*", re.I)


def page_sections(html: str) -> list[dict]:
    txt = re.sub(r"<[^>]+>", " ", html)
    txt = htmllib.unescape(txt)
    txt = re.sub(r"\s+", " ", txt)
    parts = SEC_RE.split(txt)
    sections = []
    # parts = [pre, num1, body1, num2, body2, ...]
    for num, body in zip(parts[1::2], parts[2::2]):
        # trim trailing site chrome from the final section
        body = re.split(r"(Property of Tarlton|Back to top|©)", body)[0]
        body = body.strip()
        if len(body) > 20:
            sections.append({"num": num, "text": body[:8000]})
    return sections


def main() -> None:
    articles = []
    with httpx.Client(follow_redirects=True) as client:
        for roman, title, slug in ARTICLE_PAGES:
            url = f"{BASE}/{slug}"
            resp = client.get(url, headers=HEADERS, timeout=60)
            resp.raise_for_status()
            secs = page_sections(resp.text)
            articles.append({"key": roman, "title": title, "url": url, "sections": secs})
            print(f"Art. {roman} ({title}): {len(secs)} sections")
            time.sleep(1.0)
    OUT.write_text(json.dumps({"articles": articles}, indent=1))
    print(f"done: {OUT}")


if __name__ == "__main__":
    main()
