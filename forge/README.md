# Forge — AI-Powered Code Intelligence Platform

**Forge** is an internal AI developer platform built for Capgemini AIE India / HSBC RFP.
It provides three AI-powered pipelines that work against a live codebase loaded into a graph database.

---

## The Three Pipelines

### Pipeline 1 — Impact Analysis
**"What breaks if I change X?"**

Takes a natural-language change request, queries the KuzuDB code graph to trace all callers and dependencies, and produces a layered impact report showing exactly which services, files, and functions need to change — with confidence levels and evidence sourcing.

### Pipeline 2 — Code Generation
**"Write the code for me."**

Takes an approved impact report and automatically generates a unified diff implementing the change. Design Agent reads the codebase, creates a plan, Implementation Agents produce diffs in parallel, the Deterministic Gate runs 8 harness checks (syntax, imports, security, complexity, contracts, hallucination, negative constraints), and the human reviews diffs before approving.

### Pipeline 3 — Reverse Engineer
**"What does this system do?"**

Takes a plain-text application log file (no source code needed) and produces a complete 12-section specification document. Extracts services, endpoints, trace flows and Kafka topics deterministically, then uses Gemini 2.5 Pro to build an Application Specification Graph with CONFIRMED / INFERRED / GAP confidence tags, reviewed by a gap agent before spec writing.

---

## Quick Start

### Prerequisites

```
Python 3.11+
Node.js 18+
GOOGLE_API_KEY  (for Gemini — Pipelines 1, 2, 3)
```

### Setup

```bash
# 1. Create and activate venv
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate        # macOS/Linux

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Build frontend
cd frontend && npm install && npm run build && cd ..

# 4. Set API key and server config
# Edit .env:
#   GOOGLE_API_KEY=your_key_here
#   PORT=8000
#   HOST=0.0.0.0
#   LOG_LEVEL=info

# 5. Start server
python main.py
```

Open `http://localhost:8000`.

---

## Project Structure

```
forge/
├── main.py                          # FastAPI app, lifespan, router wiring
├── requirements.txt
├── .env                             # GOOGLE_API_KEY (not committed)
│
├── frontend/                        # React + TypeScript SPA
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx        # Home — services overview + Past Requests panel
│   │   │   ├── Chat.tsx             # Pipeline 1: requirements gathering
│   │   │   ├── Pipeline.tsx         # Pipeline 1: live analysis progress
│   │   │   ├── Results.tsx          # Pipeline 1: impact report review
│   │   │   ├── CodeGen.tsx          # Pipeline 2: code generation progress
│   │   │   ├── DiffApproval.tsx     # Pipeline 2: diff review + approve
│   │   │   ├── ReverseEngineer.tsx  # Pipeline 3: log file upload
│   │   │   ├── REPipeline.tsx       # Pipeline 3: live 5-stage progress
│   │   │   ├── RESpec.tsx           # Pipeline 3: 12-section spec viewer
│   │   │   └── HistoryDetail.tsx    # Past Requests & Results detail view
│   │   └── components/
│   │       ├── HowForgeWorks.tsx    # How it Works modal (codegen)
│   │       └── HowREWorks.tsx       # How it Works modal (RE)
│   └── dist/                        # Built static assets (served by FastAPI)
│
├── src/
│   ├── interfaces/api/
│   │   ├── routes/                  # Pipeline 1 + 2 API routes
│   │   ├── re_routes.py             # Pipeline 3 API routes
│   │   └── cache_routes.py          # Demo cache API routes
│   │
│   └── modules/
│       ├── agents/                  # Pipeline 1: context gatherer, impact, verification
│       │   ├── orchestrator.py      # 3-agent loop with harness
│       │   ├── context_gatherer.py
│       │   ├── verification_agent.py
│       │   └── impact/
│       │       └── agent.py
│       │
│       ├── codegen/                 # Pipeline 2: design → implement → verify
│       │   ├── orchestrator.py
│       │   ├── design_agent.py
│       │   ├── implementation_agent.py
│       │   ├── coordinator_agent.py
│       │   ├── verifier_agent.py
│       │   └── harness/             # 8 deterministic checks
│       │       ├── gate.py
│       │       ├── syntax_checker.py
│       │       ├── import_resolver.py
│       │       ├── security_scanner.py
│       │       ├── hallucination_detector.py
│       │       ├── contract_checker.py
│       │       └── negative_constraints.py
│       │
│       ├── reverse_engineer/        # Pipeline 3: log → spec
│       │   ├── orchestrator.py
│       │   ├── log_parser.py        # Stage 1: deterministic extraction
│       │   ├── template_extractor.py# Stage 2: drain3 template mining
│       │   ├── inference_agent.py   # Stage 3: Gemini 2.5 Pro
│       │   ├── gap_agent.py         # Stage 4: Gemini 2.5 Flash
│       │   ├── spec_writer_agent.py # Stage 5: Gemini 2.5 Flash × 12 sections
│       │   ├── harness.py           # Policy gate, budget, loop detector, sanitizer
│       │   ├── schemas.py           # ASG, RESession, SpecSection, Confidence
│       │   └── prompts.py
│       │
│       ├── codegraph/               # KuzuDB graph store + tools
│       │   ├── kuzu_store.py
│       │   ├── tools.py
│       │   └── enricher.py
│       │
│       └── cache/                   # Demo cache
│           └── demo_cache.py
│
├── docs/
│   ├── HARNESS_IMPLEMENTATION_REFERENCE.md    # 26 codegen + agent harness components
│   ├── RE_HARNESS_IMPLEMENTATION_REFERENCE.md # 10 RE pipeline harness components
│   ├── CODE_GENERATION_ARCHITECTURE.md        # Codegen pipeline design
│   ├── CODEGRAPH_INTEGRATION.md               # KuzuDB + codegraph-tools
│   └── MULTI_AGENT_CODE_GEN_RESEARCH.md       # Research backing
│
└── new-requirements/
    └── test-logs/                   # 11 test datasets for Pipeline 3
```

