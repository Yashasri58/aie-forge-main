const { getDatabase } = require('../db/database');

class RateRepository {
  
  findAll() {
    const db = getDatabase();
    return db.prepare('SELECT * FROM fx_rates ORDER BY from_currency, to_currency').all();
  }

  findByPair(fromCurrency, toCurrency) {
    const db = getDatabase();
    return db.prepare(
      'SELECT * FROM fx_rates WHERE from_currency = ? AND to_currency = ?'
    ).get(fromCurrency.toUpperCase(), toCurrency.toUpperCase());
  }

  findByFromCurrency(fromCurrency) {
    const db = getDatabase();
    return db.prepare(
      'SELECT * FROM fx_rates WHERE from_currency = ?'
    ).all(fromCurrency.toUpperCase());
  }

  updateRate(fromCurrency, toCurrency, newRate) {
    const db = getDatabase();
    const now = new Date().toISOString();
    
    const stmt = db.prepare(`
      UPDATE fx_rates 
      SET rate = ?, updated_at = ?
      WHERE from_currency = ? AND to_currency = ?
    `);

    const result = stmt.run(newRate, now, fromCurrency.toUpperCase(), toCurrency.toUpperCase());
    
    if (result.changes === 0) {
      return null;
    }

    return this.findByPair(fromCurrency, toCurrency);
  }

  createRate(fromCurrency, toCurrency, rate) {
    const db = getDatabase();
    
    const stmt = db.prepare(`
      INSERT INTO fx_rates (from_currency, to_currency, rate)
      VALUES (?, ?, ?)
    `);

    stmt.run(fromCurrency.toUpperCase(), toCurrency.toUpperCase(), rate);
    return this.findByPair(fromCurrency, toCurrency);
  }
}

module.exports = new RateRepository();
