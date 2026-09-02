const Database = require('better-sqlite3');
const path = require('path');
const fs = require('fs');

const DB_PATH = process.env.DB_PATH || path.join(__dirname, '../../data/validation.db');

let db = null;

function getDatabase() {
  if (!db) {
    const dataDir = path.dirname(DB_PATH);
    if (!fs.existsSync(dataDir)) {
      fs.mkdirSync(dataDir, { recursive: true });
    }
    db = new Database(DB_PATH);
    db.pragma('journal_mode = WAL');
  }
  return db;
}

async function initializeDatabase() {
  const db = getDatabase();
  
  // Create rules table
  db.exec(`
    CREATE TABLE IF NOT EXISTS rules (
      id TEXT PRIMARY KEY,
      rule_code TEXT UNIQUE NOT NULL,
      rule_name TEXT NOT NULL,
      description TEXT,
      rule_type TEXT NOT NULL,
      parameters TEXT,
      is_active INTEGER DEFAULT 1,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
  `);

  // Create validation history table
  db.exec(`
    CREATE TABLE IF NOT EXISTS validation_history (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      payment_id TEXT,
      rules_checked TEXT,
      rules_passed TEXT,
      rules_failed TEXT,
      is_valid INTEGER,
      validated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
  `);

  // Seed rules if empty
  const count = db.prepare('SELECT COUNT(*) as count FROM rules').get();
  if (count.count === 0) {
    await seedRules(db);
  }

  console.log('Validation Database initialized successfully');
  return db;
}

async function seedRules(db) {
  const rules = [
    {
      id: 'RULE001',
      rule_code: 'AMOUNT_LIMIT_SINGLE',
      rule_name: 'Single Transaction Amount Limit',
      description: 'Maximum amount allowed for a single transaction',
      rule_type: 'AMOUNT',
      parameters: JSON.stringify({
        GBP: 50000,
        EUR: 60000,
        USD: 50000,
        SGD: 70000
      })
    },
    {
      id: 'RULE002',
      rule_code: 'AMOUNT_LIMIT_DAILY',
      rule_name: 'Daily Transaction Amount Limit',
      description: 'Maximum total amount allowed per day per account',
      rule_type: 'AMOUNT',
      parameters: JSON.stringify({
        GBP: 250000,
        EUR: 300000,
        USD: 250000,
        SGD: 350000
      })
    },
    {
      id: 'RULE003',
      rule_code: 'BLOCKED_COUNTRIES',
      rule_name: 'Blocked Countries',
      description: 'Countries blocked from receiving transfers',
      rule_type: 'COUNTRY',
      parameters: JSON.stringify({
        blocked: ['NK', 'IR', 'SY', 'CU']
      })
    },
    {
      id: 'RULE004',
      rule_code: 'HIGH_RISK_COUNTRIES',
      rule_name: 'High Risk Countries',
      description: 'Countries requiring additional verification',
      rule_type: 'COUNTRY',
      parameters: JSON.stringify({
        highRisk: ['RU', 'BY', 'VE', 'MM']
      })
    },
    {
      id: 'RULE005',
      rule_code: 'DUPLICATE_CHECK',
      rule_name: 'Duplicate Transaction Check',
      description: 'Prevent duplicate transactions within time window',
      rule_type: 'DUPLICATE',
      parameters: JSON.stringify({
        windowMinutes: 5
      })
    },
    {
      id: 'RULE006',
      rule_code: 'CURRENCY_PAIRS',
      rule_name: 'Allowed Currency Pairs',
      description: 'Allowed currency conversion pairs',
      rule_type: 'CURRENCY',
      parameters: JSON.stringify({
        allowed: ['GBP-EUR', 'GBP-USD', 'GBP-SGD', 'EUR-GBP', 'EUR-USD', 'EUR-SGD', 'USD-GBP', 'USD-EUR', 'USD-SGD', 'SGD-GBP', 'SGD-EUR', 'SGD-USD']
      })
    }
  ];

  const insert = db.prepare(`
    INSERT INTO rules (id, rule_code, rule_name, description, rule_type, parameters)
    VALUES (@id, @rule_code, @rule_name, @description, @rule_type, @parameters)
  `);

  const insertMany = db.transaction((rules) => {
    for (const rule of rules) {
      insert.run(rule);
    }
  });

  insertMany(rules);
  console.log('Seeded validation rules');
}

module.exports = { getDatabase, initializeDatabase };
