/**
 * Currency Rules
 * Validates currency pairs for cross-border transfers
 */

/**
 * Check if currency pair is allowed
 */
async function checkCurrencyPair(payment, params) {
  const { currency, targetCurrency } = payment;
  
  // Same currency is always allowed
  if (currency === targetCurrency) {
    return { passed: true };
  }
  
  const allowedPairs = params.allowed || [];
  const pair = `${currency}-${targetCurrency}`;
  const reversePair = `${targetCurrency}-${currency}`;
  
  if (allowedPairs.includes(pair) || allowedPairs.includes(reversePair)) {
    return { passed: true };
  }
  
  return {
    passed: false,
    message: `Currency conversion from ${currency} to ${targetCurrency} is not supported`
  };
}

/**
 * Validate currency code format
 */
function isValidCurrencyCode(code) {
  return typeof code === 'string' && /^[A-Z]{3}$/.test(code);
}

/**
 * Get list of supported currencies
 */
function getSupportedCurrencies() {
  return ['GBP', 'EUR', 'USD', 'SGD', 'JPY', 'CHF', 'AUD', 'CAD'];
}

/**
 * Check if currency is supported
 */
function isSupportedCurrency(currency) {
  return getSupportedCurrencies().includes(currency?.toUpperCase());
}

module.exports = {
  checkCurrencyPair,
  isValidCurrencyCode,
  getSupportedCurrencies,
  isSupportedCurrency
};
