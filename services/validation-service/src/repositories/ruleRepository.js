const { getDatabase } = require('../db/database');
const { formatRuleResponse } = require('../utils/formatters');

class RuleRepository {

  findAll() {
    const db = getDatabase();
    const rows = db.prepare('SELECT * FROM rules ORDER BY rule_code').all();
    return rows.map(formatRuleResponse);
  }

  findAllActive() {
    const db = getDatabase();
    return db.prepare('SELECT * FROM rules WHERE is_active = 1 ORDER BY rule_code').all();
  }

  findById(id) {
    const db = getDatabase();
    const row = db.prepare('SELECT * FROM rules WHERE id = ?').get(id);
    return row ? formatRuleResponse(row) : null;
  }

  findByCode(code) {
    const db = getDatabase();
    const row = db.prepare('SELECT * FROM rules WHERE rule_code = ?').get(code);
    return row ? formatRuleResponse(row) : null;
  }

  updateRuleStatus(id, isActive) {
    const db = getDatabase();
    const stmt = db.prepare('UPDATE rules SET is_active = ? WHERE id = ?');
    stmt.run(isActive ? 1 : 0, id);
    return this.findById(id);
  }

  updateRuleParameters(id, parameters) {
    const db = getDatabase();
    const stmt = db.prepare('UPDATE rules SET parameters = ? WHERE id = ?');
    stmt.run(JSON.stringify(parameters), id);
    return this.findById(id);
  }

  logValidation(data) {
    const db = getDatabase();
    const stmt = db.prepare(`
      INSERT INTO validation_history (payment_id, rules_checked, rules_passed, rules_failed, is_valid)
      VALUES (?, ?, ?, ?, ?)
    `);
    stmt.run(
      data.paymentId,
      data.rulesChecked,
      data.rulesPassed,
      data.rulesFailed,
      data.isValid
    );
  }

  getValidationHistory(paymentId) {
    const db = getDatabase();
    return db.prepare(
      'SELECT * FROM validation_history WHERE payment_id = ? ORDER BY validated_at DESC'
    ).all(paymentId);
  }
}

module.exports = new RuleRepository();
