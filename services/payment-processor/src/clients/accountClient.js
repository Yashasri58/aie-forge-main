/**
 * HTTP Client for Account Service
 * Makes HTTP calls to account-service
 */

const ACCOUNT_SERVICE_URL = process.env.ACCOUNT_SERVICE_URL || 'http://localhost:3001';

/**
 * Get account by ID
 */
async function getAccountById(accountId) {
  const response = await fetch(`${ACCOUNT_SERVICE_URL}/accounts/${accountId}`);
  const data = await response.json();
  
  if (!response.ok) {
    throw new Error(data.error?.message || `Account not found: ${accountId}`);
  }
  
  return data.data;
}

/**
 * Lookup account by account number and bank code
 */
async function lookupAccount(accountNumber, bankCode) {
  const response = await fetch(`${ACCOUNT_SERVICE_URL}/accounts/lookup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ accountNumber, bankCode })
  });
  
  const data = await response.json();
  
  if (!response.ok) {
    throw new Error(data.error?.message || 'Account lookup failed');
  }
  
  return data.data;
}

/**
 * Get account balance
 */
async function getBalance(accountId) {
  const response = await fetch(`${ACCOUNT_SERVICE_URL}/accounts/${accountId}/balance`);
  const data = await response.json();
  
  if (!response.ok) {
    throw new Error(data.error?.message || 'Failed to get balance');
  }
  
  return data.data;
}

/**
 * Debit an account
 */
async function debitAccount(accountId, amount) {
  const response = await fetch(`${ACCOUNT_SERVICE_URL}/accounts/${accountId}/debit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ amount })
  });
  
  const data = await response.json();
  
  if (!response.ok) {
    throw new Error(data.error?.message || 'Debit failed');
  }
  
  return data.data;
}

/**
 * Credit an account
 */
async function creditAccount(accountId, amount) {
  const response = await fetch(`${ACCOUNT_SERVICE_URL}/accounts/${accountId}/credit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ amount })
  });
  
  const data = await response.json();
  
  if (!response.ok) {
    throw new Error(data.error?.message || 'Credit failed');
  }
  
  return data.data;
}

module.exports = {
  getAccountById,
  lookupAccount,
  getBalance,
  debitAccount,
  creditAccount
};
