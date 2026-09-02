# Step 1: Microservices + Contracts — Final Plan

**Date:** 2026-09-02  
**Status:** FINAL — Ready for Implementation

---

## Overview

Build a **functional cross-border wire transfer application** with 7 independent microservices + UI. This application is the **target system** that will be:
- Analyzed by the code graph (Step 2)
- Modified by AI agents (Step 4)
- Verified by the harness (Step 5)

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Services** | 7 independent services | Each is a separate repo |
| **HUB/WOLF** | Mocked inline (not separate services) | Real systems are external, we simulate |
| **Shared code** | Within each service only | No cross-service shared libraries |
| **Communication** | HTTP only | Simple, synchronous |
| **Database** | SQLite per service | Zero config, file-based |
| **Language** | Plain JavaScript (ES6+) | Simpler, faster to build |
| **UI** | Simple HTML + CSS + JS | Focus is on backend |

---

## Architecture

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

---

## 7 Services — Detailed Specification

### 1. Gateway Service (Port 3000)

**Responsibility:** Single entry point for UI, routes requests to appropriate services.

```
gateway-service/
├── src/
│   ├── index.js                 # Express app entry
│   ├── routes/
│   │   ├── payments.js          # /api/payments/* → payment-processor
│   │   ├── accounts.js          # /api/accounts/* → account-service
│   │   └── fx.js                # /api/fx/* → fx-service
│   ├── middleware/
│   │   ├── requestLogger.js     # Log all requests
│   │   ├── errorHandler.js      # Global error handling
│   │   └── requestId.js         # Add unique request ID
│   └── utils/
│       ├── httpClient.js        # Make HTTP calls to other services
│       └── responseFormatter.js # Standard response format
├── contracts/
│   └── openapi.yaml
├── package.json
├── Dockerfile
└── README.md
```

**APIs:**
| Method | Endpoint | Routes To |
|--------|----------|-----------|
| POST | /api/payments | payment-processor |
| GET | /api/payments | payment-processor |
| GET | /api/payments/:id | payment-processor |
| GET | /api/accounts | account-service |
| GET | /api/accounts/:id | account-service |
| POST | /api/accounts | account-service |
| GET | /api/fx/rates | fx-service |
| POST | /api/fx/convert | fx-service |

---

### 2. Account Service (Port 3001)

**Responsibility:** Manage accounts, balances. This is our internal account database (NOT the external HUB).

```
account-service/
├── src/
│   ├── index.js
│   ├── routes/
│   │   └── accounts.js
│   ├── services/
│   │   ├── accountService.js    # Business logic
│   │   └── balanceService.js    # Balance operations
│   ├── repositories/
│   │   └── accountRepository.js # Database access
│   ├── utils/
│   │   ├── validators.js        # Validate account data
│   │   ├── formatters.js        # Format account numbers
│   │   └── ibanGenerator.js     # Generate/validate IBAN
│   └── db/
│       ├── database.js          # SQLite connection
│       ├── schema.sql           # Table definitions
│       └── seed.sql             # Pre-seeded accounts
├── contracts/
│   └── openapi.yaml
├── package.json
├── Dockerfile
└── README.md
```

**APIs:**
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /accounts | List all accounts |
| GET | /accounts/:id | Get account by ID |
| POST | /accounts | Create new account |
| GET | /accounts/:id/balance | Get current balance |
| PUT | /accounts/:id/balance | Update balance (internal) |
| POST | /accounts/lookup | Find by account number + bank code |

