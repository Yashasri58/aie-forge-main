const Database = require('better-sqlite3');
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');

const DB_PATH = process.env.DB_PATH || path.join(__dirname, '../../data/audit.db');

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
  
  // Create audit_events table
  db.exec(`
    CREATE TABLE IF NOT EXISTS audit_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      event_id TEXT UNIQUE NOT NULL,
      event_type TEXT NOT NULL,
      entity_type TEXT NOT NULL,
      entity_id TEXT NOT NULL,
      actor TEXT,
      action TEXT,
      details TEXT,
      previous_state TEXT,
      new_state TEXT,
      ip_address TEXT,
      integrity_hash TEXT,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
  `);

  // Create indexes
  db.exec(`
    CREATE INDEX IF NOT EXISTS idx_audit_entity 
    ON audit_events(entity_type, entity_id)
  `);
  
  db.exec(`
    CREATE INDEX IF NOT EXISTS idx_audit_type 
    ON audit_events(event_type)
  `);
  
  db.exec(`
    CREATE INDEX IF NOT EXISTS idx_audit_created 
    ON audit_events(created_at)
  `);

  console.log('Audit Database initialized successfully');
  return db;
}

module.exports = { getDatabase, initializeDatabase };
