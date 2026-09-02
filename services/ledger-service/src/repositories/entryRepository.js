const { getDatabase } = require('../db/database');
const { formatEntryResponse } = require('../utils/formatters');

class EntryRepository {

  findAll(limit = 100, offset = 0) {
    const db = getDatabase();
    const rows = db.prepare(
      'SELECT * FROM ledger_entries ORDER BY created_at DESC LIMIT ? OFFSET ?'
    ).all(limit, offset);
    return rows.map(formatEntryResponse);
  }

  findByEntryId(entryId) {
    const db = getDatabase();
    const row = db.prepare('SELECT * FROM ledger_entries WHERE entry_id = ?').get(entryId);
    return row ? formatEntryResponse(row) : null;
  }

  findByPaymentId(paymentId) {
    const db = getDatabase();
    const rows = db.prepare(
      'SELECT * FROM ledger_entries WHERE payment_id = ? ORDER BY created_at'
    ).all(paymentId);
    return rows.map(formatEntryResponse);
  }

  findByAccountId(accountId, limit = 50) {
    const db = getDatabase();
    const rows = db.prepare(
      'SELECT * FROM ledger_entries WHERE account_id = ? ORDER BY created_at DESC LIMIT ?'
    ).all(accountId, limit);
    return rows.map(formatEntryResponse);
  }

  create(entry) {
    const db = getDatabase();
    
    const stmt = db.prepare(`
      INSERT INTO ledger_entries 
      (entry_id, payment_id, account_id, entry_type, amount, currency, balance_before, balance_after, description)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);

    stmt.run(
      entry.entryId,
      entry.paymentId,
      entry.accountId,
      entry.entryType,
      entry.amount,
      entry.currency,
      entry.balanceBefore,
      entry.balanceAfter,
      entry.description
    );

    return this.findByEntryId(entry.entryId);
  }

  createMany(entries) {
    const db = getDatabase();
    
    const stmt = db.prepare(`
      INSERT INTO ledger_entries 
      (entry_id, payment_id, account_id, entry_type, amount, currency, balance_before, balance_after, description)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);

    const insertMany = db.transaction((entries) => {
      const results = [];
      for (const entry of entries) {
        stmt.run(
          entry.entryId,
          entry.paymentId,
          entry.accountId,
          entry.entryType,
          entry.amount,
          entry.currency,
          entry.balanceBefore,
          entry.balanceAfter,
          entry.description
        );
        results.push(entry.entryId);
      }
      return results;
    });

    const entryIds = insertMany(entries);
    return entryIds.map(id => this.findByEntryId(id));
  }

  getAccountBalance(accountId) {
    const db = getDatabase();
    const result = db.prepare(`
      SELECT 
        SUM(CASE WHEN entry_type = 'CREDIT' THEN amount ELSE 0 END) -
        SUM(CASE WHEN entry_type = 'DEBIT' THEN amount ELSE 0 END) as balance
      FROM ledger_entries 
      WHERE account_id = ?
    `).get(accountId);
    return result?.balance || 0;
  }

  countByPaymentId(paymentId) {
    const db = getDatabase();
    const result = db.prepare(
      'SELECT COUNT(*) as count FROM ledger_entries WHERE payment_id = ?'
    ).get(paymentId);
    return result?.count || 0;
  }
}

module.exports = new EntryRepository();
