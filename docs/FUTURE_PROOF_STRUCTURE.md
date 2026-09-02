# Payment Application — Future-Proof Structure

**Goal:** Structure that easily accommodates adding new services, APIs, features, or integrations without restructuring.

---

## Current State vs Future-Proof

### Problem with Current Structure
```
services/
├── account-service/      # Service 1
├── payment-processor/    # Service 2
├── ...                   # Flat list of services
```

**Issues:**
- All services at same level — no logical grouping
- No clear place for shared contracts, schemas, or libs
- No separation between core vs supporting services
- Hard to add new service types (batch, streaming, etc.)

---

## Proposed Future-Proof Structure

```
project-root/
│
├── apps/                           # All runnable applications
│   ├── services/                   # Microservices (backend)
│   │   ├── core/                   # Core business services
│   │   │   ├── account-service/
│   │   │   ├── payment-processor/
│   │   │   └── ledger-service/
│   │   │
│   │   ├── support/                # Supporting services
│   │   │   ├── validation-service/
│   │   │   ├── fx-service/
│   │   │   └── audit-service/
│   │   │
│   │   ├── gateway/                # API gateways
│   │   │   └── gateway-service/
│   │   │
│   │   └── integration/            # External integrations (future)
│   │       ├── hub-adapter/        # Real HUB integration (future)
│   │       └── wolf-adapter/       # Real WOLF integration (future)
│   │
│   ├── web/                        # Frontend applications
│   │   ├── payment-ui/             # Customer-facing UI
│   │   └── admin-ui/               # Admin dashboard (future)
│   │
│   ├── batch/                      # Batch jobs (future)
│   │   ├── reconciliation/
│   │   └── reporting/
│   │
│   └── workers/                    # Background workers (future)
│       ├── notification-worker/
│       └── settlement-worker/
│
├── packages/                       # Shared libraries
│   ├── contracts/                  # OpenAPI specs, schemas
│   │   ├── openapi/
│   │   │   ├── account-service.yaml
│   │   │   ├── payment-processor.yaml
│   │   │   └── ...
│   │   └── schemas/                # Shared JSON schemas
│   │       ├── Payment.json
│   │       ├── Account.json
│   │       └── ...
│   │
│   ├── common/                     # Shared utilities (optional)
│   │   ├── errors/
│   │   ├── logging/
│   │   └── http-client/
│   │
│   └── test-utils/                 # Shared test utilities
│       ├── fixtures/
│       └── mocks/
│
├── infrastructure/                 # Infrastructure as code
│   ├── docker/
│   │   ├── docker-compose.yaml
│   │   ├── docker-compose.dev.yaml
│   │   └── docker-compose.test.yaml
│   │
│   ├── kubernetes/                 # K8s manifests (future)
│   │   ├── base/
│   │   └── overlays/
│   │
│   └── terraform/                  # Cloud infra (future)
│
├── tools/                          # Development tools
│   ├── harness/                    # AI Development Harness (Steps 2-5)
│   │   ├── core/
│   │   ├── graph/
│   │   ├── analyzer/
│   │   ├── agents/
│   │   ├── verifier/
│   │   └── governance/
│   │
│   ├── scripts/                    # Utility scripts
│   │   ├── setup.sh
│   │   ├── seed-data.js
│   │   └── generate-contracts.js
│   │
│   └── generators/                 # Code generators (future)
│       ├── service-template/
│       └── api-template/
│
├── docs/                           # Documentation
│   ├── architecture/
│   │   ├── overview.md
│   │   ├── service-map.md
│   │   └── data-flow.md
│   │
│   ├── api/                        # API documentation
│   │   └── generated/              # Auto-generated from OpenAPI
│   │
│   ├── guides/
│   │   ├── USER_GUIDE.md
│   │   ├── DEVELOPER_GUIDE.md
│   │   └── DEPLOYMENT_GUIDE.md
│   │
│   └── decisions/                  # Architecture Decision Records
│       ├── ADR-001-microservices.md
│       └── ADR-002-http-only.md
│
├── config/                         # Global configuration
│   ├── services.yaml               # Service registry
│   ├── environments/
│   │   ├── development.yaml
│   │   ├── staging.yaml
│   │   └── production.yaml
│   └── feature-flags.yaml
│
├── .github/                        # CI/CD (GitHub Actions)
│   └── workflows/
│       ├── ci.yaml
│       ├── deploy.yaml
│       └── pr-check.yaml
│
├── start.bat                       # Windows startup
├── start.sh                        # Linux/Mac startup
├── stop.bat
├── install.bat
├── package.json                    # Root package (workspaces)
└── README.md
```

