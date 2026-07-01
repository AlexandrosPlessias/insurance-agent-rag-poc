# Documentation Index

This folder contains the in-depth reference docs for the Insurance Agent RAG PoC.
Start with the root-level quick-reads ([README.md](../README.md), [SETUP.md](../SETUP.md),
[USAGE.md](../USAGE.md)) then drill down here for architecture and design details.

---

## Operations

Root-level guides — these are the day-to-day documents most readers need.

| Doc | What it covers |
|---|---|
| [`../README.md`](../README.md) | Project overview, key features, full phase roadmap |
| [`../SETUP.md`](../SETUP.md) | First-time WSL2 install, bootstrap, config, verification |
| [`../USAGE.md`](../USAGE.md) | Running the stack, ingesting PDFs, observability, troubleshooting |

---

## Architecture

| Doc | What it covers |
|---|---|
| [`GRAPH.md`](architecture/GRAPH.md) | LangGraph compiled state machine — every node, edge, and conditional |
| [`agentic.md`](agentic.md) | **Phase 11** — Planner · Orchestrator · Workers · Tools · Skills architecture, audit events, extension playbook |
| [`ingestion.md`](ingestion.md) | Phase 6 ingestion & chunking pipeline — design decisions and tuning knobs |
| [`agentic.md § 10`](agentic.md#10--legacy-phase-110-contracts) | Phase 1–10 per-node MUST/MUST-NOT contracts (appended to `agentic.md`) |

---

## Strategic Vision

| Doc | What it covers |
|---|---|
| [`insurance_rag_strategic_roadmap.md`](insurance_rag_strategic_roadmap.md) | Full enterprise Azure production architecture vision across 5 pillars. § 5 maps each strategic component to the PoC phase that validates it. |

---

## Presentation

| Doc | What it covers |
|---|---|
| [`presentation/deck.md`](presentation/deck.md) | 16-slide stakeholder deck — Markdown source of truth for the PPTX |
| [`presentation/README.md`](presentation/README.md) | Screenshot-capture runbook for updating deck slides |