---

## API Reference

### Pipeline 1 — Impact Analysis

| Method | Path | Description |
|--------|------|-------------|
| POST | `/pipeline/start` | Start with initial requirement message |
| POST | `/pipeline/{id}/respond` | Continue requirements gathering |
| POST | `/pipeline/{id}/confirm` | Confirm requirements, start analysis |
| GET  | `/pipeline/{id}` | Poll state + activity log |
| POST | `/pipeline/{id}/approve` | Approve the impact report |

### Pipeline 2 — Code Generation

| Method | Path | Description |
|--------|------|-------------|
| POST | `/codegen/start` | Start from approved pipeline ID |
| GET  | `/codegen/{id}` | Poll state + activity log |
| GET  | `/codegen/{id}/plan` | Get the design plan |
| GET  | `/codegen/{id}/diffs` | Get all generated diffs |
| POST | `/codegen/{id}/approve` | Approve or reject changes |

### Pipeline 3 — Reverse Engineer

| Method | Path | Description |
|--------|------|-------------|
| POST | `/reverse-engineer/start` | Upload log file + optional context |
| GET  | `/reverse-engineer/{id}` | Poll session state + activity log |
| GET  | `/reverse-engineer/{id}/facts` | Extracted facts (services, endpoints, traces) |
| GET  | `/reverse-engineer/{id}/spec/all` | All 12 spec sections |
| GET  | `/reverse-engineer/{id}/spec/{section_id}` | Single section |
| GET  | `/reverse-engineer/{id}/spec/download` | ZIP of all Markdown files |

### Demo Cache

| Method | Path | Description |
|--------|------|-------------|
| GET  | `/cache` | List all past runs (metadata) |
| GET  | `/cache/stats` | Counts by pipeline type |
| GET  | `/cache/{id}` | Full entry: input + output |
| DELETE | `/cache/{id}` | Delete one entry |
| POST | `/cache/{id}/label` | Rename label |

---

## How Each Pipeline Saves to Cache

Every completed pipeline run is **automatically saved** to `forge_demo_cache.db`:

| Pipeline | Saved when | Label format |
|---|---|---|
| Impact Analysis | Human clicks "Approve" on impact report | First 60 chars of change description |
| Code Generation | Human clicks "Approve Changes" on diffs | Change request + `[service-name]` |
| Reverse Engineer | All 12 spec sections generated | `RE: {log_filename}` |

Past runs appear on the Dashboard under **"Past Requests & Results"**. Click any entry to see the full input and result.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_API_KEY` | Yes (for LLM stages) | Gemini API key — Pipelines 1, 2, 3 all use Gemini |

Without `GOOGLE_API_KEY`, Stages 1 and 2 of Pipeline 3 still run (deterministic), and the app starts, but LLM stages return mock responses.

---

## Key Design Principles

**The LLM proposes. The harness verifies.**

All three pipelines use deterministic harness components that run outside the LLM to verify its outputs:
- Pipeline 1: cypher write guard, symbol name validator, receipt log, grounding check, loop detector, injection sanitizer
- Pipeline 2: syntax check (tree-sitter), import resolver, security scanner, complexity analyser, contract checker, hallucination detector, negative constraints
- Pipeline 3: policy gate, budget enforcer, loop detector, input sanitizer, confidence tagging (CONFIRMED/INFERRED/GAP)

See `docs/HARNESS_IMPLEMENTATION_REFERENCE.md` and `docs/RE_HARNESS_IMPLEMENTATION_REFERENCE.md` for full detail.

---

## SQLite Databases

| File | Contains |
|---|---|
| `forge_sessions.db` | Impact analysis pipeline sessions (Pipeline 1) |
| `forge_re_sessions.db` | Reverse engineer sessions (Pipeline 3) |
| `forge_demo_cache.db` | All completed pipeline runs (all 3 pipelines) |

All three are created automatically on first run. Not committed to git.
