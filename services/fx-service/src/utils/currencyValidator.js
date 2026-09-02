/**
 * Currency validation utilities
 * Called from conversionService and routes
 */

const SUPPORTED_CURRENCIES = ['GBP', 'EUR', 'USD', 'SGD', 'JPY', 'CHF', 'AUD', 'CAD'];

/**
 * Check if currency code is valid and supported
 */
function isValidCurrency(currency) {
  if (!currency || typeof currency !== 'string') {
    return false;
  }
  return SUPPORTED_CURRENCIES.includes(currency.toUpperCase());
}

/**
 * Check if amount is a valid positive number
 */
function isValidAmount(amount) {
  if (amount === undefined || amount === null) {
    return false;
  }
  const num = parseFloat(amount);
  return !isNaN(num) && num > 0 && isFinite(num);
}

/**
 * Normalize currency code to uppercase
 */
function normalizeCurrency(currency) {
  return currency?.toUpperCase() || '';
}

/**
 * Get list of supported currencies
 */
function getSupportedCurrencies() {
  return [...SUPPORTED_CURRENCIES];
}

/**
 * Check if a currency pair is valid
 */
function isValidCurrencyPair(fromCurrency, toCurrency) {
  return isValidCurrency(fromCurrency) && isValidCurrency(toCurrency);
}

module.exports = {
  isValidCurrency,
  isValidAmount,
  normalizeCurrency,
  getSupportedCurrencies,
  isValidCurrencyPair,
  SUPPORTED_CURRENCIES
};
