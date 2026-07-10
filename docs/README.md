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

All architecture docs live in [`docs/architecture/`](architecture/).

| Doc | What it covers |
|---|---|
| [`architecture/GRAPH.md`](architecture/GRAPH.md) | LangGraph compiled state machine — every node, edge, and conditional |
| [`architecture/agentic-pipeline.md`](architecture/agentic-pipeline.md) | **Phase 11** — Planner · Orchestrator · Workers · Tools · Skills architecture, audit events, extension playbook |
| [`architecture/design-rationale.md`](architecture/design-rationale.md) | Why the topology is six separate nodes, not branching logic — design intent and MUST/MUST-NOT contracts |
| [`architecture/ingestion.md`](architecture/ingestion.md) | Phase 6 ingestion & chunking pipeline — design decisions and tuning knobs |
| [`architecture/high_level_architecture.png`](architecture/high_level_architecture.png) | System overview diagram |

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

---

## Wiki

The [`docs/wiki/`](wiki/) folder is the GitHub Wiki source of truth — sync'd to the repo wiki on every merge to `dev`. Start at [`wiki/Home.md`](wiki/Home.md).
