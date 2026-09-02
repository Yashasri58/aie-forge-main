# AI-Accelerated Payments Modernization — Project Plan

**Version:** 2.0  
**Date:** 2026-09-02 (Updated)  
**Timeline:** 8 weeks

---

## Executive Summary

Build a **functional payment application** with 7 microservices + UI, then demonstrate AI-powered code generation using:
1. Code graph for understanding service dependencies
2. Requirement decomposition into service-level tasks  
3. Multi-agent orchestration for coordinated changes
4. Deterministic verification harness
5. Audit-grade governance

---

## Phase Overview

| Phase | Weeks | Focus |
|-------|-------|-------|
| **Phase 1** | 1–2 | Foundation — 7 Microservices + UI + Contracts |
| **Phase 2** | 3 | Code Graph Construction |
| **Phase 3** | 4 | Requirement → Service Mapping |
| **Phase 4** | 5–6 | Agent Orchestration |
| **Phase 5** | 7–8 | Verification Harness + Governance |

---

## Phase 1: Foundation — Functional Payment Application

**Goal:** Build a working cross-border wire transfer system with 7 microservices, UI, and OpenAPI contracts.

### 1.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        PAYMENT UI (:8080)                       │
│         Dashboard | New Payment | History | Accounts            │
└─────────────────────────────────────────────────────────────────┘
                                │ HTTP
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    GATEWAY SERVICE (:3000)                      │
│              API Entry Point + Request Routing                  │
└─────────────────────────────────────────────────────────────────┘
        │              │              │              │
        ▼              ▼              ▼              ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│   ACCOUNT   │ │   PAYMENT   │ │     FX      │ │    AUDIT    │
│   SERVICE   │ │  PROCESSOR  │ │   SERVICE   │ │   SERVICE   │
│   (:3001)   │ │   (:3002)   │ │   (:3005)   │ │   (:3006)   │
└─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
┌─────────────┐ ┌─────────────┐ ┌ ─ ─ ─ ─ ─ ─ ┐
│ VALIDATION  │ │   LEDGER    │    MOCK HUB   
│   SERVICE   │ │   SERVICE   │    MOCK WOLF  
│   (:3003)   │ │   (:3004)   │  (inline in   
└─────────────┘ └─────────────┘   processor)  
                               └ ─ ─ ─ ─ ─ ─ ┘
```

### 1.2 Services (7 Independent Repos)

| # | Service | Port | Responsibility |
|---|---------|------|----------------|
| 1 | gateway-service | 3000 | API entry point, routing |
| 2 | account-service | 3001 | Account management, balances |
| 3 | payment-processor | 3002 | Core orchestration (+ mocks HUB/WOLF internally) |
| 4 | validation-service | 3003 | Business rules engine |
| 5 | ledger-service | 3004 | Double-entry bookkeeping |
| 6 | fx-service | 3005 | Currency conversion |
| 7 | audit-service | 3006 | Compliance logging, audit trail |
| — | payment-ui | 8080 | User interface |

**Note:** HUB and WOLF are external systems. We mock them inline within payment-processor (not as separate services).

### 1.3 Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Node.js + Express.js |
| Language | Plain JavaScript (ES6+) |
| Database | SQLite (per service) |
| API Style | REST + JSON |
| Communication | HTTP (synchronous) |
| UI | Plain HTML + CSS + Vanilla JS |
| Contracts | OpenAPI 3.1 YAML |
| Container | Docker + Docker Compose |

### 1.4 Code Structure (Within Each Service)

Each service has internal shared utils (functions called from multiple places within the same service):

```
service-name/
├── src/
│   ├── routes/          # API endpoints
│   ├── services/        # Business logic
│   ├── repositories/    # Database access
│   ├── utils/           # Shared utilities (internal only)
│   │   ├── validators.js    ← Called by routes AND services
│   │   └── formatters.js    ← Called by multiple modules
│   └── db/
└── contracts/
    └── openapi.yaml
