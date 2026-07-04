# Verified data sources (checked live 2026-07-03)

Ranked by ease of integration. All access patterns below were verified with real requests.

## 1. Chronicling America (Library of Congress) — newspaper usage evidence
- Old `chroniclingamerica.loc.gov` API retired 2025 → use the **loc.gov JSON API** (no key).
- **Throttle:** ~1 req / 3–5 s with retries + a User-Agent header, or you get 403s.
- Search **must** include `searchType=advanced` or filters are silently ignored:
  `https://www.loc.gov/collections/chronicling-america/?dl=page&location_state=texas&start_date=1875-09-01&end_date=1876-02-29&qs=QUERY&searchType=advanced&fo=json&c=100`
- OCR text: page JSON (`https://www.loc.gov/resource/{lccn}/{date}/ed-1/?sp=1&fo=json`) → `resources[0].fulltext_file` → JSON with `full_text`. Word coordinates available.
- TX 1874–1878: **10,403 pages / 8 titles** — Dallas Daily Herald (5,474), Freie Presse (German, 1,516), Waco Daily Examiner (1,142), Weekly Democratic Statesman–Austin (846), Dallas Weekly Herald (709), San Marcos Free Press (460), Brenham Weekly Banner (248), San Saba News (8). **No Galveston Daily News.**

## 2. Era dictionaries (Internet Archive) — semantic-meaning reference corpus
- Pattern: `https://archive.org/download/{id}/{id}_djvu.txt` (no auth).
- **Bouvier's Law Dictionary (1880 printing):** id `lawdictionaryada01bouvuoft`. Avoid the 1914 Rawle revision (wrong era).
- **Webster's (1864-base text, 1898 printing):** id `webstersinternat00port`. Good enough; the true 1873 printing is image-only on HathiTrust.
- Real work: parsing entries out of 3-column OCR.

## 3. Tarlton Law Library — convention record
- **McKay Debates (1875), 65 PDFs, EXCELLENT text layer** (clean 1930 typeset) — our machine-readable convention source:
  `https://tarltonapps.law.utexas.edu/imgs/constitutions/files/debates1875/1875_09_22to23_dbt.pdf`
- **Convention Journal PDFs: near-garbage OCR** — treat as image-tier / link-only:
  `https://tarltonapps.law.utexas.edu/imgs/constitutions/files/journals1875/1875_09_06_jnl.pdf`
- Index pages: `https://tarlton.law.utexas.edu/constitutions/texas-1876-en/debates` (and `/journals`). Text is public domain.

## 4. Portal to Texas History (UNT) — the deep Texas newspaper corpus
- Free, no key. **Landmine:** the HTML `/search/` endpoint sits behind an ALTCHA bot wall for scripts; the **OpenSearch endpoint bypasses it**:
  `https://texashistory.unt.edu/search/opensearch/?q=%22QUERY%22&t=fulltext&format=json`
  `fq=` facet filters appear ignored — filter client-side on `dc:date`.
- Per-page OCR via IIIF annotations (word-level, with xywh coords):
  `https://texashistory.unt.edu/ark:/67531/{ark}/m1/{page}/annotations/ocr/`
- ~17,112 newspaper items 1870–1879 — much broader than ChronAm (likely incl. Galveston papers).

## 5. Gammel's Laws of Texas (on the Portal) — era statutes for tradition evidence
- Collection: `https://texashistory.unt.edu/explore/collections/GLT/`; **Vol 8 = laws of 1873–1879**. Same OCR-annotation endpoint works; direct ARK/IIIF URLs bypass the bot wall.

## Priority for the build
1. ChronAm API (newspapers, easiest, throttled)
2. McKay Debates PDFs via `pdftotext` (convention floor evidence)
3. Bouvier + Webster djvu.txt (definitions)
4. Portal OpenSearch + OCR annotations (broader newspapers — if time allows)
5. Gammel's Vol 8 (statutes/tradition — if time allows)
