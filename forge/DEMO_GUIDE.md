# Forge AI Code Graph - Demo Guide

## Quick Start
```bash
cd forge
python main.py
# Opens at http://localhost:8000
```

---

## Demo Scenarios

### 1. Add Retry Logic to Payment Gateway
**Best for:** Showing cross-service impact analysis

**Flow:**
1. Dashboard → Click "Make Changes to Codebase"
2. Type: `Add retry logic to payment gateway`
3. Agent asks: "Which service?" → Reply: `payment-processor`
4. Agent asks: "Which function?" → Reply: `processPayment`
5. Review requirements → Click "Confirm & Start Analysis"
6. Watch pipeline with live logs
7. View results: 7 services impacted, execution order, shared interface changes

**Key talking points:**
- Layer 0: Direct change to `PaymentOrchestrator.processPayment`
- Layer 1: 6 downstream services (gateway, account, audit, fx, ledger, validation)
- Suggests new error code: `PAYMENT_TEMPORARY_UNAVAILABLE (HTTP 503)`
- Recommends config: `PAYMENT_RETRY_MAX_ATTEMPTS=3`

---

### 2. Deprecate Old Auth Endpoint
**Best for:** Showing caller discovery

**Flow:**
1. Dashboard → "Make Changes to Codebase"
2. Type: `Deprecate the old auth endpoint`
3. Agent asks: "Which service?" → Reply: `gateway-service`
4. Agent asks: "Which endpoint?" → Reply: `/auth/login`
5. Confirm → Run analysis

**Key talking points:**
- Finds all callers of the deprecated endpoint
- Shows migration path for dependent services
- Identifies breaking changes

---

### 3. Add Logging to All API Calls
**Best for:** Showing broad cross-cutting changes

**Flow:**
1. Dashboard → "Make Changes to Codebase"
2. Type: `Add logging to all API calls`
3. Agent asks: "Which service?" → Reply: `all services` or `payment-processor`
4. Agent asks: "What level of logging?" → Reply: `request/response with timing`
5. Confirm → Run analysis

**Key talking points:**
- Shows how a cross-cutting concern affects multiple layers
- Identifies performance implications
- Suggests logging patterns and audit-service integration

---

### 4. Add Currency Conversion Validation
**Best for:** Showing service mesh understanding

**Flow:**
1. Dashboard → "Make Changes to Codebase"
2. Type: `Add validation before currency conversion`
3. Agent asks: "Which service?" → Reply: `fx-service`
4. Agent asks: "What validation?" → Reply: `validate currency pairs before conversion`
5. Confirm → Run analysis

**Key talking points:**
- Shows fx-service dependencies
- Identifies callers: payment-processor
- Suggests validation rules and error handling

---

### 5. Add Account Balance Check Before Payment
**Best for:** Showing transactional dependencies

**Flow:**
1. Dashboard → "Make Changes to Codebase"
2. Type: `Add account balance verification before processing payment`
3. Agent asks: "Which service?" → Reply: `payment-processor`
4. Agent asks: "When should this happen?" → Reply: `before calling ledger-service`
5. Confirm → Run analysis

**Key talking points:**
- Shows payment-processor → account-service dependency
- Identifies rollback scenarios
- Suggests idempotency requirements

---

## Graph Explorer Demo

### Show "How it Works" Modal
1. Navigate to Graph Explorer (click "View Graph" from any page)
2. Click "How it works" button (bottom left)
3. Step through 5 stages:
   - **Step 1:** Scan Microservices (8 repos)
   - **Step 2:** Extract Symbols (270 functions)
   - **Step 3:** Map Internal Calls (AST analysis)
   - **Step 4:** Detect HTTP Routes (REST endpoints)
   - **Step 5:** Link Cross-Service (184 connections)
4. Or click "Auto-play" for automated walkthrough

### Explore the Graph
1. Click on service nodes to see details
2. Click "Expand Children" to see functions within a service
3. Use Legend to understand node types:
   - Blue: Services
   - Purple: Functions
   - Dashed lines: HTTP/inferred connections
   - Solid lines: Direct code calls

---

## Demo Tips

### Timing
| Section | Duration |
|---------|----------|
| Dashboard overview | 1 min |
| Chat + requirements gathering | 2-3 min |
| Pipeline execution | 30-60 sec |
| Results walkthrough | 2-3 min |
| Graph explorer + How it Works | 2-3 min |
| **Total** | **8-10 min** |

### Key Stats to Mention
- **8 microservices** indexed
- **270 functions** extracted
- **184 cross-service connections** mapped
- Supports **JavaScript/Node.js** (TypeScript, Python coming)

### Impressive Features to Highlight
1. **Context gathering agent** - Asks clarifying questions before analysis
2. **Live pipeline logs** - Shows real-time backend activity
3. **Layered impact report** - Layer 0 (direct), Layer 1 (callers), Layer 2 (transitive)
4. **Verification loop** - Agent validates its own report against the graph
5. **Execution order** - Tells you which service to modify first
6. **Shared interface changes** - Identifies contracts that need updating

### If Asked About...

**Q: How does it handle multiple languages?**
> Currently optimized for JavaScript/Node.js. The architecture supports pluggable parsers - Python and TypeScript are next.

**Q: How does it discover HTTP connections?**
> We scan for fetch/axios calls and Express route definitions, then match callers to callees based on URL patterns.

**Q: Can it work with our existing repos?**
> Yes - point it at any git repo. It indexes the code and builds the graph automatically.

**Q: How accurate is the impact analysis?**
> The report includes confidence scores. Direct code calls are 100% confident. HTTP inferences are 70-90% based on pattern matching.

---

## Services in the Demo

| Service | Functions | Description |
|---------|-----------|-------------|
| payment-processor | 63 | Core payment orchestration |
| account-service | 42 | Account management & balances |
| validation-service | 47 | Payment validation rules |
| audit-service | 32 | Event logging & compliance |
| ledger-service | 26 | Financial ledger entries |
| fx-service | 25 | Currency conversion |
| gateway-service | 4 | API gateway / entry point |
| payment-ui | 31 | Frontend application |

---

## Troubleshooting

### Backend not starting
```bash
cd forge
pip install -r requirements.txt
python main.py
```

### Frontend changes not showing
```bash
cd forge/frontend
npm run build
# Restart backend
```

### LLM errors
Check that `ANTHROPIC_API_KEY` is set in your environment.