**Database Schema:**
```sql
CREATE TABLE accounts (
  id TEXT PRIMARY KEY,
  account_number TEXT UNIQUE NOT NULL,
  bank_code TEXT NOT NULL,
  holder_name TEXT NOT NULL,
  currency TEXT NOT NULL,
  balance REAL DEFAULT 0,
  country TEXT NOT NULL,
  status TEXT DEFAULT 'ACTIVE',
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

**Pre-seeded Accounts (5):**
| ID | Holder | Account Number | Bank Code | Currency | Balance | Country |
|----|--------|----------------|-----------|----------|---------|---------|
| ACC001 | John Doe | GB82WEST12345698765432 | WESTGB2L | GBP | 50,000 | GB |
| ACC002 | Jane Smith | DE89370400440532013000 | COBADEFF | EUR | 75,000 | DE |
| ACC003 | Bob Wilson | US12345678901234567890 | CHASUS33 | USD | 100,000 | US |
| ACC004 | Alice Chen | SG1234567890123456 | DBSSSGSG | SGD | 45,000 | SG |
| ACC005 | Carlos Garcia | ES9121000418450200051332 | CAIXESBB | EUR | 30,000 | ES |

---

### 3. Payment Processor (Port 3002)

**Responsibility:** Core payment orchestration. Coordinates all steps of a cross-border wire transfer. Contains mocked HUB/WOLF clients.

```
payment-processor/
├── src/
│   ├── index.js
│   ├── routes/
│   │   └── payments.js
│   ├── services/
│   │   ├── paymentService.js    # CRUD operations
│   │   └── orchestrator.js      # Payment flow orchestration
│   ├── clients/
│   │   ├── accountClient.js     # Calls account-service
│   │   ├── validationClient.js  # Calls validation-service
│   │   ├── fxClient.js          # Calls fx-service
│   │   ├── ledgerClient.js      # Calls ledger-service
│   │   ├── auditClient.js       # Calls audit-service
│   │   ├── mockHubClient.js     # MOCK: External HUB system
│   │   └── mockWolfClient.js    # MOCK: External WOLF sanctions
│   ├── repositories/
│   │   └── paymentRepository.js
│   ├── utils/
│   │   ├── paymentIdGenerator.js # Generate PMT-YYYY-NNNNN
│   │   ├── statusManager.js      # Manage status transitions
│   │   ├── amountCalculator.js   # Calculate fees, totals
│   │   └── validators.js         # Validate payment data
│   └── db/
│       ├── database.js
│       └── schema.sql
├── contracts/
│   └── openapi.yaml
├── package.json
├── Dockerfile
└── README.md
```

**APIs:**
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /payments | Initiate new payment |
| GET | /payments | List payments (with filters) |
| GET | /payments/:id | Get payment by ID |
| GET | /payments/:id/status | Get current status |

**Payment Flow (Orchestrator):**
```
1. Receive payment request
2. Generate payment ID
3. Save with status INITIATED
4. Call account-service → Validate sender exists
5. Call account-service → Validate receiver exists
6. Call validation-service → Run business rules
7. Call mockWolfClient → Sanction screening
8. Call fx-service → Get conversion rate (if cross-currency)
9. Calculate fees
10. Call mockHubClient → Verify account can be debited
11. Call account-service → Check sufficient balance
12. Call ledger-service → Create ledger entries
13. Call account-service → Debit sender
14. Call account-service → Credit receiver
15. Update status to COMPLETED
16. Call audit-service → Log completion
```

**Mock HUB Client:**
```javascript
// src/clients/mockHubClient.js
// Simulates external HUB (core banking) system
// Returns account verification status

async function verifyAccount(accountNumber, bankCode) {
  // Simulate network delay
  await delay(100);
  
  // Mock: 95% success rate
  if (Math.random() < 0.95) {
    return { verified: true, message: 'Account verified by HUB' };
  }
  return { verified: false, message: 'HUB verification failed' };
}
```

**Mock WOLF Client:**
```javascript
// src/clients/mockWolfClient.js
// Simulates external WOLF (sanctions screening) system
// Returns screening result

