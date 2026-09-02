const Database = require('better-sqlite3');
const path = require('path');
const fs = require('fs');

const DB_PATH = process.env.DB_PATH || path.join(__dirname, '../../data/payments.db');

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
  
  // Create payments table
  db.exec(`
    CREATE TABLE IF NOT EXISTS payments (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      payment_id TEXT UNIQUE NOT NULL,
      sender_account_id TEXT NOT NULL,
      sender_account_number TEXT,
      sender_bank_code TEXT,
      sender_name TEXT,
      sender_country TEXT,
      receiver_account_id TEXT NOT NULL,
      receiver_account_number TEXT,
      receiver_bank_code TEXT,
      receiver_name TEXT,
      receiver_country TEXT,
      amount REAL NOT NULL,
      currency TEXT NOT NULL,
      target_amount REAL,
      target_currency TEXT,
      fx_rate REAL,
      fee_amount REAL DEFAULT 0,
      total_debit REAL,
      status TEXT DEFAULT 'INITIATED',
      failure_reason TEXT,
      reference TEXT,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
  `);

  // Create payment_status_history table
  db.exec(`
    CREATE TABLE IF NOT EXISTS payment_status_history (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      payment_id TEXT NOT NULL,
      status TEXT NOT NULL,
      message TEXT,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
  `);

  // Create indexes
  db.exec(`
    CREATE INDEX IF NOT EXISTS idx_payment_status 
    ON payments(status)
  `);
  
  db.exec(`
    CREATE INDEX IF NOT EXISTS idx_payment_sender 
    ON payments(sender_account_id)
  `);
  
  db.exec(`
    CREATE INDEX IF NOT EXISTS idx_payment_created 
    ON payments(created_at)
  `);

  console.log('Payment Database initialized successfully');
  return db;
}

module.exports = { getDatabase, initializeDatabase };
