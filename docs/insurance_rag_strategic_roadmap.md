# Enterprise Insurance AI — Strategic Architecture Vision

> **Context.** This document captures the full enterprise-grade architecture vision that
> informs the design decisions of the local PoC. The PoC (Phases 1–12) runs on a single
> WSL2 workstation with local Ollama models and validates the core patterns at reduced scale.
> A production deployment would replace the local components with Azure-hosted equivalents
> as described below.
>
> For the PoC implementation see the main [README.md](../README.md).
> Per-phase architecture docs live in [`docs/`](./).

---

## 1. Introduction

The Insurance AI assistant serves branch operators answering policy and KPI questions in real
time. The strategic vision is built on three pillars:

- **Regulatory compliance** — EU AI Act and GDPR alignment by design; all processing within
  EU geographic boundaries; immutable audit trail for every decision.
- **Auditability** — every agent decision logged with OTel trace correlation; tamper-evident
  audit DB queryable by compliance reviewers.
- **Agentic extensibility** — a Planner · Orchestrator · Workers · Skills backbone that grows
  from a single-intent assistant to a multi-channel autonomous workflow engine.

---

## 2. Enterprise Architecture Specification

### 2.1 Data Ingestion Pipeline

- **Regulatory Compliance & Sovereignty (RAI 1.0):** Absolute adherence to the EU AI Act and
  GDPR frameworks. All computing, tokenization, parsing, and storage must occur **strictly
  within EU geographic boundaries**.
- **Source Connectors (2.1.1):** Native automation connectors fetching data from Microsoft
  SharePoint, secure web endpoints, and direct User Interface file uploads.
- **Ingestion Type Constraints (2.1.2):** Standardised on unstructured and semi-structured
  **PDF** files for the initial implementation phase.
- **Historical Evolution Data & Versioning (2.1.3):** Permanent activation of **Azure Storage
  Blob Versioning** to retain snapshots of data evolution over time.
- **Processing Engine (2.1.4):**
    - **Raw Isolation Store:** Unaltered retention of incoming binaries.
    - **Advanced Extraction:** Convert doc to docx and xls to xlsx; use PyMuPDF for PDFs or
      Azure Document Intelligence (DI) for scanned documents (fallback: Content Understanding).
    - **Immutable Metadata Enrichment:** Deep tagging, timestamping, and enforcement of an
      **"Is Deleted" Soft-Delete Flag**.
    - **Retention Enforcement:** Strict systemic ban on physical deletion of data or preceding
      versions before a compliance threshold of **X years**.
- **DevOps Orchestration (2.1.5):** Dual execution paths:
    - Automated, time-triggered pipeline iteration executed via a **CI/CD — Cron Job**
      configuration.
    - Manual, ad-hoc pipeline execution triggered securely via the administrative UI.

---

### 2.2 Advanced Data Indexing Engine

- **Sovereign Data Storage (RAI 2.0):** Inverted index processing, embedding vectors, and
  semantic caches are confined fully within the European Economic Area (EEA).
- **Document-to-Chunk Level Summary Propagation (2.2.1):** Execution of custom cloud functions
  to synthesise high-level metadata and descriptive abstractive summaries for each document.
    - In-memory generation of a specific `documents_keywords_array`.
    - **Chunk-Level Injection:** Injecting parent document summaries and structural keywords
      directly into every child text chunk to prevent contextual isolation during retrieval.
- **Security Access Controls (2.2.2):** Granular evaluation and architectural provisioning for
  **Role-Based Access Control (RBAC) at the discrete Document level** to partition data access
  by organisational clearances.
- **Strict Structural Schema Declaration (2.2.3):**
    ```json
    {
      "title": "String",
      "description": "String",
      "chunk": "String",
      "vector": "Vector",
      "keywords": "Array of Strings",
      "user_group": "String (IAM mapping identifier)",
      "year": "Integer (Fiscal context)",
      "language": "String (ISO 639-1 format)",
      "document_category": "Array of Strings (Multi-class taxonomy)",
      "channel": "String",
      "ingestion_date_time": "ISO 8601 UTC Timestamp",
      "activation_date_time": "Date — extracted from first page of document; may be after creation date",
      "source_url": "String"
    }
    ```
    *Note: `activation_date_time` solves the "Pre-Activation Upload Dilemma" where guidelines
    are uploaded days before their legal enforcement date (e.g. uploaded Monday, effective
    Friday).*
