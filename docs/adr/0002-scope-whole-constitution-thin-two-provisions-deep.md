# ADR-0002: Whole constitution presentable; 1–2 provisions deep

Status: accepted
Date: 2026-07-03

## Context

Hackathon time is fixed. Options were: one provision deep, whole constitution shallow, or open-ended legal Q&A.

## Decision

- Ingest and index the **entire 1876 Texas Constitution** so any provision can be browsed and gets at least a thin, uniform treatment (text, structure, whatever evidence retrieval returns).
- Build the **full presentation-grade pipeline for 1–2 "deep provisions"**, chosen for evidentiary richness and demo resonance.
- Output artifact: a **research memo with pinpoint citations** for an appellate-lawyer user. Every claim links to a viewable primary source. The tool retrieves, organizes, and drafts memo prose — it does not draft brief/argument prose.

## Consequences

- The deep provisions define "done" for the demo; the thin path defines "done" for the product shell.
- Deep-provision choice is a real decision (see ADR-0003 when made) — it should be a clause with rich 1874–1878 newspaper discussion and modern litigation relevance.
- Pinpoint-citation requirement drives the architecture: retrieval must preserve source locators (paper/date/page) end-to-end, and the memo renderer must link claims to source views.
