"""The six Texas constitutions preceding 1876, full text from Tarlton.

Powers the "Prior Texas Constitutions" lineage lookup: given a phrase selected
in the 1876 reader, report (without elaboration) which earlier constitutions
contain that phrase verbatim.

Note: the "Coahuila y Tejas" state constitution is dated 1827 at Tarlton
(1824 is the *federal* Mexican constitution).

Output: data/prior_constitutions.json
  {editions: [{year, name, url, pages: [{label, url, text}]}]}

Usage:
    uv run python -m ingest.prior_constitutions
"""

from __future__ import annotations

import html as htmllib
import json
import re
import time
from pathlib import Path

import httpx

BASE = "https://tarlton.law.utexas.edu/constitutions"
HEADERS = {"User-Agent": "Mozilla/5.0 originalism-searcher-hackathon"}
OUT = Path(__file__).resolve().parent.parent / "data" / "prior_constitutions.json"

# (year, display name, landing url, tarlton dir, [(label, slug), ...])
EDITIONS = [
    ("1827", "Constitution of Coahuila y Tejas (1827)",
     f"{BASE}/constitution-state-coahuila-texas-1827", "coahuila-texas-1827-eng", [
        ("Preamble & Preliminary Provisions", "preamble-preliminary-provisions"),
        ("Title I (Legislative Power)", "title-1-legislative-power"),
        ("Title II (Executive Power)", "title-2-executive-power"),
        ("Title III (Judicial Power)", "title-3-judicial-power"),
        ("Title IV (State Revenue)", "title-4-state-revenue"),
        ("Title V (Civic Militia)", "title-5-civic-militia"),
        ("Title VI (Public Education)", "title-6-public-education"),
        ("Title VII (Observance of the Constitution)", "title-7-observance-constitution"),
    ]),
    ("1836", "Constitution of the Republic of Texas (1836)",
     f"{BASE}/republic-texas-1836", "republic-texas-1836", [
        ("Preamble & Art. I", "preamble-article-1-powers-governement"),
        ("Art. II (Legislative)", "article-2-legislative"),
        ("Art. III (Executive)", "article-3-executive"),
        ("Art. IV (Judicial)", "article-4-judicial"),
        ("Art. V (Oaths)", "article-5-oaths"),
        ("Art. VI (President)", "article-6-president-vice-president"),
        ("Schedule", "schedule"),
        ("General Provisions", "general-provisions"),
        ("Declaration of Rights", "declaration-rights"),
    ]),
    ("1845", "Constitution of Texas (1845)",
     f"{BASE}/constitution-texas-1845", "texas-1845-en", [
        ("Preamble & Art. I (Bill of Rights)", "preamble-article-1-bill-rights"),
        ("Art. II", "article-2-division-powers-government"),
        ("Art. III (Legislative)", "article-3-legislative-department"),
        ("Art. IV (Judicial)", "article-4-judicial-department"),
        ("Art. V (Executive)", "article-5-executive-department"),
        ("Art. VI (Militia)", "article-6-militia"),
        ("Art. VII (General Provisions)", "article-7-general-provisions"),
        ("Art. VIII (Slaves)", "article-8-slaves"),
        ("Art. IX (Impeachment)", "article-9-impeachment"),
        ("Art. X (Education)", "article-10-education"),
        ("Art. XI (Head Rights)", "article-11-head-rights"),
        ("Art. XII (Land Office)", "article-12-land-office"),
        ("Art. XIII (Schedule)", "article-13-schedule"),
    ]),
    ("1861", "Constitution of Texas (1861)",
     "https://tarlton.law.utexas.edu/c.php?g=801151", "texas-1861", [
        ("Preamble & Art. I (Bill of Rights)", "preamble-article-1-bill-rights"),
        ("Art. II", "article-2-division-powers-government"),
        ("Art. III (Legislative)", "article-3-legislative-department"),
        ("Art. IV (Judicial)", "article-4-judicial-department"),
        ("Art. V (Executive)", "article-5-executive-department"),
        ("Art. VI (Militia)", "article-6-militia"),
        ("Art. VII (General Provisions)", "article-7-general-provisions"),
        ("Art. VIII (Slaves)", "article-8-slaves"),
        ("Art. IX (Impeachment)", "article-9-impeachment"),
        ("Art. X (Education)", "article-10-education"),
        ("Art. XI", "article-11"),
        ("Art. XII (Land Office)", "article-12-land-office"),
        ("Art. XIII (Schedule)", "article-13-schedule"),
    ]),
    ("1866", "Constitution of Texas (1866)",
     "https://tarlton.law.utexas.edu/c.php?g=810765", "texas-1866", [
        ("Preamble & Art. I (Bill of Rights)", "preamble-article-1-bill-rights"),
        ("Art. II", "article-2-division-powers-government"),
        ("Art. III (Legislative)", "article-3-legislative-department"),
        ("Art. IV (Judicial)", "article-4-judicial-department"),
        ("Art. V (Executive)", "article-5-executive-department"),
        ("Art. VI (Militia)", "article-6-militia"),
        ("Art. VII (General Provisions)", "article-7-general-provisions"),
        ("Art. VIII (Freedmen)", "article-8-freedmen"),
        ("Art. IX (Impeachment)", "article-9-impeachment"),
        ("Art. X (Education)", "article-10-education"),
        ("Art. XI (Head Rights)", "article-11-head-rights"),
        ("Art. XII (Land Office)", "article-12-land-office"),
    ]),
    ("1869", "Constitution of Texas (1869)",
     f"{BASE}/constitution-texas-1869", "texas-1869", [
        ("Preamble & Art. I (Bill of Rights)", "preamble-article-1-bill-rights"),
        ("Art. II", "article-2-division-powers-government"),
        ("Art. III (Legislative)", "article-3-legislative-department"),
        ("Art. IV (Executive)", "article-4-executive-department"),
        ("Art. V (Judicial)", "article-5-judicial-department"),
        ("Art. VI (Right of Suffrage)", "article-6-right-suffrage"),
        ("Art. VII (Militia)", "article-7-militia"),
        ("Art. VIII (Impeachment)", "article-8-impeachment"),
        ("Art. IX (Public Schools)", "article-9-public-schools"),
        ("Art. X (Land Office)", "article-10-land-office"),
        ("Art. XI (Immigration)", "article-11-immigration"),
        ("Art. XII (General Provisions)", "article-12-general-provisions"),
    ]),
]