- **Infrastructure-as-Code Automation (2.2.4):** Single-click provisioning scripts to define
  and unify Data Sources, Vector Index schemas, custom Cognitive Skillsets, and Azure Search
  Indexers.
- **Indexer Execution Lifecycles (2.2.5):** Dual-state scheduling via a persistent time-based
  Indexer Scheduler and direct, reactive Ad-Hoc Indexer invocation triggered automatically on
  completion of any Data Ingestion pipeline loop.

---

### 2.3 Answering API Back-End Architecture

- **Legal Governance & Audit Trail (RAI 3.0):** Mandatory automated record-keeping logs
  tracking lifecycle changes, privacy policies, and strict GDPR portability frameworks.
- **Real-Time Guardrails Subsystem (2.3.1):** Synchronous, intercepting middleware providing:
    - Heuristic and vector-based analysis for **Obfuscated Input** identification.
    - Dynamic structural syntax scanning to neutralise **Prompt Injection** threats.
    - In-line **PII Masking** utilising a stateless, zero-retention data transformation layer
      prior to LLM submission.
- **LLM Infrastructure Resilience (2.3.2):** Architectural abstractions mitigating **Model
  Churn** (seamless hot-swapping of foundation LLM versions), pinning execution environments to
  strict regional boundaries, and active runtime transaction token tracking for **Cost
  Estimation**.
- **Enterprise Integration Grid (2.3.3):** Out-of-the-box system orchestrators mapping:
    - Identity Access Management (IAM) permissions for internal user profiles.
    - Core CRM APIs parsing real-time Client Information portfolios.
    - Localisation microservices translating contextual data queries.
    - Transactional databases evaluating active Policy Contracts.
- **Ad-Hoc Asset Submissions (2.3.4):** Isolated API endpoints enabling real-time user-driven
  document uploads with sandboxed validation.
- **The Agentic Orchestration Backbone (2.3.5):**
    - **Orchestration Framework (2.3.5.1):** State-machine driven multi-agent framework
      utilising distinct execution boundaries, explicit custom tools, and skills.
    - **Agent Topography:**
        - **RAG Agent (2.3.5.2):** Dedicated retrieval engine leveraging hybrid search vectors,
          dense cross-encoders, question reformulation and multi-source aggregator tools.
        - **Talk-to-Your-Data Agent (2.3.5.3):** Conversational proxy interfacing with
          structured data schemas and long-term history records to output clean natural language
          prose.
        - **Report Generation Agent (2.3.5.4):** High-tier analysis engine accessing memory
          logs to execute internal Python data transformations. Leverages programmatic
          visualisation tools to convert pandas DataFrames into persistent images, routing
          outputs through a structural Formatter Tool.
        - **Validator Agent (2.3.5.5):** Checks for grounded answers, valid citations, and
          hallucinations; applies reputation guardrails at output.
    - **Memory Tiering (2.3.5.6):** Partitioned into ephemeral **Short-Term (Session) Memory**
      and persistent **Long-Term (Historical context) Memory**.
    - **Optimisation Hyper-Loops (2.3.5.7):** State tuning frameworks, contextual routing
      optimisation, structured programmatic error handling, and target fine-tuning
      configurations.
- **Observability, Tracing & Explanations (2.3.6):** Enterprise implementation of
  OpenTelemetry (OTel) paired with dedicated LLM monitoring solutions (**Langfuse**). This
  layer serves as the primary system of record for the critical question: *"Why did the model
  reason this way?"* It provides defensive forensic telemetry if an end-user files a formal
  complaint, charge, or legal indictment.
- **Audit Engine (2.3.7):** System-level immutable telemetry capture storing user execution
  traces, token consumption records, and guardrail mitigation incidents.
- **DevOps & CI/CD Pipelines (2.3.8):**
    - Infrastructure-as-Code (IaC) pipelines for complete cloud resource reproduction.
    - Immutable container deployment pipelines (AKS Build Container Image, Staged Progression
      to Non-Prod, Promotion to Prod, and automated instant Rollback).
    - Continuous integration Unit Testing suites.
    - Continuous LLM Evaluation and Regression pipelines to enforce generation quality bounds.

