/**
 * Validators for account data
 * These functions are called from multiple places within the service
 */

const VALID_CURRENCIES = ['GBP', 'EUR', 'USD', 'SGD', 'JPY', 'CHF', 'AUD', 'CAD'];
const VALID_COUNTRIES = ['GB', 'DE', 'US', 'SG', 'JP', 'CH', 'AU', 'CA', 'FR', 'ES', 'IT', 'NL'];
const VALID_STATUSES = ['ACTIVE', 'FROZEN', 'CLOSED'];

/**
 * Validate account creation data
 */
function validateAccountData(data) {
  if (!data) {
    return { valid: false, message: 'Account data is required' };
  }

  // Required fields
  if (!data.accountNumber) {
    return { valid: false, message: 'accountNumber is required' };
  }

  if (!data.bankCode) {
    return { valid: false, message: 'bankCode is required' };
  }

  if (!data.holderName) {
    return { valid: false, message: 'holderName is required' };
  }

  if (!data.currency) {
    return { valid: false, message: 'currency is required' };
  }

  if (!data.country) {
    return { valid: false, message: 'country is required' };
  }

  // Format validations
  if (!isValidAccountNumber(data.accountNumber)) {
    return { valid: false, message: 'Invalid account number format' };
  }

  if (!isValidBankCode(data.bankCode)) {
    return { valid: false, message: 'Invalid bank code format (SWIFT/BIC)' };
  }

  if (!isValidCurrency(data.currency)) {
    return { valid: false, message: `Invalid currency. Allowed: ${VALID_CURRENCIES.join(', ')}` };
  }

  if (!isValidCountry(data.country)) {
    return { valid: false, message: `Invalid country code. Allowed: ${VALID_COUNTRIES.join(', ')}` };
  }

  if (data.balance !== undefined && !isValidBalance(data.balance)) {
    return { valid: false, message: 'Balance must be a non-negative number' };
  }

  return { valid: true };
}

/**
 * Validate balance update
 */
function validateBalanceUpdate(balance) {
  if (balance === undefined || balance === null) {
    return { valid: false, message: 'Balance is required' };
  }

  if (typeof balance !== 'number') {
    return { valid: false, message: 'Balance must be a number' };
  }

  if (balance < 0) {
    return { valid: false, message: 'Balance cannot be negative' };
  }

  return { valid: true };
}

/**
 * Validate account number format
 * Accepts IBAN format or basic account numbers
 */
function isValidAccountNumber(accountNumber) {
  if (!accountNumber || typeof accountNumber !== 'string') {
    return false;
  }
  // Basic validation: 8-34 alphanumeric characters
  return /^[A-Z0-9]{8,34}$/i.test(accountNumber);
}

/**
 * Validate SWIFT/BIC code
 * Format: 8 or 11 characters (BANKCCLL or BANKCCLLXXX)
 */
function isValidBankCode(bankCode) {
  if (!bankCode || typeof bankCode !== 'string') {
    return false;
  }
  // SWIFT/BIC: 8 or 11 alphanumeric characters
  return /^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$/i.test(bankCode);
}

/**
 * Validate currency code
 */
function isValidCurrency(currency) {
  return VALID_CURRENCIES.includes(currency?.toUpperCase());
}

/**
 * Validate country code
 */
function isValidCountry(country) {
  return VALID_COUNTRIES.includes(country?.toUpperCase());
}

/**
 * Validate balance is a valid number
 */
function isValidBalance(balance) {
  return typeof balance === 'number' && balance >= 0 && isFinite(balance);
}

/**
 * Validate account status
 */
function isValidStatus(status) {
  return VALID_STATUSES.includes(status?.toUpperCase());
}

module.exports = {
  validateAccountData,
  validateBalanceUpdate,
  isValidAccountNumber,
  isValidBankCode,
  isValidCurrency,
  isValidCountry,
  isValidBalance,
  isValidStatus,
  VALID_CURRENCIES,
  VALID_COUNTRIES,
  VALID_STATUSES
};
