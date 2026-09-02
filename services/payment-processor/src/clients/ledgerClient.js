/**
 * HTTP Client for Ledger Service
 * Makes HTTP calls to ledger-service
 */

const LEDGER_SERVICE_URL = process.env.LEDGER_SERVICE_URL || 'http://localhost:3004';

/**
 * Create posting entries for a payment
 */
async function createPostingEntries(postingRequest) {
  const response = await fetch(`${LEDGER_SERVICE_URL}/entries`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(postingRequest)
  });
  
  const data = await response.json();
  
  if (!response.ok) {
    throw new Error(data.error?.message || 'Posting failed');
  }
  
  return data.data;
}

/**
 * Get entries for a payment
 */
async function getEntriesByPaymentId(paymentId) {
  const response = await fetch(`${LEDGER_SERVICE_URL}/entries/payment/${paymentId}`);
  const data = await response.json();
  
  if (!response.ok) {
    throw new Error(data.error?.message || 'Failed to get entries');
  }
  
  return data.data;
}

/**
 * Get posting summary for a payment
 */
async function getPostingSummary(paymentId) {
  const response = await fetch(`${LEDGER_SERVICE_URL}/entries/payment/${paymentId}/summary`);
  const data = await response.json();
  
  if (!response.ok) {
    throw new Error(data.error?.message || 'Failed to get summary');
  }
  
  return data.data;
}

module.exports = {
  createPostingEntries,
  getEntriesByPaymentId,
  getPostingSummary
};