---

### 2.4 Front-End User Experience Design

- **Integration Topology (2.4.0):** Deep evaluation of existing internal user environments.
  Delivered primarily as an **embedded application widget** inside existing enterprise
  interfaces to mitigate portal fatigue.
- **Design Paradigm (2.4.1):** Implementation of a purposeful **"Soviet User Interface"**
  philosophy: uncompromised simplicity, low cognitive load, zero non-essential decorative
  complexity, and linear functional pathways.
- **Screen Layout Matrices:**
    - **Upload Portal (2.4.2):** Drag-and-drop secure file staging area with execution
      telemetry status tracking.
    - **Chat Interface (2.4.3):** Clean conversational thread view with strict compliance
      overlays:
        - **Source Citation (2.4.3.1):** Explicit global document visibility tags.
        - **Context Transparency (2.4.3.2):** High-fidelity UI breakdown displaying the
          verbatim source text chunks utilised in generation alongside their explicit **page
          numbers** for rapid compliance validation.
        - **Feedback Ingestion Loop (2.4.3.3):** Discrete user evaluation mechanism tracking
          a structured 1-to-5 star metric paired with an unconstrained open-text commentary
          box.
    - **Historical Log (2.4.4):** Interactive historical search ledger mapping previous
      conversational instances.
    - **Telemetry Dashboard (2.4.5):** Clean data representation displaying systemic KPIs and
      giving the user explicit visibility into their cached Short-Term and Long-Term memory
      footprints.
- **Frontend DevOps Automation (2.4.6):** Standardised multi-stage pipelines covering IaC
  validation, structural verification, production compilation, and automated rollback fallback
  triggers.

---

### 2.5 Enterprise Monitoring & Insights Architecture

- **Business Intelligence Fabric (2.5.1):** Strategic PowerBI analytics layer visualising
  holistic operational performance, aggregate user feedback trends, cross-sectional system
  interactions, and custom corporate KPIs.
- **Azure Monitoring & Operations Framework (2.5.2):** Continuous runtime metric collection
  tied directly into automated system alert hooks. Production of infrastructure telemetry
  visual dashboards using integrated **Grafana** nodes.
- **Automated Executive Report Loop (2.5.3):** End-of-month analytical reporting pipelines
  extracting batch system telemetry, applying advanced **Topic Modelling** over user inquiry
  trends, and performing structural **Feedback Sentiment Analysis** for executive business
  stakeholders.

---

## 3. Phase 1: High-Level Strategic Implementation Roadmap

### Milestone 1: Requirements Engineering & Foundations

- [ ] **Strategic Business Discovery:** Formulate and issue structured Requirements
      Questionnaires and Templates tailored for downstream insurance lines.
- [ ] **Feasibility Verification:** Execute technical and mathematical feasibility checks
      against gathered operational constraints.
- [ ] **Corporate Expectation Mapping:** Establish fundamental behavioural baselines from day
      one (e.g., *target systemic accuracy floor is strictly set above 80%; the product is a
      specialised regulatory reasoning engine, not a generic keyword search engine*).
- [ ] **Success Metrics Definition:** Document formal corporate KPIs and operational
      Acceptance Criteria.

### Milestone 2: Specification & Bill of Materials (BoM)

- [ ] **Functional Specification Architecture:** Complete and lock down the Functional
      Specification Document (FSD).
- [ ] **Technical Design Synthesis:** Complete the exhaustive Technical Specification Document
      (TSD) mapping all cloud system integrations.
- [ ] **Fiscal Estimation:** Formulate and publish the comprehensive Bill of Materials (BoM)
      capturing token, compute, network, and storage run rates.
- [ ] **Client Sign-Off Review:** Pitch and present detailed engineering plans to enterprise
      stakeholders for a formal Go/No-Go gate.

### Milestone 3: Test Scenario Design & Time-Plan Boundaries

- [ ] **UAT Design Injection:** Collaborate with business domain experts to outline real-world
      User Acceptance Testing (UAT) scenarios.