```

### 1.5 Pre-Seeded Test Data

**5 Account Holders:**

| Holder | Account | Bank | Currency | Balance |
|--------|---------|------|----------|---------|
| John Doe | GB82WEST12345698765432 | WESTGB2L | GBP | 50,000 |
| Jane Smith | DE89370400440532013000 | COBADEFF | EUR | 75,000 |
| Bob Wilson | US12345678901234567890 | CHASUS33 | USD | 100,000 |
| Alice Chen | SG1234567890123456 | DBSSSGSG | SGD | 45,000 |
| Carlos Garcia | ES9121000418450200051332 | CAIXESBB | EUR | 30,000 |

### 1.5 Deliverables

- [ ] 7 runnable microservices
- [ ] Functional UI (dashboard, payment form, history)
- [ ] OpenAPI spec for each service
- [ ] Docker Compose for local environment
- [ ] End-to-end payment flow working
- [ ] 5 pre-seeded test accounts

### 1.6 Payment Flow

```
INITIATED → VALIDATING → SCREENING → PROCESSING → POSTING → COMPLETED
                ↓            ↓           ↓
             REJECTED      ON_HOLD     FAILED
```

---

## Phase 2: Code Graph Construction

**Goal:** Build a queryable semantic graph of the 7-service payment system.

### 2.1 Graph Components

| Node Type | What It Represents | Source |
|-----------|-------------------|--------|
| **Service** | Microservice (7 total) | Directory structure |
| **Endpoint** | REST API endpoint | OpenAPI spec + code |
| **Function** | JS function/module | AST parsing |
| **Schema** | Data model | OpenAPI schemas |
| **HTTPCall** | Service-to-service call | Code analysis |

### 2.2 Edge Types

| Edge | Meaning | Example |
|------|---------|---------|
| `CALLS` | Service A calls Service B's API | payment-processor → account-service |
| `USES_SCHEMA` | Code references schema | /payments uses PaymentRequest |
| `CONTAINS` | Service contains function | validation-service contains amountLimit.js |
| `DEPENDS_ON` | Code dependency | orchestrator.js depends on fxService |

### 2.3 Graph Construction Pipeline

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  OpenAPI Specs  │ ──▶ │   AST Parser    │ ──▶ │   Graph Builder │
│  (7 services)   │     │   (JavaScript)  │     │   (NetworkX/    │
└─────────────────┘     └─────────────────┘     │    Neo4j)       │
                                                └─────────────────┘
```

### 2.4 Key Queries for Demo

```
Q1: "What services are affected if I add a field to PaymentRequest?"
    → gateway-service, payment-processor, validation-service

Q2: "What happens if account-service is down?"
    → payment-processor fails at step 2 and step 8

Q3: "Which services touch FX conversion?"
    → fx-service, payment-processor
```

### 2.5 Deliverables

- [ ] Graph schema definition
- [ ] AST parser for JavaScript/Node.js
- [ ] OpenAPI spec parser
- [ ] HTTP call detector (find fetch/axios calls)
- [ ] Graph construction script
- [ ] Query API: `GET /graph/impact?change=PaymentRequest.amount`

---

## Phase 3: Requirement → Service Mapping

**Goal:** Given a natural language requirement, identify impacted services.

### 3.1 Input → Output

```
INPUT:  "Add currency conversion validation before posting"
OUTPUT:
  - payment-processing (FX rate lookup, validation logic)
  - posting-settlement (pre-posting check, message format update)
  - validation-routing (new rule integration)
  Confidence: 87%
  Human review recommended: Yes (new validation rule)
```

### 3.2 Processing Pipeline

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Requirement   │ ──▶ │  Entity/Intent  │ ──▶ │   Graph Query   │
│   (NL text)     │     │   Extraction    │     │   (find nodes)  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │                        │
                               ▼                        ▼
                        "currency conversion"    Services touching
                        "validation"             FX + validation +
                        "posting"                posting stages
                               │                        │
                               └────────┬───────────────┘
                                        ▼
                              ┌─────────────────┐
                              │  Impact Analysis │
                              │  + Confidence    │
                              └─────────────────┘
