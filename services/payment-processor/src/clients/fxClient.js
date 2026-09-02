/**
 * HTTP Client for FX Service
 * Makes HTTP calls to fx-service
 */

const FX_SERVICE_URL = process.env.FX_SERVICE_URL || 'http://localhost:3005';

/**
 * Get exchange rate between two currencies
 */
async function getRate(fromCurrency, toCurrency) {
  const response = await fetch(`${FX_SERVICE_URL}/rates/${fromCurrency}/${toCurrency}`);
  const data = await response.json();
  
  if (!response.ok) {
    throw new Error(data.error?.message || 'Failed to get FX rate');
  }
  
  return data.data;
}

/**
 * Convert amount between currencies
 */
async function convertCurrency(fromCurrency, toCurrency, amount) {
  const response = await fetch(`${FX_SERVICE_URL}/convert`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ from: fromCurrency, to: toCurrency, amount })
  });
  
  const data = await response.json();
  
  if (!response.ok) {
    throw new Error(data.error?.message || 'Currency conversion failed');
  }
  
  return data.data;
}

/**
 * Get all exchange rates
 */
async function getAllRates() {
  const response = await fetch(`${FX_SERVICE_URL}/rates`);
  const data = await response.json();
  
  if (!response.ok) {
    throw new Error(data.error?.message || 'Failed to get rates');
  }
  
  return data.data;
}

module.exports = {
  getRate,
  convertCurrency,
  getAllRates
};