- [ ] **Timeline Boundary Enforcement:** Finalise operational schedule deadlines across the
      core execution windows:
    - **Build Phase:** Concrete development sprints mapping ingestion, indexing, and agent
      orchestration.
    - **Internal Test Phase:** Unit validation, integration check-outs, and regression
      tracking.
    - **Deployment Pipeline Verification:** Code promotion into staging nodes.
    - **User Acceptance Testing (UAT):** Real-world testing loops with enterprise operators.
    - **Security & Scale Operations:** Execution of strict external Penetration Tests and
      horizontal Infrastructure Stress Tests.
    - **Friends and Family (FnF) Run:** Limited internal alpha rollout for controlled
      validation (if flagged as operationally necessary).
    - **Production Rollout:** Staged cut-over to live enterprise clusters.
    - **Post-Production Support Hypercare:** Dedicated support engineering window post-launch.
    - **Maintenance & Evolution Lifecycles:** Continuous parameter calibration and systemic
      support structure hand-offs.

---

## 4. Horizon Target: North Star Roadmap

The subsequent evolutionary phases transfer the system from a highly advanced internal
assistant into an omni-channel, context-aware autonomous layer.

| 🤖 Advanced Cognitive Agents | 🎙️ Advanced Channel Integrations |
| :--- | :--- |
| • Corporate Watchlists & Risk Alerts <br> • Real-time Client Prep Synthesis <br> • AI Cross-Sale/Up-Sale Trainer | • Enterprise MS Teams Integration <br> • Real-Time Voice Engine Integration |
| **📊 Predictive Analytics** | **🧠 Next-Gen Architecture Layers** |
| • Time-Series Forecasting <br> &nbsp;&nbsp;&nbsp;(Nixtla TimeGEN-1 on Azure AI) | • Episodic Memory Optimisation <br> • AG-UI Protocol Standardisation |

---

## 5. PoC Coverage

The table below maps each strategic component (§ 2) to the PoC phase that validates it.
Components not in PoC scope are noted explicitly — they require Azure infrastructure and
enterprise integrations beyond the local workstation target.

| Strategic Component | PoC Phase | Status |
|---|---|---|
| PDF ingestion pipeline (§ 2.1) | Phase 6 | ✅ local (PyMuPDF + ChromaDB) |
| LLM document summariser + metadata sidecar (§ 2.1.4) | Phase 6 | ✅ |
| Chunk-level header-aware splitting (§ 2.2.1) | Phase 6 | ✅ |
| Year-scoped RAG retrieval (§ 2.3.5.2) | Phase 1, 7 | ✅ |
| Validator — grounded answers + citation check (§ 2.3.5.5) | Phase 2 | ✅ |
| Report generation agent — Markdown + chart (§ 2.3.5.4) | Phase 3 | ✅ |
| Long-term episodic memory — SQLite (§ 2.3.5.6) | Phase 4 | ✅ |
| OTel observability — Aspire Dashboard (§ 2.3.6) | Phase 5 | ✅ |
| Year-aware routing + clarifier + out-of-year guard (§ 2.3.5) | Phase 7 | ✅ |
| Talk-to-Data agent — typed Operation + pandas (§ 2.3.5.3) | Phase 8 | ✅ |
| Audit trail with OTel trace correlation (§ 2.3.7) | Phase 7 | ✅ |
| Executive annual report — DOCX / PDF / MD (§ 2.3.5.4) | Phase 9 | ✅ |
| Agentic Orchestration Backbone — Planner · Orchestrator · Workers · Skills (§ 2.3.5.1) | Phase 11 | ✅ |
| Feedback Ingestion Loop — thumbs + audit row (§ 2.4.3.3) | Phase 11 | ✅ |
| UI file upload (§ 2.3.4, § 2.4.2) | Phase 6 | ✅ |
| SharePoint / Azure Blob connectors (§ 2.1.1) | — | Not in PoC scope |
| RBAC at document level (§ 2.2.2) | — | Not in PoC scope |
| PowerBI analytics layer (§ 2.5.1) | — | Not in PoC scope |
| Grafana operational dashboards (§ 2.5.2) | — | Not in PoC scope |
| Human-in-the-loop approval gates + Telegram (§ 4) | Phase 12 | ✅ |
| Multi-modal voice — faster-whisper STT + Piper TTS, EN/EL (§ 4) | Phase 13 | ✅ |
| Cross-conversation planning + resume tokens (§ 4) | Phase 14 | Planned |
| Recursive Skill composition — sub-Plans (§ 4) | Phase 15 | Planned |