```

### 3.3 Techniques

| Step | Approach |
|------|----------|
| **Entity extraction** | LLM (Claude/GPT) or fine-tuned NER for payment domain |
| **Intent classification** | Add/Modify/Remove + scope (field/endpoint/service) |
| **Graph traversal** | Match entities to graph nodes, follow edges |
| **Impact scoring** | Direct match (high), 1-hop (medium), 2-hop (low) |
| **Confidence calculation** | Based on match quality + coverage |

### 3.4 Deliverables

- [ ] Requirement parser (NL → structured intent)
- [ ] Graph query generator
- [ ] Impact analysis engine
- [ ] Confidence scoring algorithm
- [ ] Human review flagging logic
- [ ] CLI/API: `analyze-requirement "requirement text"`

### 3.5 Gaps Identified & Mitigations

| Gap | Risk | Mitigation |
|-----|------|------------|
| **Ambiguous requirements** | Wrong services identified | Add clarification prompts, confidence thresholds |
| **Missing domain context** | LLM doesn't understand payment terms | Fine-tune or use RAG with payment glossary |
| **Second-order impacts missed** | Change A breaks B which breaks C | Implement transitive dependency traversal |

---

## Phase 4: Agent Orchestration

**Goal:** Coordinate multiple AI agents to make changes across services.

### 4.1 Agent Roles

| Agent | Responsibility | Context Window |
|-------|---------------|----------------|
| **Coordinator** | Decomposes tasks, maintains contracts, sequences work | Full system view (compressed) |
| **Service Specialist** | Deep context on one service, generates code | Single service (full detail) |
| **Verifier** | Validates changes, checks contracts, flags issues | Cross-service contracts |

### 4.2 Orchestration Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        COORDINATOR                              │
│  1. Receive impacted services list                              │
│  2. Create task breakdown per service                           │
│  3. Extract current contracts                                   │
│  4. Dispatch to specialists                                     │
└─────────────────────────────────────────────────────────────────┘
          │                    │                    │
          ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   Specialist:   │  │   Specialist:   │  │   Specialist:   │
│   payment-proc  │  │   posting-sett  │  │   validation    │
│                 │  │                 │  │                 │
│  - Read code    │  │  - Read code    │  │  - Read code    │
│  - Generate fix │  │  - Generate fix │  │  - Generate fix │
│  - Create PR    │  │  - Create PR    │  │  - Create PR    │
└─────────────────┘  └─────────────────┘  └─────────────────┘
          │                    │                    │
          └────────────────────┼────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                         VERIFIER                                │
│  1. Collect all changes                                         │
│  2. Validate contracts still compatible                         │
│  3. Check for breaking changes                                  │
│  4. Report issues → loop back to specialists if needed          │
└─────────────────────────────────────────────────────────────────┘
```

### 4.3 Token Efficiency Strategies

| Strategy | How It Works | Savings |
|----------|--------------|---------|
| **Memory pointers** | Reference code by file:line, not full content | ~84% |
| **Sub-agent isolation** | Each specialist gets only their service | 50K → 2K |
| **Contract summaries** | Compress contracts to signatures only | ~60% |
| **Incremental context** | Only add context when specialist asks | On-demand |

### 4.4 Model Routing

| Task Type | Model | Rationale |
|-----------|-------|-----------|
| Planning, decomposition | Claude Opus / GPT-4 | Needs reasoning |
| Code generation | Claude Sonnet / GPT-4 | Balance of quality + speed |
| Simple edits | Claude Haiku / GPT-3.5 | Fast, cheap |
| Verification | Deterministic (no LLM) | No hallucination risk |

### 4.5 Deliverables

- [ ] Coordinator agent implementation
- [ ] Service specialist agent template
- [ ] Verifier agent implementation
- [ ] Task queue / orchestration layer
- [ ] Context management system (memory pointers)
- [ ] PR generation per service

### 4.6 Gaps Identified & Mitigations

