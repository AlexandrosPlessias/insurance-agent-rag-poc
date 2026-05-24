
# 🛡️ Local Insurance Assistant: Privacy-First Agentic RAG PoC

This repository contains the Proof of Concept (PoC) for an **Enterprise Insurance Assistant Agentic App**. The system features advanced Retrieval-Augmented Generation (RAG) capabilities, multi-agent orchestration, and persistent memory.

Designed for high-compliance financial and insurance environments, this PoC architecture supports **100% local AI inference**. This guarantees absolute data sovereignty, enabling the processing of sensitive enterprise policy documents and contracts without exposing PII or proprietary corporate data to external third-party LLM APIs.

---

## 🏗️ System Architecture

The application decouples user interaction, business logic orchestration, and the agent topology to ensure a production-ready blueprint even when running entirely on a single workstation:

```text
                ┌────────────────────┐
                │    Streamlit UI    │
                └─────────┬──────────┘
                          │
                          ▼
                ┌────────────────────┐
                │  FastAPI Backend   │
                └─────────┬──────────┘
                          │
                          ▼
                ┌────────────────────┐
                │     LangGraph      │
                │    Supervisor      │
                └──────┬─────────────┘
                       │
        ┌──────────────┼──────────────┼──────────────┐
        ▼              ▼              ▼              ▼
 ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌─────────────────┐
 │ RAG Agent  │ │Memory Agent│ │Report Agent│ │ Validator Agent │
 └─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └────────┬────────┘
       │              │              │                 │
       ▼              ▼              ▼                 │
 ┌────────────┐ ┌────────────┐ ┌────────────┐          │
 │  ChromaDB  │ │   SQLite   │ │   Pandas   │          │
 └────────────┘ └────────────┘ └────────────┘          │
       │                                               |
       ▼                                               ▼
 ┌────────────────────────────────────────────────────────┐
 │       Ollama                                           │
 │  qwen2.5 + nomic                                       │
 └────────────────────────────────────────────────────────┘

```

---

## 🛠️ Recommended Local Stack

| Layer | Component Choice | Rationale |
| --- | --- | --- |
| **OS Layer** | `WSL2 Ubuntu` | Native environment for stable Docker support, Python tooling, ChromaDB compatibility, and Ollama execution. |
| **Main LLM** | `qwen2.5:7b` (q4_K_M) | Top-tier local reasoning model; quantized by default to protect laptop RAM usage while maintaining dense domain comprehension. |
| **Embeddings** | `nomic-embed-text` | High-efficiency local vector embeddings, optimized for LangChain compatibility and RAG text parsing. |
| **Orchestration** | `LangGraph` | Stateful, multi-agent graph architecture featuring supervisor routing and deterministic validation loops. |
| **Vector DB** | `ChromaDB` | Lightweight, embedded vector database utilizing an explicit file-based disk storage directory. |
| **Memory Store** | `SQLite` | High-speed, local relational engine handling persistent, multi-session episodic user memory. |
| **Backend API** | `FastAPI` | High-performance, asynchronous REST API gateway decoupling frontend interactions from heavy agent graph workloads. |
| **Frontend UI** | `Streamlit` | Low-complexity, rapid-prototype UI focusing heavily on core utility ("Soviet UI" design paradigm). |
| **PDF Parsing** | `PyMuPDF` | Fast, high-fidelity local programmatic parsing utilities for complex corporate insurance schemas. |

---

## 🚀 Environment Initialization & Setup

### 1. Operating System Environment (Windows Pre-requisites)

To maximize stability, compile and execute the Python runtime inside an Ubuntu-based **WSL2 (Windows Subsystem for Linux)** environment:

```bash
# Execute within standard PowerShell/Command Prompt to spin up WSL2
wsl --install -d Ubuntu

```

### 2. Core Local AI Inference Engine (Ollama Setup)

Install Ollama within your workspace and retrieve the localized, quantized model binaries directly into your workspace cache:

```bash
# Pull the highly-optimized main reasoning model
ollama pull qwen2.5:7b

# Pull the core RAG text embedding model
ollama pull nomic-embed-text

# Optional alternative fallback model
ollama pull llama3.1:8b

```

### 3. Core Software Integration Snippets

#### A. LangChain Local Integration Bridge

```python
from langchain_ollama import ChatOllama, OllamaEmbeddings

# Initialize the main localized reasoning engine
llm = ChatOllama(
    model="qwen2.5:7b",
    temperature=0
)

# Initialize the local data transformer
embeddings = OllamaEmbeddings(
    model="nomic-embed-text"
)

```

#### B. ChromaDB Local Vector Store Instantiation

```python
from langchain_chroma import Chroma

vectorstore = Chroma(
    collection_name="policies",
    embedding_function=embeddings,
    persist_directory="./chroma_db"
)

```

---

## 📈 Agile Implementation Strategy (Phases 1-5)

To maintain a disciplined development loop, this project rejects premature infrastructure optimization (e.g., distributed Kubernetes, MCP transport pipelines, or Grafana logging frameworks at day one). Development is tightly partitioned into modular checkpoints:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        MVP CONSTRUCTION PATHWAY                        │
├───────────────────────────────────┬────────────────────────────────────┤
│ 🔹 Phase 1: Basic RAG Validation  │ 🔹 Phase 2: LangGraph Integration  │
│  • Local PDF Parsing (PyMuPDF)    │  • State-Machine Supervisor Node   │
│  • ChromaDB Indexing              │  • Dynamic Output Validator        │
│  • Basic Vector QA Engine         │                                    │
├───────────────────────────────────┼────────────────────────────────────┤
│ 🔹 Phase 3: Reporting Autonomy    │ 🔹 Phase 4: Long-Term Memory       │
│  • Markdown Output Formatting     │  • SQLite Conversation Persistence │
│  • Dynamic Chart Generation       │  • Cross-Session User History      │
├───────────────────────────────────┴────────────────────────────────────┤
│                    🔹 Phase 5: Production Observability                 │
│                     • Langfuse / OpenTelemetry Tracing                 │
│                     • UI Performance Metrics                           │
└────────────────────────────────────────────────────────────────────────┘

```

### Core MVP Checklist (Phase 1 Target Clearances)

* [ ] Programmatic PDF Document Ingestion (`PyMuPDF`).
* [ ] Chunking and Local `ChromaDB` Indexing.
* [ ] Retrieval Augmentation Loop using Local Embedding Tensors.
* [ ] Deterministic LangGraph State Flow Engine.
* [ ] Primary RAG Agent Task Routing.
* [ ] UI Source Citations mapped to exact page numbers.
* [ ] Simplified Streamlit Conversational Frontend.

---

## 🔒 Enterprise Privacy Narrative

> **Architecture Declaration:** *“The PoC supports fully local inference using Ollama, enabling enterprise policy processing without external LLM data exposure.”*

By routing sensitive operational guidelines, data frames, and user records strictly through a local sandboxed vector space, this application demonstrates a path toward strict **GDPR alignment and EU AI Act compliance compliance** directly from an individual enterprise workstation.