const Database = require('better-sqlite3');
const path = require('path');
const fs = require('fs');

const DB_PATH = process.env.DB_PATH || path.join(__dirname, '../../data/ledger.db');

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
  
  // Create ledger_entries table
  db.exec(`
    CREATE TABLE IF NOT EXISTS ledger_entries (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      entry_id TEXT UNIQUE NOT NULL,
      payment_id TEXT NOT NULL,
      account_id TEXT NOT NULL,
      entry_type TEXT NOT NULL CHECK(entry_type IN ('DEBIT', 'CREDIT')),
      amount REAL NOT NULL,
      currency TEXT NOT NULL,
      balance_before REAL,
      balance_after REAL,
      description TEXT,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
  `);

  // Create indexes
  db.exec(`
    CREATE INDEX IF NOT EXISTS idx_ledger_payment 
    ON ledger_entries(payment_id)
  `);
  
  db.exec(`
    CREATE INDEX IF NOT EXISTS idx_ledger_account 
    ON ledger_entries(account_id)
  `);

  console.log('Ledger Database initialized successfully');
  return db;
}

module.exports = { getDatabase, initializeDatabase };
