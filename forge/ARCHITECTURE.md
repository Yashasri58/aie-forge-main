# Forge Impact Analysis Pipeline

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    MULTI-AGENT PIPELINE                         │
│                    (All agents use Google ADK)                  │
└─────────────────────────────────────────────────────────────────┘

User Requirement
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  1. CONTEXT GATHERER AGENT                                      │
│     ─────────────────────                                       │
│     Tools: get_available_services(), search_functions()         │
│     Purpose: Clarify vague requirements via conversation        │
│     Output: RequirementsOutput (JSON)                           │
│             {services, functions, description, constraints}     │
└─────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. IMPACT AGENT                                                │
│     ────────────                                                │
│     Tools: get_schema(), query_graph(), trace_call_path(),      │
│            analyze_impact(), search_symbols(),                  │
│            get_service_topology()                               │
│     Purpose: Produce layered impact report                      │
│     Output: Human-readable report with:                         │
│             - Layer 0 (direct changes)                          │
│             - Layer 1 (secondary impacts)                       │
│             - Layer 2 (tertiary impacts)                        │
│             - Execution order                                   │
│             - Summary                                           │
└─────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. VERIFICATION AGENT                                          │
│     ──────────────────                                          │
│     Tools: trace_callers(), trace_callees(), search_symbol()    │
│     Purpose: Verify all callers traced at each layer            │
│     Output: {complete, confidence, gaps[], verified_paths}      │
└─────────────────────────────────────────────────────────────────┘
       │
       ├── Gaps found? ──► Loop back to Impact Agent (max 3x)
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  4. HUMAN APPROVAL GATE                                         │
│     ────────────────────                                        │
│     Review report → ✅ APPROVE or ❌ REJECT                     │
└─────────────────────────────────────────────────────────────────┘
```

## File Structure

```
forge/
├── main.py                          # FastAPI app entry point
├── requirements.txt                 # Dependencies
├── .env                             # GOOGLE_API_KEY
│
└── src/
    ├── interfaces/
    │   └── api/
    │       └── routes/
    │           ├── __init__.py      # Router exports
    │           ├── health.py        # Health check endpoints
    │           ├── impact.py        # Impact Q&A endpoints
    │           ├── graph_explorer.py # Graph visualization
    │           └── pipeline.py      # Pipeline endpoints
    │
    └── modules/
        └── agents/
            ├── __init__.py          # Agent exports
            ├── base.py              # BaseADKAgent class
            ├── context_gatherer.py  # Requirements clarification
            ├── verification_agent.py # Completeness verification
            ├── orchestrator.py      # Pipeline coordination
            │
            └── impact/
                ├── __init__.py
                ├── agent.py         # ImpactAgent (main analysis)
                ├── tools.py         # GraphTools (graph queries)
                └── prompts.py       # System instructions
```

## API Endpoints

### Pipeline
- `POST /pipeline/start` - Start analysis with requirement
- `POST /pipeline/{id}/respond` - Answer clarifying questions
- `GET /pipeline/{id}` - Get current state
- `GET /pipeline/{id}/report` - Get layered report (text)
- `GET /pipeline/{id}/report/json` - Get report as JSON
- `POST /pipeline/{id}/approve` - Approve/reject
- `DELETE /pipeline/{id}` - Delete pipeline

### Impact Q&A
- `POST /impact/analyze` - Interactive impact analysis
- `GET /impact/search` - Search symbols

### Graph
- `GET /graph/overview` - System overview
- `GET /graph/service/{name}` - Service details

## Running

```bash
cd forge
python -m venv venv
.\venv\Scripts\activate  # Windows
pip install -r requirements.txt

# Set API key in .env
echo GOOGLE_API_KEY=your-key >> .env

# Run
python main.py
```

## Example Usage

```bash
# Start pipeline
curl -X POST http://localhost:8000/pipeline/start \
  -H "Content-Type: application/json" \
  -d '{"message": "Add fraud detection - reject payments where sender made >5 in last 10 minutes"}'

# Get report
curl http://localhost:8000/pipeline/{id}/report
```

## Report Format

```
════════════════════════════════════════════════════════════════
LAYER 0 — Directly required by the requirement
════════════════════════════════════════════════════════════════

SERVICE: validation-service  [conf: 100%  evidence: contract]
│
├── FILE: src/rules/ruleEngine.js
│   └── ADD handler: _checkFraudVelocity
│       WHY: new rule to check payment velocity
│       CHANGE: register under 'FRAUD_VELOCITY_CHECK'
│
...

════════════════════════════════════════════════════════════════
EXECUTION ORDER
════════════════════════════════════════════════════════════════

  1. audit-service       ← no dependencies
  2. validation-service  ← depends on audit-service
  3. payment-processor   ← depends on validation-service
  4. gateway-service     ← depends on payment-processor

════════════════════════════════════════════════════════════════
SUMMARY
════════════════════════════════════════════════════════════════

  Total: 4 services, 8 files, 10 function-level changes
  Confidence: HIGH (all callers traced)
```