async function screenPayment(sender, receiver, amount) {
  // Simulate network delay
  await delay(200);
  
  // Mock: Check against fake blocklist
  const blockedCountries = ['NK', 'IR', 'SY'];
  if (blockedCountries.includes(sender.country) || 
      blockedCountries.includes(receiver.country)) {
    return { result: 'HIT', reason: 'Blocked country' };
  }
  
  // Mock: 2% random hit rate for demo
  if (Math.random() < 0.02) {
    return { result: 'HIT', reason: 'Name match on sanctions list' };
  }
  
  return { result: 'CLEAR', message: 'No sanctions hits' };
}
```

**Database Schema:**
```sql
CREATE TABLE payments (
  id TEXT PRIMARY KEY,
  payment_id TEXT UNIQUE NOT NULL,
  sender_account_id TEXT NOT NULL,
  receiver_account_id TEXT NOT NULL,
  amount REAL NOT NULL,
  currency TEXT NOT NULL,
  target_amount REAL,
  target_currency TEXT,
  fx_rate REAL,
  fee_amount REAL DEFAULT 0,
  status TEXT DEFAULT 'INITIATED',
  failure_reason TEXT,
  reference TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE payment_status_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  payment_id TEXT NOT NULL,
  status TEXT NOT NULL,
  message TEXT,
  timestamp TEXT DEFAULT CURRENT_TIMESTAMP
);
```

---

### 4. Validation Service (Port 3003)

**Responsibility:** Business rules engine. Validates payments against configurable rules.

```
validation-service/
├── src/
│   ├── index.js
│   ├── routes/
│   │   └── validation.js
│   ├── services/
│   │   └── validationService.js  # Run all rules
│   ├── rules/
│   │   ├── ruleEngine.js         # Rule execution engine
│   │   ├── amountLimitRule.js    # Single/daily amount limits
│   │   ├── currencyRule.js       # Allowed currency pairs
│   │   ├── countryRule.js        # Blocked countries
│   │   └── duplicateRule.js      # Duplicate detection
│   ├── repositories/
│   │   └── ruleRepository.js
│   ├── utils/
│   │   ├── ruleLoader.js         # Load rules from DB
│   │   └── validators.js         # Input validation
│   └── db/
│       ├── database.js
│       ├── schema.sql
│       └── seed.sql              # Pre-configured rules
├── contracts/
│   └── openapi.yaml
├── package.json
├── Dockerfile
└── README.md
```

**APIs:**
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /validate | Validate payment against all rules |
| GET | /rules | List all rules |
| GET | /rules/:id | Get rule details |

**Validation Response:**
```json
{
  "valid": false,
  "rulesChecked": ["AMOUNT_LIMIT", "CURRENCY", "COUNTRY", "DUPLICATE"],
  "rulesPassed": ["CURRENCY", "COUNTRY", "DUPLICATE"],
  "rulesFailed": [
    {
      "code": "AMOUNT_LIMIT",
      "message": "Amount 60000 GBP exceeds single transaction limit of 50000"
    }
  ],
  "warnings": []
}
```

**Pre-configured Rules:**
| Rule Code | Description | Parameters |
|-----------|-------------|------------|
| AMOUNT_LIMIT_SINGLE | Max per transaction | GBP:50000, EUR:60000, USD:50000 |
| AMOUNT_LIMIT_DAILY | Max daily per account | GBP:250000, EUR:300000, USD:250000 |
| BLOCKED_COUNTRIES | Restricted destinations | NK, IR, SY, CU |
| CURRENCY_PAIRS | Allowed conversions | GBP↔EUR, GBP↔USD, EUR↔USD |
| DUPLICATE_WINDOW | Same payment window | 5 minutes |

---

### 5. Ledger Service (Port 3004)

**Responsibility:** Double-entry bookkeeping. Creates debit/credit entries for every payment.

```
ledger-service/
├── src/
│   ├── index.js
│   ├── routes/
│   │   └── ledger.js
│   ├── services/
│   │   └── ledgerService.js      # Create entries
│   ├── repositories/
│   │   └── entryRepository.js
│   ├── utils/
│   │   ├── entryIdGenerator.js   # Generate entry IDs
│   │   ├── balanceCalculator.js  # Calculate running balance
│   │   └── validators.js
│   └── db/
│       ├── database.js
│       └── schema.sql
├── contracts/
│   └── openapi.yaml
├── package.json
├── Dockerfile
└── README.md
```

**APIs:**
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /entries | Create ledger entries for payment |
| GET | /entries | List entries (with filters) |
| GET | /entries/payment/:paymentId | Get entries for payment |
| GET | /entries/account/:accountId | Get entries for account |

**Double-Entry Logic:**
```
For payment of 1000 GBP → 1150 EUR:

Entry 1: DEBIT  sender   1000 GBP  (reduces sender balance)
Entry 2: CREDIT receiver 1150 EUR  (increases receiver balance)
Entry 3: CREDIT fees     15 GBP    (bank fee revenue)
```

**Database Schema:**
```sql
CREATE TABLE ledger_entries (
  id TEXT PRIMARY KEY,
  entry_id TEXT UNIQUE NOT NULL,
  payment_id TEXT NOT NULL,
  account_id TEXT NOT NULL,
  entry_type TEXT NOT NULL,  -- DEBIT or CREDIT
  amount REAL NOT NULL,
  currency TEXT NOT NULL,
  balance_before REAL,
  balance_after REAL,
  description TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

---

### 6. FX Service (Port 3005)

**Responsibility:** Currency conversion rates and calculations.

```
fx-service/
├── src/
│   ├── index.js
│   ├── routes/
│   │   └── fx.js
│   ├── services/
│   │   ├── rateService.js        # Get/manage rates
│   │   └── conversionService.js  # Convert amounts
│   ├── repositories/
│   │   └── rateRepository.js
│   ├── utils/
│   │   ├── rateCalculator.js     # Apply markup
│   │   ├── currencyValidator.js  # Validate currency codes
│   │   └── rounder.js            # Round to 2 decimals
│   └── db/
│       ├── database.js
│       ├── schema.sql
│       └── seed.sql              # Pre-seeded rates
├── contracts/
│   └── openapi.yaml
├── package.json
├── Dockerfile
└── README.md
```

**APIs:**
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /rates | Get all current rates |
| GET | /rates/:from/:to | Get specific rate |
| POST | /convert | Convert amount |

**Conversion Response:**
```json
{
  "from": "GBP",
  "to": "EUR",
  "originalAmount": 1000,
  "convertedAmount": 1145.00,
  "baseRate": 1.15,
  "markup": 0.005,
  "effectiveRate": 1.145,
  "markupAmount": 5.00
}
```

**Pre-seeded FX Rates:**
| From | To | Rate |
|------|----|------|
| GBP | EUR | 1.15 |
| GBP | USD | 1.27 |
| GBP | SGD | 1.68 |
| EUR | GBP | 0.87 |
| EUR | USD | 1.10 |
| EUR | SGD | 1.46 |
| USD | GBP | 0.79 |
| USD | EUR | 0.91 |
| USD | SGD | 1.33 |

---

### 7. Audit Service (Port 3006)

**Responsibility:** Compliance logging, audit trail for all payment actions.

```
audit-service/
├── src/
│   ├── index.js
│   ├── routes/
│   │   └── audit.js
│   ├── services/
│   │   └── auditService.js       # Log audit events
│   ├── repositories/
│   │   └── auditRepository.js
│   ├── utils/
│   │   ├── eventFormatter.js     # Format audit events
│   │   ├── hashGenerator.js      # Generate integrity hash
│   │   └── validators.js
│   └── db/
│       ├── database.js
│       └── schema.sql
├── contracts/
│   └── openapi.yaml
├── package.json
├── Dockerfile
└── README.md
```

**APIs:**
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /events | Log audit event |
| GET | /events | List events (with filters) |
| GET | /events/payment/:paymentId | Get events for payment |
| GET | /events/account/:accountId | Get events for account |

**Audit Event Types:**
| Event | Description |
|-------|-------------|
| PAYMENT_INITIATED | Payment created |
| PAYMENT_VALIDATED | Passed validation rules |
| PAYMENT_SCREENED | Sanctions screening complete |
| PAYMENT_PROCESSED | FX and fees calculated |
| PAYMENT_POSTED | Ledger entries created |
| PAYMENT_COMPLETED | Payment successful |
| PAYMENT_FAILED | Payment failed (with reason) |
| PAYMENT_REJECTED | Rejected by rules/screening |
| ACCOUNT_CREATED | New account created |
| ACCOUNT_DEBITED | Account debited |
| ACCOUNT_CREDITED | Account credited |

**Database Schema:**
```sql
CREATE TABLE audit_events (
  id TEXT PRIMARY KEY,
  event_id TEXT UNIQUE NOT NULL,
  event_type TEXT NOT NULL,
  entity_type TEXT NOT NULL,  -- PAYMENT, ACCOUNT, etc.
  entity_id TEXT NOT NULL,
  actor TEXT,                  -- Who triggered (user/system)
  details TEXT,                -- JSON details
  integrity_hash TEXT,         -- SHA256 for tamper detection
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

---

### 8. Payment UI (Port 8080)

**Responsibility:** User interface for the payment application.

```
payment-ui/
├── public/
│   ├── index.html
│   ├── css/
│   │   └── styles.css
│   └── js/
│       ├── app.js               # Main application
│       ├── api.js               # API client
│       ├── pages/
│       │   ├── dashboard.js
│       │   ├── accounts.js
│       │   ├── newPayment.js
│       │   └── paymentHistory.js
│       └── utils/
│           ├── formatters.js
│           └── validators.js
├── package.json                 # Simple HTTP server
├── Dockerfile
└── README.md
```

**Screens:**
1. **Dashboard** — Account summary, recent payments
2. **Accounts** — List accounts, create new
3. **New Payment** — Payment form with preview
4. **Payment History** — List all payments with status
5. **Payment Detail** — Status timeline, full details

---

## Inter-Service Communication

### Payment Flow — HTTP Calls

```
┌──────┐     ┌─────────┐     ┌───────────┐     ┌─────────┐     ┌───────────┐
│  UI  │────▶│ Gateway │────▶│ Payment   │────▶│ Account │     │ Validation│
│      │     │         │     │ Processor │     │ Service │     │  Service  │
└──────┘     └─────────┘     └───────────┘     └─────────┘     └───────────┘
                                   │                                │
                                   │  1. Lookup sender              │
                                   │────────────────────────────────│
                                   │◀────────────────────────────────│
                                   │                                │
                                   │  2. Lookup receiver            │
                                   │────────────────────────────────│
                                   │◀────────────────────────────────│
                                   │                                │
                                   │  3. Validate payment           │
                                   │─────────────────────────────────────────────▶│
                                   │◀─────────────────────────────────────────────│
                                   │
                                   │  4. Screen (WOLF mock - internal)
                                   │
                                   │  5. Get FX rate ─────────────────────────────────────┐
                                   │◀──────────────────────────────────────────────────────│ FX Service
                                   │
                                   │  6. Verify with HUB (mock - internal)
                                   │
                                   │  7. Check balance ─────────────▶│ Account Service
                                   │◀────────────────────────────────│
                                   │
                                   │  8. Create entries ────────────────────────────────────┐
                                   │◀───────────────────────────────────────────────────────│ Ledger Service
                                   │
                                   │  9. Debit sender ──────────────▶│ Account Service
                                   │  10. Credit receiver ──────────▶│
                                   │
                                   │  11. Log completion ───────────────────────────────────┐
                                   │                                                        │ Audit Service
```

---

## Service Dependencies Matrix

| Service | Calls | Called By |
|---------|-------|-----------|
| gateway-service | account, payment-processor, fx | UI |
| account-service | — | gateway, payment-processor |
| payment-processor | account, validation, fx, ledger, audit | gateway |
| validation-service | — | payment-processor |
| ledger-service | — | payment-processor |
| fx-service | — | gateway, payment-processor |
| audit-service | — | payment-processor |

---

## Payment Status Flow

```
INITIATED
    │
    ▼
VALIDATING ─────────────────────────────┐
    │                                   │
    │ (rules passed)                    │ (rules failed)
    ▼                                   ▼
SCREENING                            REJECTED
    │
    │ (CLEAR)              (HIT)
    ▼                        │
PROCESSING                   ▼
    │                     ON_HOLD
    │ (FX + fees OK)
    ▼
POSTING
    │
    │ (ledger OK)
    ▼
COMPLETING
    │
    │ (balance updated)
    ▼
COMPLETED

(Any step can → FAILED with reason)
```

---

## Folder Structure (Complete)

```
payment-system/
│
├── gateway-service/
│   ├── src/
│   │   ├── index.js
│   │   ├── routes/
│   │   ├── middleware/
│   │   └── utils/
│   ├── contracts/
│   │   └── openapi.yaml
│   ├── package.json
│   ├── Dockerfile
│   └── README.md
│
├── account-service/
│   ├── src/
│   │   ├── index.js
│   │   ├── routes/
│   │   ├── services/
│   │   ├── repositories/
│   │   ├── utils/
│   │   └── db/
│   ├── contracts/
│   │   └── openapi.yaml
│   ├── package.json
│   ├── Dockerfile
│   └── README.md
│
├── payment-processor/
│   ├── src/
│   │   ├── index.js
│   │   ├── routes/
│   │   ├── services/
│   │   ├── clients/
│   │   ├── repositories/
│   │   ├── utils/
│   │   └── db/
│   ├── contracts/
│   │   └── openapi.yaml
│   ├── package.json
│   ├── Dockerfile
│   └── README.md
│
├── validation-service/
│   ├── src/
│   │   ├── index.js
│   │   ├── routes/
│   │   ├── services/
│   │   ├── rules/
│   │   ├── repositories/
│   │   ├── utils/
│   │   └── db/
│   ├── contracts/
│   │   └── openapi.yaml
│   ├── package.json
│   ├── Dockerfile
│   └── README.md
│
├── ledger-service/
│   ├── src/
│   │   ├── index.js
│   │   ├── routes/
│   │   ├── services/
│   │   ├── repositories/
│   │   ├── utils/
│   │   └── db/
│   ├── contracts/
│   │   └── openapi.yaml
│   ├── package.json
│   ├── Dockerfile
│   └── README.md
│
├── fx-service/
│   ├── src/
│   │   ├── index.js
│   │   ├── routes/
│   │   ├── services/
│   │   ├── repositories/
│   │   ├── utils/
│   │   └── db/
│   ├── contracts/
│   │   └── openapi.yaml
│   ├── package.json
│   ├── Dockerfile
│   └── README.md
│
├── audit-service/
│   ├── src/
│   │   ├── index.js
│   │   ├── routes/
│   │   ├── services/
│   │   ├── repositories/
│   │   ├── utils/
│   │   └── db/
│   ├── contracts/
│   │   └── openapi.yaml
│   ├── package.json
│   ├── Dockerfile
│   └── README.md
│
├── payment-ui/
│   ├── public/
│   │   ├── index.html
│   │   ├── css/
│   │   └── js/
│   ├── package.json
│   ├── Dockerfile
│   └── README.md
│
├── docker-compose.yaml
└── README.md
```

---

## Implementation Order

| Order | Service | Reason |
|-------|---------|--------|
| 1 | account-service | Foundation — other services depend on accounts |
| 2 | fx-service | Independent, simple |
| 3 | validation-service | Independent, rules engine |
| 4 | ledger-service | Independent, bookkeeping |
| 5 | audit-service | Independent, logging |
| 6 | payment-processor | Core — integrates all others |
| 7 | gateway-service | Routes to all services |
| 8 | payment-ui | Uses gateway |

---

## Next Steps

1. ✅ Plan finalized
2. → Create folder structure
3. → Build account-service
4. → Build remaining services in order
5. → Build gateway-service
6. → Build payment-ui
7. → Test end-to-end flow
8. → Create OpenAPI contracts