def page_text(html: str) -> str:
    """Clean page body text (same hygiene as ingest.constitution)."""
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    html = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    txt = re.sub(r"<[^>]+>", " ", html)
    txt = htmllib.unescape(txt)
    txt = re.sub(r"\s+", " ", txt)
    # the guide body starts after the last prev/next breadcrumb ("<< Previous: ..."
    # / "Next: ... >>"); everything before it is sidebar/nav chrome
    crumbs = list(re.finditer(r"(<< Previous:[^<>]*|Next:[^<>]*>>)", txt))
    if crumbs:
        txt = txt[crumbs[-1].end():].lstrip("> ")
    txt = re.split(
        r"(Property of Tarlton|Back to top|©|\(Transcription, errors in original"
        r"|Last Updated:|Print Page|Login to LibApps)", txt)[0]
    return txt.strip()


def main() -> None:
    editions = []
    with httpx.Client(follow_redirects=True) as client:
        for year, name, landing, tdir, pages in EDITIONS:
            out_pages = []
            for label, slug in pages:
                url = f"{BASE}/{tdir}/{slug}"
                resp = client.get(url, headers=HEADERS, timeout=60)
                resp.raise_for_status()
                text = page_text(resp.text)
                out_pages.append({"label": label, "url": url, "text": text})
                print(f"{year} {label}: {len(text)} chars")
                time.sleep(0.8)
            editions.append({"year": year, "name": name, "url": landing,
                             "pages": out_pages})
    OUT.write_text(json.dumps({"editions": editions}, indent=1))
    print(f"done: {OUT}")


if __name__ == "__main__":
    main()