| Gap | Risk | Mitigation |
|-----|------|------------|
| **Agent coordination is hard** | Deadlocks, race conditions | Use sequential merge strategy, not parallel commits |
| **Specialists may conflict** | Service A change incompatible with Service B | Verifier catches, loops back with constraints |
| **Token budget overrun** | Complex changes exceed context | Split into smaller PRs, staged rollout |
| **No rollback on failure** | Partial changes left in bad state | Feature flags + atomic commit groups |

---

## Phase 5: Verification Harness + Governance

**Goal:** Deterministically verify AI-generated changes; provide audit trail.

### 5.1 Verification Layers

| Layer | What It Checks | Enforcement | Tooling |
|-------|---------------|-------------|---------|
| **Pre-commit hooks** | Lint, type check, secrets, formatting | Blocks commit | ESLint, Checkstyle, git-secrets |
| **Contract validation** | OpenAPI/AsyncAPI compatibility | Breaks build | Spectral, openapi-diff, Prism |
| **Architectural rules** | Naming conventions, dependency direction, data flow | Rejects violation | ArchUnit, custom rules |
| **Integration tests** | End-to-end payment flow | Blocks merge | Testcontainers, Pact |
| **Hallucination detection** | API mismatches, undefined identifiers | Auto-correct or reject | AST-based static analysis |

### 5.2 Contract Validation Detail

```
┌─────────────────────────────────────────────────────────────────┐
│                    CONTRACT VALIDATION                          │
├─────────────────────────────────────────────────────────────────┤
│  1. Extract OpenAPI from each service (before + after)          │
│  2. Run openapi-diff: detect breaking changes                   │
│     - Removed endpoints                                         │
│     - Changed request/response schemas                          │
│     - Modified required fields                                  │
│  3. Cross-reference consumer expectations (Pact contracts)      │
│  4. Fail build if breaking change detected without version bump │
└─────────────────────────────────────────────────────────────────┘
```

### 5.3 Architectural Rules Engine

| Rule | Description | Enforcement |
|------|-------------|-------------|
| **No direct DB access across services** | Service A cannot query Service B's database | Dependency check |
| **Events must use shared schemas** | AsyncAPI messages reference shared schemas | Schema registry validation |
| **PII fields must be encrypted** | Fields tagged @PII use encryption | AST + annotation check |
| **Payment logic requires approval** | Changes to `*Payment*.java` need senior review | Path-based classification |

### 5.4 Governance — Risk-Tiered Autonomy

| Risk Level | Change Type | Approval Required | Automation |
|------------|-------------|-------------------|------------|
| **Low** | Docs, logging, formatting | None | Auto-merge |
| **Medium** | Non-payment business logic | 1 peer review | PR required |
| **High** | Payment logic, transactions | Senior engineer | PR + sign-off |
| **Critical** | Compliance, regulatory | Architecture board | PR + audit log |

### 5.5 Audit Trail Requirements

| What | How | Storage |
|------|-----|---------|
| **Requirement → Code link** | PR description references Jira ID | Git + Jira integration |
| **AI vs Human authorship** | Git trailers: `AI-Generated-By: coordinator-agent` | Git metadata |
| **Approval chain** | GitHub required reviewers + sign-off | GitHub audit log |
| **Test evidence** | CI artifacts linked to PR | S3 / artifact storage |
| **Deployment record** | Which commit deployed when | Deployment pipeline |

### 5.6 Deliverables

- [ ] Pre-commit hook configuration
- [ ] Contract diff tool integration
- [ ] Architectural rules engine (ArchUnit or custom)
- [ ] Integration test suite (payment flow)
- [ ] Hallucination detection rules (AST-based)
- [ ] Risk classification system
- [ ] Audit log schema + storage
- [ ] Governance dashboard (optional)

### 5.7 Gaps Identified & Mitigations

| Gap | Risk | Mitigation |
|-----|------|------------|
| **Too many false positives** | Teams ignore warnings | Tune rules, start strict then relax |
| **Integration tests are slow** | Blocks fast iteration | Run subset on PR, full suite on merge |
| **Risk classification is subjective** | Inconsistent enforcement | Clear rubric, path-based auto-classification |
| **Audit trail adds overhead** | Teams skip it | Automate capture, make it invisible |

---

## Demo Scenario — End-to-End Walkthrough

