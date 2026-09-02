/**
 * Validation utilities for payment data
 * Called from validationService and rules
 */

/**
 * Validate payment data structure
 */
function validatePaymentData(data) {
  if (!data) {
    return { valid: false, message: 'Payment data is required' };
  }

  // Check required amount
  if (data.amount === undefined || data.amount === null) {
    return { valid: false, message: 'Amount is required' };
  }

  if (typeof data.amount !== 'number' || data.amount <= 0) {
    return { valid: false, message: 'Amount must be a positive number' };
  }

  // Check currency
  if (!data.currency) {
    return { valid: false, message: 'Currency is required' };
  }

  if (!isValidCurrencyCode(data.currency)) {
    return { valid: false, message: 'Invalid currency code format' };
  }

  // Check sender info
  if (!data.senderAccountId && !data.senderAccountNumber) {
    return { valid: false, message: 'Sender account is required' };
  }

  // Check receiver info
  if (!data.receiverAccountId && !data.receiverAccountNumber) {
    return { valid: false, message: 'Receiver account is required' };
  }

  return { valid: true };
}

/**
 * Validate currency code format (3 uppercase letters)
 */
function isValidCurrencyCode(code) {
  return typeof code === 'string' && /^[A-Z]{3}$/.test(code.toUpperCase());
}

/**
 * Validate country code format (2 uppercase letters)
 */
function isValidCountryCode(code) {
  return typeof code === 'string' && /^[A-Z]{2}$/.test(code.toUpperCase());
}

/**
 * Validate account number format
 */
function isValidAccountNumber(accountNumber) {
  return typeof accountNumber === 'string' && accountNumber.length >= 8;
}

/**
 * Validate amount is reasonable
 */
function isValidAmount(amount) {
  return typeof amount === 'number' && amount > 0 && amount < 1000000000 && isFinite(amount);
}

module.exports = {
  validatePaymentData,
  isValidCurrencyCode,
  isValidCountryCode,
  isValidAccountNumber,
  isValidAmount
};
