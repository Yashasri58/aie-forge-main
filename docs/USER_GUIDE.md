# Cross-Border Wire Transfer System

## User Guide & Technical Documentation

---

## Table of Contents

1. [Overview](#overview)
2. [Getting Started](#getting-started)
3. [User Guide - Account Holder](#user-guide---account-holder)
4. [User Guide - Administrator](#user-guide---administrator)
5. [Service Architecture](#service-architecture)
6. [End-to-End Payment Flow](#end-to-end-payment-flow)
7. [API Reference](#api-reference)
8. [Demo Credentials](#demo-credentials)

---

## Overview

This is a microservices-based cross-border wire transfer payment system demonstrating:
- Real-time payment processing with multi-step orchestration
- FX currency conversion
- Sanctions screening (WOLF mock)
- Account verification (HUB mock)
- Double-entry ledger bookkeeping
- Complete audit trail with integrity hashing

### Technology Stack
- **Backend**: Node.js with Express.js
- **Database**: SQLite (per-service)
- **Frontend**: Vanilla HTML/CSS/JavaScript
- **Communication**: HTTP/REST between services

---

## Getting Started

### Prerequisites
- Node.js 18+
- npm

### Starting the Services

```bash
# Navigate to services directory
cd services

# Install dependencies for each service
cd account-service && npm install && cd ..
cd fx-service && npm install && cd ..
cd validation-service && npm install && cd ..
cd ledger-service && npm install && cd ..
cd audit-service && npm install && cd ..
cd payment-processor && npm install && cd ..
cd gateway-service && npm install && cd ..
cd payment-ui && npm install && cd ..

# Start each service (in separate terminals or background)
cd account-service && npm start      # Port 3001
cd fx-service && npm start           # Port 3005
cd validation-service && npm start   # Port 3003
cd ledger-service && npm start       # Port 3004
cd audit-service && npm start        # Port 3006
cd payment-processor && npm start    # Port 3002
cd gateway-service && npm start      # Port 3000
cd payment-ui && npm start           # Port 8080
```

### Accessing the Application

Open your browser and navigate to: **http://localhost:8080**

---

## User Guide - Account Holder

### Logging In

1. Go to http://localhost:8080
2. Select the **"Account Holder"** tab (default)
3. Enter your credentials:
   - **Account Number**: Your IBAN or account number
   - **Bank Code**: Your bank's SWIFT/BIC code
4. Click **"Login to My Account"**

### Dashboard Features

After logging in, you have access to:

#### 💸 New Payment
Create a new wire transfer:
1. Your account is pre-selected as the sender
2. Select the **Receiver Account** from the dropdown
3. Enter the **Amount** to send
4. Select the **Currency** (must match your account currency for best rates)
5. Optionally add a **Payment Reference** (invoice number, description)
6. Click **"📊 Calculate"** to see:
   - Exchange rate (if cross-currency)
   - Transfer fee
   - Total amount to be debited
7. Click **"💸 Submit Payment"** to process

**Processing Status**: Watch the 12-step real-time progress:
- ✓ Validating Request
- ✓ Looking Up Accounts
- ✓ Running Validation Rules
- ✓ Sanctions Screening (WOLF)
- ✓ FX Conversion
- ✓ Calculating Fees
- ✓ Verifying with HUB
- ✓ Checking Balance
- ✓ Creating Ledger Entries
- ✓ Debiting Sender
- ✓ Crediting Receiver
- ✓ Completing Payment

#### 📋 My Payments
View your payment history:
- See all payments you've sent or received
- Filter by status (Completed, Failed, etc.)
- Click any payment to view full details including:
  - Payment information
  - Sender/Receiver details
  - Status history timeline

#### 👤 My Accounts
View your account details:
- Current balance
- Account number and bank code
- Currency and country
- Recent transaction history (sent/received)

#### 💱 FX Rates
- View current exchange rates
- Use the Quick Convert tool to check rates before sending

### Account Holder Limitations
- Can only send payments from your own account
- Cannot view other customers' accounts
- No access to Admin features

---

## User Guide - Administrator

### Logging In

1. Go to http://localhost:8080
2. Select the **"Administrator"** tab
3. Enter credentials:
   - **Username**: admin
   - **Password**: admin
4. Click **"Admin Login"**

### Dashboard Features

Administrators have full access to all features:

#### 💸 New Payment
- Can initiate payments from ANY account
- Full access to all sender/receiver combinations

#### 📋 My Payments
- View ALL payments in the system
- Filter and search across all transactions

#### 🏦 All Accounts
- View all customer accounts
- See balances across all accounts
- Statistics: total accounts, currencies, active count

#### 💱 FX Rates
- Same as account holder

#### ⚙️ Admin Panel

**Create New Account**:
1. Enter Account Holder Name
2. Enter Account Number (IBAN format)
3. Enter Bank Code (SWIFT/BIC format, e.g., CHASUS33)
4. Select Currency
5. Enter Country Code (2 letters, e.g., US, GB)
6. Set Initial Balance
7. Click "➕ Create Account"

**System Status**:
- Real-time health check of all 7 microservices
- Shows Online/Offline status for each service
- Click "🔄 Check All Services" to refresh

**Audit Log**:
- View recent audit events
- See event type, entity, actor, and timestamp
- All events have integrity hashes for tamper detection

---

## Service Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           FRONTEND                                       │
│                     payment-ui (Port 8080)                              │
│                    HTML + CSS + JavaScript                               │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │ HTTP
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         API GATEWAY                                      │
│                   gateway-service (Port 3000)                           │
│                    Routes: /api/payments                                 │
│                           /api/accounts                                  │
│                           /api/fx                                        │
│                           /api/audit                                     │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │ HTTP
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      PAYMENT PROCESSOR                                   │
│                 payment-processor (Port 3002)                           │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      ORCHESTRATOR                                │   │
│  │  Coordinates the entire payment flow across all services         │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌──────────────┐  ┌──────────────┐                                    │
│  │ mockHubClient│  │mockWolfClient│  (Inline mocks for external systems)│
│  │ (Account     │  │ (Sanctions   │                                    │
│  │  Verification)│  │  Screening)  │                                    │
│  └──────────────┘  └──────────────┘                                    │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │ HTTP (to downstream services)
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       DOWNSTREAM SERVICES                                │
│                                                                          │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐        │
│  │ account-service │  │validation-service│  │   fx-service    │        │
│  │   (Port 3001)   │  │   (Port 3003)    │  │   (Port 3005)   │        │
│  │                 │  │                  │  │                 │        │
│  │ • Account CRUD  │  │ • Amount limits  │  │ • Exchange rates│        │
│  │ • Balance mgmt  │  │ • Blocked countries│ │ • Conversions  │        │
│  │ • Lookups       │  │ • Duplicate check│  │ • Rate pairs    │        │
│  │                 │  │ • Currency pairs │  │                 │        │
│  │ SQLite: accounts│  │ SQLite: rules    │  │ SQLite: rates   │        │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘        │
│                                                                          │
│  ┌─────────────────┐  ┌─────────────────┐                              │
│  │  ledger-service │  │  audit-service  │                              │
│  │   (Port 3004)   │  │   (Port 3006)   │                              │
│  │                 │  │                 │                              │
│  │ • Double-entry  │  │ • Event logging │                              │
│  │   bookkeeping   │  │ • Audit trails  │                              │
│  │ • Debit/Credit  │  │ • Integrity hash│                              │
│  │                 │  │                 │                              │
│  │ SQLite: entries │  │ SQLite: events  │                              │
│  └─────────────────┘  └─────────────────┘                              │
└─────────────────────────────────────────────────────────────────────────┘
```

### Service Details

| Service | Port | Database | Purpose |
|---------|------|----------|---------|
| **payment-ui** | 8080 | None | Web frontend (HTML/CSS/JS) |
| **gateway-service** | 3000 | None | API gateway, routes to services |
| **payment-processor** | 3002 | payments.db | Core orchestration, payment state |
| **account-service** | 3001 | accounts.db | Account management, balances |
| **validation-service** | 3003 | validation.db | Business rules engine |
| **fx-service** | 3005 | fx.db | Exchange rates, conversion |
| **ledger-service** | 3004 | ledger.db | Double-entry bookkeeping |
| **audit-service** | 3006 | audit.db | Event logging, audit trail |

---

## End-to-End Payment Flow

When you submit a payment, here's exactly what happens:

### Step-by-Step Flow

```
USER CLICKS "Submit Payment"
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 1: Request Validation                                        │
│ payment-processor validates request structure                     │
│ (required fields, data types, SWIFT code format)                 │
└──────────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 2-3: Account Lookup                                          │
│ payment-processor → account-service                               │
│ GET /accounts/lookup/{accountNumber}/{bankCode}                  │
│ Retrieves sender and receiver account details                    │
└──────────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 4: Create Payment Record                                     │
│ payment-processor creates payment with status: INITIATED         │
│ Stores in local SQLite database                                  │
└──────────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 5: Audit Log - Payment Initiated                            │
│ payment-processor → audit-service                                 │
│ POST /events                                                      │
│ Logs PAYMENT_INITIATED event with SHA256 integrity hash          │
└──────────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 6: Validation Rules                                          │
│ Status changes to: VALIDATING                                     │
│ payment-processor → validation-service                            │
│ POST /validate                                                    │
│                                                                   │
│ Rules checked:                                                    │
│ • AMOUNT_LIMIT_SINGLE: Max $1,000,000 per transaction           │
│ • AMOUNT_LIMIT_DAILY: Max $5,000,000 per day                    │
│ • BLOCKED_COUNTRIES: Iran, North Korea, Syria, Cuba, Russia     │
│ • HIGH_RISK_COUNTRIES: Warning for AF, IQ, LY, MM, SD, VE, YE   │
│ • CURRENCY_PAIRS: Valid currency combination check               │
│ • DUPLICATE_CHECK: Same sender/receiver/amount in 5 minutes     │
│                                                                   │
│ If any rule fails → Status: REJECTED, flow ends                  │
└──────────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 7: Sanctions Screening (WOLF)                                │
│ Status changes to: SCREENING                                      │
│ payment-processor → mockWolfClient (inline mock)                 │
│                                                                   │
│ Screens:                                                          │
│ • Sender name and country                                        │
│ • Receiver name and country                                      │
│ • Against sanctions lists (SDN, EU, UN)                          │
│                                                                   │
│ Results:                                                          │
│ • CLEAR: Continue processing                                     │
│ • HIT: Status: ON_HOLD, requires manual review                   │
│                                                                   │
│ Demo triggers:                                                    │
│ • Name contains "SANCTIONED" → HIT                               │
│ • Country is KP, IR, SY, CU, RU → HIT                           │
└──────────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 8: FX Conversion                                             │
│ Status changes to: PROCESSING                                     │
│ payment-processor → fx-service                                    │
│ POST /convert                                                     │
│                                                                   │
│ If sender currency ≠ receiver currency:                          │
│ • Looks up exchange rate                                         │
│ • Calculates converted amount                                    │
│ • Applies spread (0.5% default)                                  │
│                                                                   │
│ Example: GBP 1000 → EUR                                          │
│ Rate: 1.15, Spread: 0.5%                                         │
│ Effective rate: 1.14425                                          │
│ Converted: EUR 1,144.25                                          │
└──────────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 9: Fee Calculation                                           │
│ payment-processor calculates transfer fee                        │
│                                                                   │
│ Fee structure (fixed + 0.1% variable):                           │
│ • USD: $25 + 0.1%                                                │
│ • EUR: €20 + 0.1%                                                │
│ • GBP: £15 + 0.1%                                                │
│ • SGD: $35 + 0.15%                                               │
│                                                                   │
│ Example: GBP 1000                                                │
│ Fee: £15 + (1000 × 0.001) = £16                                 │
│ Total debit: £1,016                                              │
└──────────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 10: HUB Verification                                         │
│ payment-processor → mockHubClient (inline mock)                  │
│                                                                   │
│ Verifies:                                                         │
│ • Account exists in banking network                              │
│ • Account is active and can receive funds                        │
│ • Bank routing is valid                                          │
│                                                                   │
│ If verification fails → Status: FAILED                           │
└──────────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 11: Balance Check                                            │
│ payment-processor → account-service                               │
│ GET /accounts/{id}/balance                                       │
│                                                                   │
│ Checks: sender.balance >= totalDebit                             │
│                                                                   │
│ If insufficient → Status: FAILED                                 │
│ "Insufficient balance. Required: X, Available: Y"                │
└──────────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 12: Ledger Posting                                           │
│ Status changes to: POSTING                                        │
│ payment-processor → ledger-service                                │
│ POST /entries/posting                                             │
│                                                                   │
│ Creates double-entry bookkeeping entries:                        │
│ 1. DEBIT sender account: £1,016 (amount + fee)                  │
│ 2. CREDIT receiver account: €1,144.25                           │
│ 3. CREDIT fee revenue account: £16                               │
│                                                                   │
│ Each entry records:                                               │
│ • Balance before and after                                       │
│ • Linked to payment ID                                           │
│ • Timestamp                                                       │
└──────────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 13: Account Updates                                          │
│ Status changes to: COMPLETING                                     │
│ payment-processor → account-service                               │
│                                                                   │
│ POST /accounts/{senderId}/debit                                  │
│ Debits sender: balance -= totalDebit                             │
│                                                                   │
│ Audit: ACCOUNT_DEBITED event logged                              │
│                                                                   │
│ POST /accounts/{receiverId}/credit                               │
│ Credits receiver: balance += targetAmount                        │
│                                                                   │
│ Audit: ACCOUNT_CREDITED event logged                             │
└──────────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 14: Complete Payment                                         │
│ Status changes to: COMPLETED                                      │
│                                                                   │
│ payment-processor → audit-service                                 │
│ Logs PAYMENT_COMPLETED event                                      │
│                                                                   │
│ Returns payment details to frontend                              │
└──────────────────────────────────────────────────────────────────┘
           │
           ▼
     USER SEES SUCCESS
```

### Payment Status Flow

```
INITIATED → VALIDATING → SCREENING → PROCESSING → POSTING → COMPLETING → COMPLETED
               ↓              ↓           ↓
           REJECTED       ON_HOLD      FAILED
           (rules)     (sanctions)   (balance/hub)
```

### Service Communication Matrix

| From | To | When | Endpoint |
|------|-----|------|----------|
| UI | Gateway | All requests | /api/* |
| Gateway | Payment Processor | Payments | /payments |
| Gateway | Account Service | Accounts | /accounts |
| Gateway | FX Service | Rates | /rates, /convert |
| Gateway | Audit Service | Events | /events |
| Payment Processor | Account Service | Lookup, balance, debit, credit | /accounts/* |
| Payment Processor | Validation Service | Rule check | /validate |
| Payment Processor | FX Service | Conversion | /convert |
| Payment Processor | Ledger Service | Postings | /entries/posting |
| Payment Processor | Audit Service | Event logging | /events |

---

## API Reference

### Gateway Service (Port 3000)

#### Payments
```
POST   /api/payments              Create new payment
GET    /api/payments              List all payments
GET    /api/payments/:id          Get payment by ID
GET    /api/payments/:id/details  Get payment with audit trail
```

#### Accounts
```
GET    /api/accounts              List all accounts
POST   /api/accounts              Create new account
GET    /api/accounts/:id          Get account by ID
GET    /api/accounts/:id/balance  Get account balance
```

#### FX
```
GET    /api/fx/rates              Get all exchange rates
GET    /api/fx/rates/:from/:to    Get specific rate
POST   /api/fx/convert            Convert currency
```

#### Audit
```
GET    /api/audit/events          List audit events
GET    /api/audit/payments/:id    Get audit trail for payment
```

### Request/Response Examples

#### Create Payment
```json
// POST /api/payments
{
  "senderAccountNumber": "GB82WEST12345698765432",
  "senderBankCode": "WESTGB2L",
  "receiverAccountNumber": "DE89370400440532013000",
  "receiverBankCode": "COBADEFF",
  "amount": 1000,
  "currency": "GBP",
  "reference": "Invoice #12345"
}

// Response
{
  "paymentId": "PAY-20260902-A1B2C3",
  "status": "COMPLETED",
  "sender": {
    "accountId": "ACC001",
    "name": "John Doe",
    "accountNumber": "GB82WEST12345698765432"
  },
  "receiver": {
    "accountId": "ACC002",
    "name": "Jane Smith",
    "accountNumber": "DE89370400440532013000"
  },
  "amount": 1000,
  "currency": "GBP",
  "targetAmount": 1144.25,
  "targetCurrency": "EUR",
  "fxRate": 1.14425,
  "feeAmount": 16,
  "totalDebit": 1016
}
```

#### Convert Currency
```json
// POST /api/fx/convert
{
  "from": "GBP",
  "to": "EUR",
  "amount": 1000
}

// Response
{
  "success": true,
  "data": {
    "from": "GBP",
    "to": "EUR",
    "originalAmount": 1000,
    "convertedAmount": 1144.25,
    "rate": 1.14425
  }
}
```

---

## Demo Credentials

### Account Holder Logins

| Name | Account Number | Bank Code | Currency | Initial Balance |
|------|---------------|-----------|----------|-----------------|
| John Doe | GB82WEST12345698765432 | WESTGB2L | GBP | £50,000 |
| Jane Smith | DE89370400440532013000 | COBADEFF | EUR | €75,000 |
| Bob Wilson | US12345678901234567890 | CHASUS33 | USD | $100,000 |
| Alice Chen | SG1234567890123456 | DBSSSGSG | SGD | $45,000 |
| Carlos Garcia | ES9121000418450200051332 | CAIXESBB | EUR | €30,000 |

### Administrator Login

| Username | Password |
|----------|----------|
| admin | admin |

---

## Troubleshooting

### Service Won't Start
- Check if port is already in use: `netstat -an | findstr :<port>`
- Ensure dependencies are installed: `npm install`

### Payment Fails
- **REJECTED**: Check validation rules (amount limits, blocked countries)
- **ON_HOLD**: Sanctions screening hit (check names/countries)
- **FAILED**: Insufficient balance or HUB verification failed

### UI Shows Errors
- Ensure gateway service is running on port 3000
- Check browser console for CORS errors
- Verify all services are healthy in Admin panel

---

## File Structure

```
services/
├── account-service/          # Account management
│   ├── src/
│   │   ├── index.js
│   │   ├── db/database.js
│   │   ├── repositories/accountRepository.js
│   │   ├── services/accountService.js
│   │   ├── routes/accounts.js
│   │   └── utils/
│   └── package.json
│
├── fx-service/               # FX rates & conversion
│   ├── src/
│   │   ├── index.js
│   │   ├── db/database.js
│   │   ├── repositories/rateRepository.js
│   │   ├── services/conversionService.js
│   │   └── routes/fx.js
│   └── package.json
│
├── validation-service/       # Business rules
│   ├── src/
│   │   ├── index.js
│   │   ├── db/database.js
│   │   ├── services/validationService.js
│   │   ├── rules/
│   │   │   ├── ruleEngine.js
│   │   │   ├── amountLimitRule.js
│   │   │   ├── countryRule.js
│   │   │   ├── duplicateRule.js
│   │   │   └── currencyRule.js
│   │   └── routes/validation.js
│   └── package.json
│
├── ledger-service/           # Double-entry bookkeeping
│   ├── src/
│   │   ├── index.js
│   │   ├── db/database.js
│   │   ├── repositories/entryRepository.js
│   │   ├── services/ledgerService.js
│   │   └── routes/ledger.js
│   └── package.json
│
├── audit-service/            # Audit logging
│   ├── src/
│   │   ├── index.js
│   │   ├── db/database.js
│   │   ├── repositories/auditRepository.js
│   │   ├── services/auditService.js
│   │   └── routes/audit.js
│   └── package.json
│
├── payment-processor/        # Core orchestration
│   ├── src/
│   │   ├── index.js
│   │   ├── db/database.js
│   │   ├── repositories/paymentRepository.js
│   │   ├── services/
│   │   │   ├── orchestrator.js      # Main payment flow
│   │   │   └── paymentService.js
│   │   ├── clients/
│   │   │   ├── accountClient.js
│   │   │   ├── validationClient.js
│   │   │   ├── fxClient.js
│   │   │   ├── ledgerClient.js
│   │   │   ├── auditClient.js
│   │   │   ├── mockHubClient.js     # HUB mock
│   │   │   └── mockWolfClient.js    # WOLF mock
│   │   ├── routes/payments.js
│   │   └── utils/
│   └── package.json
│
├── gateway-service/          # API Gateway
│   ├── src/
│   │   ├── index.js
│   │   └── routes/
│   │       ├── payments.js
│   │       ├── accounts.js
│   │       ├── fx.js
│   │       └── audit.js
│   └── package.json
│
├── payment-ui/               # Web frontend
│   ├── src/server.js
│   ├── public/
│   │   ├── index.html
│   │   ├── css/styles.css
│   │   └── js/
│   │       ├── api.js
│   │       └── app.js
│   └── package.json
│
└── docker-compose.yaml       # Container orchestration
```

---

## Security Notes (Demo Only)

This is a demonstration system. In production, you would need:

- Proper authentication (OAuth2, JWT)
- HTTPS/TLS encryption
- Input sanitization
- Rate limiting
- Database encryption
- Secrets management
- PCI-DSS compliance for payment data
- Real sanctions screening integration
- Real banking network connectivity

---

*Documentation generated for Cross-Border Wire Transfer System v1.0*
