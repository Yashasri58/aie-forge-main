/**
 * HTTP Client for Validation Service
 * Makes HTTP calls to validation-service
 */

const VALIDATION_SERVICE_URL = process.env.VALIDATION_SERVICE_URL || 'http://localhost:3003';

/**
 * Validate a payment
 */
async function validatePayment(paymentData) {
  const response = await fetch(`${VALIDATION_SERVICE_URL}/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(paymentData)
  });
  
  const data = await response.json();
  
  if (!response.ok) {
    throw new Error(data.error?.message || 'Validation request failed');
  }
  
  return data.data;
}

/**
 * Get all validation rules
 */
async function getRules() {
  const response = await fetch(`${VALIDATION_SERVICE_URL}/rules`);
  const data = await response.json();
  
  if (!response.ok) {
    throw new Error(data.error?.message || 'Failed to get rules');
  }
  
  return data.data;
}

module.exports = {
  validatePayment,
  getRules
};
