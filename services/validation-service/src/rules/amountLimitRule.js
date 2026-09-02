/**
 * Amount Limit Rules
 * Validates payment amounts against configured limits
 */

const { formatCurrency } = require('../utils/formatters');

/**
 * Check if amount exceeds single transaction limit
 */
async function checkSingleLimit(payment, params) {
  const { amount, currency } = payment;
  const limit = params[currency];

  if (!limit) {
    // No limit configured for this currency, pass by default
    return { passed: true };
  }

  if (amount > limit) {
    return {
      passed: false,
      message: `Amount ${formatCurrency(amount)} ${currency} exceeds single transaction limit of ${formatCurrency(limit)} ${currency}`
    };
  }

  // Warn if close to limit (>80%)
  if (amount > limit * 0.8) {
    return {
      passed: true,
      warning: `Amount is ${Math.round((amount / limit) * 100)}% of single transaction limit`
    };
  }

  return { passed: true };
}

/**
 * Check if amount exceeds daily limit for the account
 * Note: In a real system, this would check against actual daily totals
 */
async function checkDailyLimit(payment, params) {
  const { amount, currency, senderDailyTotal = 0 } = payment;
  const limit = params[currency];

  if (!limit) {
    return { passed: true };
  }

  const projectedTotal = senderDailyTotal + amount;

  if (projectedTotal > limit) {
    return {
      passed: false,
      message: `Total daily amount ${formatCurrency(projectedTotal)} ${currency} would exceed daily limit of ${formatCurrency(limit)} ${currency}`
    };
  }

  // Warn if close to limit (>80%)
  if (projectedTotal > limit * 0.8) {
    return {
      passed: true,
      warning: `Daily total would be ${Math.round((projectedTotal / limit) * 100)}% of daily limit`
    };
  }

  return { passed: true };
}

/**
 * Validate amount is positive and reasonable
 */
function validateAmount(amount) {
  if (amount === undefined || amount === null) {
    return { valid: false, message: 'Amount is required' };
  }

  if (typeof amount !== 'number' || isNaN(amount)) {
    return { valid: false, message: 'Amount must be a valid number' };
  }

  if (amount <= 0) {
    return { valid: false, message: 'Amount must be greater than zero' };
  }

  if (amount > 999999999) {
    return { valid: false, message: 'Amount exceeds maximum allowed value' };
  }

  return { valid: true };
}

module.exports = {
  checkSingleLimit,
  checkDailyLimit,
  validateAmount
};