---

## Key Design Principles

### 1. **Logical Grouping by Purpose**

```
apps/
├── services/           # Backend microservices
│   ├── core/           # Core business logic
│   ├── support/        # Supporting services
│   ├── gateway/        # API gateways
│   └── integration/    # External system adapters
├── web/                # Frontend apps
├── batch/              # Batch processing
└── workers/            # Background workers
```

**Why:** Easy to find things, clear ownership, scales with team size.

### 2. **Shared Contracts in One Place**

```
packages/contracts/
├── openapi/            # All OpenAPI specs
└── schemas/            # Shared data schemas
```

**Why:** 
- Single source of truth for API contracts
- Harness can easily scan all contracts
- Prevents drift between services

### 3. **Tools Separate from Application**

```
tools/
├── harness/            # AI Development Harness
├── scripts/            # Utility scripts
└── generators/         # Code generators
```

**Why:** 
- Clear separation of concerns
- Tools evolve independently
- Easy to add new tools

### 4. **Infrastructure as Code**

```
infrastructure/
├── docker/             # Local development
├── kubernetes/         # Container orchestration
└── terraform/          # Cloud resources
```

**Why:**
- Reproducible environments
- Version-controlled infrastructure
- Easy to add new environments

---

## Adding New Components

### Adding a New Service

```bash
# 1. Decide category: core, support, gateway, or integration
# 2. Create folder:
mkdir -p apps/services/support/notification-service

# 3. Use standard structure inside:
notification-service/
├── src/
│   ├── index.js
│   ├── routes/
│   ├── services/
│   ├── repositories/
│   ├── utils/
│   └── db/
├── contracts/
│   └── openapi.yaml      # Also copy to packages/contracts/openapi/
├── package.json
├── Dockerfile
└── README.md

# 4. Register in config/services.yaml
# 5. Update docker-compose
```

### Adding a New API Endpoint

```bash
# 1. Add route in the service:
# apps/services/core/account-service/src/routes/newEndpoint.js

# 2. Update OpenAPI spec:
# packages/contracts/openapi/account-service.yaml

# 3. Harness will auto-detect via graph rebuild
```

### Adding a New Frontend App

```bash
# Create under apps/web/
mkdir -p apps/web/mobile-app
mkdir -p apps/web/partner-portal
```

### Adding a New External Integration

```bash
# Create adapter service under apps/services/integration/
mkdir -p apps/services/integration/swift-adapter
mkdir -p apps/services/integration/blockchain-connector
```

### Adding a Batch Job

```bash
mkdir -p apps/batch/eod-settlement
mkdir -p apps/batch/monthly-statements
```

---

## Service Template

Every service follows this internal structure:

```
{service-name}/
├── src/
│   ├── index.js              # Entry point
│   ├── app.js                # Express app setup
│   │
│   ├── routes/               # API routes (thin layer)
│   │   ├── index.js          # Route aggregator
│   │   └── {resource}.js     # Resource routes
│   │
│   ├── controllers/          # Request handlers (optional)
│   │   └── {resource}Controller.js
│   │
│   ├── services/             # Business logic
│   │   └── {resource}Service.js
│   │
│   ├── repositories/         # Data access
│   │   └── {resource}Repository.js
│   │
│   ├── clients/              # HTTP clients to other services
│   │   └── {service}Client.js
│   │
│   ├── models/               # Data models (if ORM)
│   │   └── {Entity}.js
│   │
│   ├── middleware/           # Express middleware
│   │   ├── auth.js
│   │   ├── validation.js
│   │   └── errorHandler.js
│   │
│   ├── utils/                # Utilities (internal to service)
│   │   ├── validators.js
│   │   ├── formatters.js
│   │   └── constants.js
│   │
│   ├── db/                   # Database
│   │   ├── database.js       # Connection setup
│   │   ├── migrations/       # Schema migrations
│   │   └── seeds/            # Seed data
│   │
│   └── config/               # Service config
│       └── index.js
│
├── tests/                    # Tests
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│
├── contracts/                # Service contract
│   └── openapi.yaml
│
├── package.json
├── Dockerfile
├── .env.example
└── README.md
```

