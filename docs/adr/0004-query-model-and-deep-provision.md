# ADR-0004: Interpretive-question query model; both-ways memos; deep provision = Art. I, § 17

Status: accepted
Date: 2026-07-03

## Context

The system needed a unit of work (whole-provision dossier vs. focused question), a stance on adverse evidence, and a concrete deep provision to script the demo around.

## Decision

1. **Unit of work = an interpretive question anchored to a provision.** Input: provision (article + section) + the proposition at issue + optionally the specific disputed terms. Retrieval targets the contested terms; the memo answers the question.
2. **Memos assess the question both ways.** Counter-evidence is reported alongside supporting evidence ("here's what opposing counsel will find"). One-sided advocacy memos are out of scope by design.
3. **Deep provision: Art. I, § 17 (takings — "taken, damaged or destroyed for public use").** The 1876 text famously added "damaged or destroyed" beyond the federal "taken"; what "damaged" meant to an 1876 reader is live in modern Texas inverse-condemnation litigation (flooding, road access, utilities). Demo interpretive question (working): *"Did 'damaged' in Art. I, § 17 encompass consequential injury to property (access, flooding) without physical appropriation?"*

## Consequences

- Whole-constitution thin path (ADR-0002) still exists: browse any provision, see its text + raw retrieval. The deep pipeline is built and tuned against § 17.
- Prompting must produce a claims-both-ways schema, each claim tagged supporting/adverse/neutral and referencing evidence IDs (ADR-0003).
- Retrieval terms for the demo: "damaged," "damage to property," "public use," "compensation," "internal improvements," railroad right-of-way disputes 1874–1878.
