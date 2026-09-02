const Database = require('better-sqlite3');
const path = require('path');
const fs = require('fs');

const DB_PATH = process.env.DB_PATH || path.join(__dirname, '../../data/fx.db');

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
  
  // Create fx_rates table
  db.exec(`
    CREATE TABLE IF NOT EXISTS fx_rates (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      from_currency TEXT NOT NULL,
      to_currency TEXT NOT NULL,
      rate REAL NOT NULL,
      updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(from_currency, to_currency)
    )
  `);

  // Create index
  db.exec(`
    CREATE INDEX IF NOT EXISTS idx_fx_pair 
    ON fx_rates(from_currency, to_currency)
  `);

  // Seed initial rates if empty
  const count = db.prepare('SELECT COUNT(*) as count FROM fx_rates').get();
  if (count.count === 0) {
    await seedRates(db);
  }

  console.log('FX Database initialized successfully');
  return db;
}

async function seedRates(db) {
  const rates = [
    // GBP pairs
    { from: 'GBP', to: 'EUR', rate: 1.15 },
    { from: 'GBP', to: 'USD', rate: 1.27 },
    { from: 'GBP', to: 'SGD', rate: 1.68 },
    { from: 'GBP', to: 'JPY', rate: 186.50 },
    { from: 'GBP', to: 'CHF', rate: 1.12 },
    
    // EUR pairs
    { from: 'EUR', to: 'GBP', rate: 0.87 },
    { from: 'EUR', to: 'USD', rate: 1.10 },
    { from: 'EUR', to: 'SGD', rate: 1.46 },
    { from: 'EUR', to: 'JPY', rate: 162.00 },
    { from: 'EUR', to: 'CHF', rate: 0.97 },
    
    // USD pairs
    { from: 'USD', to: 'GBP', rate: 0.79 },
    { from: 'USD', to: 'EUR', rate: 0.91 },
    { from: 'USD', to: 'SGD', rate: 1.33 },
    { from: 'USD', to: 'JPY', rate: 147.00 },
    { from: 'USD', to: 'CHF', rate: 0.88 },
    
    // SGD pairs
    { from: 'SGD', to: 'GBP', rate: 0.60 },
    { from: 'SGD', to: 'EUR', rate: 0.69 },
    { from: 'SGD', to: 'USD', rate: 0.75 },
    { from: 'SGD', to: 'JPY', rate: 110.50 },
    { from: 'SGD', to: 'CHF', rate: 0.66 },
  ];

  const insert = db.prepare(`
    INSERT INTO fx_rates (from_currency, to_currency, rate)
    VALUES (@from, @to, @rate)
  `);

  const insertMany = db.transaction((rates) => {
    for (const rate of rates) {
      insert.run(rate);
    }
  });

  insertMany(rates);
  console.log('Seeded FX rates');
}

module.exports = { getDatabase, initializeDatabase };
