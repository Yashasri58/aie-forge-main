const { getDatabase } = require('../db/database');
const { generateAccountId } = require('../utils/idGenerator');
const { formatAccountResponse } = require('../utils/formatters');

class AccountRepository {
  
  findAll() {
    const db = getDatabase();
    const rows = db.prepare('SELECT * FROM accounts ORDER BY created_at DESC').all();
    return rows.map(formatAccountResponse);
  }

  findById(id) {
    const db = getDatabase();
    const row = db.prepare('SELECT * FROM accounts WHERE id = ?').get(id);
    return row ? formatAccountResponse(row) : null;
  }

  findByAccountNumber(accountNumber) {
    const db = getDatabase();
    const row = db.prepare('SELECT * FROM accounts WHERE account_number = ?').get(accountNumber);
    return row ? formatAccountResponse(row) : null;
  }

  findByAccountNumberAndBankCode(accountNumber, bankCode) {
    const db = getDatabase();
    const row = db.prepare(
      'SELECT * FROM accounts WHERE account_number = ? AND bank_code = ?'
    ).get(accountNumber, bankCode);
    return row ? formatAccountResponse(row) : null;
  }

  create(accountData) {
    const db = getDatabase();
    const id = generateAccountId();
    const now = new Date().toISOString();

    const stmt = db.prepare(`
      INSERT INTO accounts (id, account_number, bank_code, holder_name, currency, balance, country, status, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);

    stmt.run(
      id,
      accountData.accountNumber,
      accountData.bankCode,
      accountData.holderName,
      accountData.currency,
      accountData.balance || 0,
      accountData.country,
      'ACTIVE',
      now,
      now
    );

    return this.findById(id);
  }

  updateBalance(id, newBalance) {
    const db = getDatabase();
    const now = new Date().toISOString();

    const stmt = db.prepare(`
      UPDATE accounts 
      SET balance = ?, updated_at = ?
      WHERE id = ?
    `);

    const result = stmt.run(newBalance, now, id);
    
    if (result.changes === 0) {
      return null;
    }

    return this.findById(id);
  }

  updateStatus(id, status) {
    const db = getDatabase();
    const now = new Date().toISOString();

    const stmt = db.prepare(`
      UPDATE accounts 
      SET status = ?, updated_at = ?
      WHERE id = ?
    `);

    const result = stmt.run(status, now, id);
    
    if (result.changes === 0) {
      return null;
    }

    return this.findById(id);
  }

  getBalance(id) {
    const db = getDatabase();
    const row = db.prepare('SELECT balance, currency FROM accounts WHERE id = ?').get(id);
    return row ? { balance: row.balance, currency: row.currency } : null;
  }
}

module.exports = new AccountRepository();
