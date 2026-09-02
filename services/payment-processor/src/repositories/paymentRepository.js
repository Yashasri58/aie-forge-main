const { getDatabase } = require('../db/database');
const { formatPaymentResponse } = require('../utils/formatters');

class PaymentRepository {

  findAll(limit = 50, offset = 0) {
    const db = getDatabase();
    const rows = db.prepare(
      'SELECT * FROM payments ORDER BY created_at DESC LIMIT ? OFFSET ?'
    ).all(limit, offset);
    return rows.map(formatPaymentResponse);
  }

  findByPaymentId(paymentId) {
    const db = getDatabase();
    const row = db.prepare('SELECT * FROM payments WHERE payment_id = ?').get(paymentId);
    return row ? formatPaymentResponse(row) : null;
  }

  findByStatus(status, limit = 50) {
    const db = getDatabase();
    const rows = db.prepare(
      'SELECT * FROM payments WHERE status = ? ORDER BY created_at DESC LIMIT ?'
    ).all(status, limit);
    return rows.map(formatPaymentResponse);
  }

  findBySenderAccountId(accountId, limit = 50) {
    const db = getDatabase();
    const rows = db.prepare(
      'SELECT * FROM payments WHERE sender_account_id = ? ORDER BY created_at DESC LIMIT ?'
    ).all(accountId, limit);
    return rows.map(formatPaymentResponse);
  }

  create(payment) {
    const db = getDatabase();
    
    const stmt = db.prepare(`
      INSERT INTO payments (
        payment_id, sender_account_id, sender_account_number, sender_bank_code, sender_name, sender_country,
        receiver_account_id, receiver_account_number, receiver_bank_code, receiver_name, receiver_country,
        amount, currency, target_amount, target_currency, fx_rate, fee_amount, total_debit, status, reference
      )
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);

    stmt.run(
      payment.paymentId,
      payment.senderAccountId,
      payment.senderAccountNumber,
      payment.senderBankCode,
      payment.senderName,
      payment.senderCountry,
      payment.receiverAccountId,
      payment.receiverAccountNumber,
      payment.receiverBankCode,
      payment.receiverName,
      payment.receiverCountry,
      payment.amount,
      payment.currency,
      payment.targetAmount,
      payment.targetCurrency,
      payment.fxRate,
      payment.feeAmount || 0,
      payment.totalDebit,
      payment.status || 'INITIATED',
      payment.reference
    );

    // Add initial status history
    this.addStatusHistory(payment.paymentId, payment.status || 'INITIATED', 'Payment initiated');

    return this.findByPaymentId(payment.paymentId);
  }

  updateStatus(paymentId, status, failureReason = null) {
    const db = getDatabase();
    const now = new Date().toISOString();
    
    const stmt = db.prepare(`
      UPDATE payments 
      SET status = ?, failure_reason = ?, updated_at = ?
      WHERE payment_id = ?
    `);

    stmt.run(status, failureReason, now, paymentId);
    this.addStatusHistory(paymentId, status, failureReason);

    return this.findByPaymentId(paymentId);
  }

  updatePaymentDetails(paymentId, updates) {
    const db = getDatabase();
    const now = new Date().toISOString();
    
    const fields = [];
    const values = [];
    
    if (updates.targetAmount !== undefined) {
      fields.push('target_amount = ?');
      values.push(updates.targetAmount);
    }
    if (updates.targetCurrency !== undefined) {
      fields.push('target_currency = ?');
      values.push(updates.targetCurrency);
    }
    if (updates.fxRate !== undefined) {
      fields.push('fx_rate = ?');
      values.push(updates.fxRate);
    }
    if (updates.feeAmount !== undefined) {
      fields.push('fee_amount = ?');
      values.push(updates.feeAmount);
    }
    if (updates.totalDebit !== undefined) {
      fields.push('total_debit = ?');
      values.push(updates.totalDebit);
    }
    
    fields.push('updated_at = ?');
    values.push(now);
    values.push(paymentId);
    
    const stmt = db.prepare(`
      UPDATE payments 
      SET ${fields.join(', ')}
      WHERE payment_id = ?
    `);
    
    stmt.run(...values);
    return this.findByPaymentId(paymentId);
  }

  addStatusHistory(paymentId, status, message = null) {
    const db = getDatabase();
    
    const stmt = db.prepare(`
      INSERT INTO payment_status_history (payment_id, status, message)
      VALUES (?, ?, ?)
    `);

    stmt.run(paymentId, status, message);
  }

  getStatusHistory(paymentId) {
    const db = getDatabase();
    return db.prepare(
      'SELECT * FROM payment_status_history WHERE payment_id = ? ORDER BY created_at'
    ).all(paymentId);
  }

  countByStatus(status) {
    const db = getDatabase();
    const result = db.prepare(
      'SELECT COUNT(*) as count FROM payments WHERE status = ?'
    ).get(status);
    return result?.count || 0;
  }
}

module.exports = new PaymentRepository();
