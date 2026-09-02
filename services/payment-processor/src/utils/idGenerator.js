const crypto = require('crypto');

/**
 * Generate unique payment ID
 * Format: PAY-YYYYMMDD-XXXXXX
 */
function generatePaymentId() {
  const date = new Date();
  const dateStr = date.toISOString().slice(0, 10).replace(/-/g, '');
  const random = crypto.randomBytes(3).toString('hex').toUpperCase();
  return `PAY-${dateStr}-${random}`;
}

/**
 * Generate unique transaction reference
 * Format: TXN-TIMESTAMP-RANDOM
 */
function generateTransactionRef() {
  const timestamp = Date.now().toString(36).toUpperCase();
  const random = crypto.randomBytes(4).toString('hex').toUpperCase();
  return `TXN-${timestamp}-${random}`;
}

module.exports = {
  generatePaymentId,
  generateTransactionRef
};