---

## Configuration: services.yaml

Central registry of all services:

```yaml
# config/services.yaml
version: "1.0"

services:
  # Core services
  core:
    account-service:
      port: 3001
      path: apps/services/core/account-service
      database: sqlite
      dependencies: []
      
    payment-processor:
      port: 3002
      path: apps/services/core/payment-processor
      database: sqlite
      dependencies:
        - account-service
        - validation-service
        - fx-service
        - ledger-service
        - audit-service
      mocks:
        - hub
        - wolf
        
    ledger-service:
      port: 3004
      path: apps/services/core/ledger-service
      database: sqlite
      dependencies: []

  # Support services
  support:
    validation-service:
      port: 3003
      path: apps/services/support/validation-service
      database: sqlite
      
    fx-service:
      port: 3005
      path: apps/services/support/fx-service
      database: sqlite
      
    audit-service:
      port: 3006
      path: apps/services/support/audit-service
      database: sqlite

  # Gateway
  gateway:
    gateway-service:
      port: 3000
      path: apps/services/gateway/gateway-service
      routes_to:
        - account-service
        - payment-processor
        - fx-service
        - audit-service

  # Future integrations (placeholder)
  integration: {}

# Web apps
web:
  payment-ui:
    port: 8080
    path: apps/web/payment-ui
    api_gateway: gateway-service

# Future batch jobs (placeholder)
batch: {}

# Future workers (placeholder)
workers: {}
```

---

## Benefits

| Scenario | How Structure Handles It |
|----------|-------------------------|
| Add new microservice | Create folder under `apps/services/{category}/` |
| Add mobile app | Create under `apps/web/` |
| Add batch job | Create under `apps/batch/` |
| Add real HUB integration | Create under `apps/services/integration/` |
| Share schema across services | Put in `packages/contracts/schemas/` |
| Add deployment scripts | Put in `infrastructure/` |
| Add AI tool | Put in `tools/` |
| Document architecture | Put in `docs/architecture/` |

---

## Migration Plan (From Current to Future-Proof)

```bash
# Current:
services/
├── account-service/
├── payment-processor/
├── validation-service/
├── ledger-service/
├── fx-service/
├── audit-service/
├── gateway-service/
└── payment-ui/

# Step 1: Create new structure
mkdir -p apps/services/core
mkdir -p apps/services/support
mkdir -p apps/services/gateway
mkdir -p apps/web
mkdir -p packages/contracts/openapi
mkdir -p infrastructure/docker
mkdir -p tools
mkdir -p docs/architecture

# Step 2: Move services
mv services/account-service apps/services/core/
mv services/payment-processor apps/services/core/
mv services/ledger-service apps/services/core/
mv services/validation-service apps/services/support/
mv services/fx-service apps/services/support/
mv services/audit-service apps/services/support/
mv services/gateway-service apps/services/gateway/
mv services/payment-ui apps/web/

# Step 3: Move infrastructure
mv services/docker-compose.yaml infrastructure/docker/

# Step 4: Move docs
mv docs/* docs/guides/

# Step 5: Update import paths / references
```

---

## Summary

The future-proof structure follows these principles:

1. **Group by purpose** — `apps/services/core`, `apps/services/support`, `apps/web`, `apps/batch`
2. **Shared contracts centralized** — `packages/contracts/`
3. **Tools separate** — `tools/harness/`, `tools/scripts/`
4. **Infrastructure as code** — `infrastructure/`
5. **Clear documentation** — `docs/architecture/`, `docs/guides/`
6. **Single service registry** — `config/services.yaml`

This allows adding any new service, app, integration, or tool without restructuring existing code.