**Requirement:** "Add currency conversion validation before posting — reject if converted amount exceeds receiver's daily limit"

| Step | Actor | Action | Proves |
|------|-------|--------|--------|
| 1 | Human | Enters requirement in UI | NL understanding |
| 2 | System | Queries graph → returns impacted services: `fx-service`, `validation-service`, `payment-processor`, `ledger-service` | Multi-service awareness |
| 3 | Human | Reviews impact analysis, approves | Human-in-the-loop |
| 4 | Coordinator | Decomposes into 4 tasks (one per service) | Task breakdown |
| 5 | Specialists | Generate code changes in parallel | Multi-agent orchestration |
| 6 | Verifier | Checks contracts — **FINDS BREAKING CHANGE** (fx-service response schema) | **WOW MOMENT** |
| 7 | System | Loops back, specialist self-corrects | Self-healing |
| 8 | Harness | All checks pass ✓ | Deterministic verification |
| 9 | System | Creates 4 linked PRs | Governance, traceability |
| 10 | Human | Reviews, merges | Audit complete |

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Graph construction takes too long | Medium | High | Start with OpenAPI parsing only |
| Agent orchestration is flaky | High | High | Extensive testing, fallback to single-agent mode |
| Demo environment instability | Medium | Medium | Dockerized, reproducible setup |
| Token costs exceed budget | Medium | Low | Model routing, caching |
| Scope creep | High | Medium | Fixed demo scenario |

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Payment flow works end-to-end | 100% | Manual test |
| Service identification accuracy | >90% | Test with 10 sample requirements |
| Contract validation catch rate | 100% | Inject 5 breaking changes |
| End-to-end demo time | <10 minutes | Stopwatch |
| Audit trail completeness | 100% | Every change traceable |

---

## Decisions Made

| Question | Decision |
|----------|----------|
| Monorepo vs multi-repo? | Multi-repo (7 separate repos) |
| Language? | Node.js + Plain JavaScript |
| Database? | SQLite (per service) |
| Messaging? | HTTP only (no pub/sub) |
| UI Framework? | Simple HTML + CSS + Vanilla JS |
| Communication? | Synchronous HTTP |

---

## Next Steps

1. ✅ Planning complete
2. → **Scaffold 7 service repositories**
3. → **Build account-service first** (foundation for others)
4. → **Build payment flow services** (processor, validation, compliance, ledger, fx)
5. → **Build gateway-service** (API aggregation)
6. → **Build UI** (dashboard, payment form)

---

## Appendix A: Service Port Summary

| Service | Port | Responsibility |
|---------|------|----------------|
| gateway-service | 3000 | API entry point |
| account-service | 3001 | Account management |
| payment-processor | 3002 | Core orchestration (+ mocks HUB/WOLF) |
| validation-service | 3003 | Business rules |
| ledger-service | 3004 | Double-entry bookkeeping |
| fx-service | 3005 | Currency conversion |
| audit-service | 3006 | Compliance audit trail |
| payment-ui | 8080 | User interface |

---

## Appendix B: Research References

| Paper/Source | Relevance |
|--------------|-----------|
| LogicLens | Semantic multi-repo graph via AST + LLM |
| GRACE | Multi-level code graph (file, AST, call graph) |
| AST-derived Graph-RAG (ArXiv:2601.08773) | Graph > vector for architectural reasoning |
| Chris Richardson's Coding Agent Sandwich | Deterministic constraints wrapping AI |
| Augment Code patterns (2026) | Six proven multi-agent patterns |
| DevEval (ACL 2024) | Real repo-level AI accuracy benchmarks |

---

## Appendix C: Glossary

| Term | Definition |
|------|------------|
| **HUB** | External account/core banking system (we mock it) |
| **WOLF** | External sanctions screening system (we mock it) |
| **AST** | Abstract Syntax Tree — parsed code structure |
| **OpenAPI** | Specification for REST API contracts |
| **SOX** | Sarbanes-Oxley Act — financial audit requirements |
| **PCI-DSS** | Payment Card Industry Data Security Standard |
