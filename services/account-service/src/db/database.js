const Database = require('better-sqlite3');
const path = require('path');
const fs = require('fs');

const DB_PATH = process.env.DB_PATH || path.join(__dirname, '../../data/accounts.db');

let db = null;

function getDatabase() {
  if (!db) {
    // Ensure data directory exists
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
  
  // Create accounts table
  db.exec(`
    CREATE TABLE IF NOT EXISTS accounts (
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
    )
  `);

  // Create index for lookups
  db.exec(`
    CREATE INDEX IF NOT EXISTS idx_account_lookup 
    ON accounts(account_number, bank_code)
  `);

  // Seed initial data if table is empty
  const count = db.prepare('SELECT COUNT(*) as count FROM accounts').get();
  if (count.count === 0) {
    await seedAccounts(db);
  }

  console.log('Database initialized successfully');
  return db;
}

async function seedAccounts(db) {
  const accounts = [
    {
      id: 'ACC001',
      account_number: 'GB82WEST12345698765432',
      bank_code: 'WESTGB2L',
      holder_name: 'John Doe',
      currency: 'GBP',
      balance: 50000.00,
      country: 'GB',
      status: 'ACTIVE'
    },
    {
      id: 'ACC002',
      account_number: 'DE89370400440532013000',
      bank_code: 'COBADEFF',
      holder_name: 'Jane Smith',
      currency: 'EUR',
      balance: 75000.00,
      country: 'DE',
      status: 'ACTIVE'
    },
    {
      id: 'ACC003',
      account_number: 'US12345678901234567890',
      bank_code: 'CHASUS33',
      holder_name: 'Bob Wilson',
      currency: 'USD',
      balance: 100000.00,
      country: 'US',
      status: 'ACTIVE'
    },
    {
      id: 'ACC004',
      account_number: 'SG1234567890123456',
      bank_code: 'DBSSSGSG',
      holder_name: 'Alice Chen',
      currency: 'SGD',
      balance: 45000.00,
      country: 'SG',
      status: 'ACTIVE'
    },
    {
      id: 'ACC005',
      account_number: 'ES9121000418450200051332',
      bank_code: 'CAIXESBB',
      holder_name: 'Carlos Garcia',
      currency: 'EUR',
      balance: 30000.00,
      country: 'ES',
      status: 'ACTIVE'
    }
  ];

  const insert = db.prepare(`
    INSERT INTO accounts (id, account_number, bank_code, holder_name, currency, balance, country, status)
    VALUES (@id, @account_number, @bank_code, @holder_name, @currency, @balance, @country, @status)
  `);

  const insertMany = db.transaction((accounts) => {
    for (const account of accounts) {
      insert.run(account);
    }
  });

  insertMany(accounts);
  console.log('Seeded 5 initial accounts');
}

module.exports = { getDatabase, initializeDatabase };
