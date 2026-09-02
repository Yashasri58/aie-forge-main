/**
 * Mock HUB Client
 * Simulates external HUB (core banking) system
 * In real system, this would call external API
 */

/**
 * Simulate network delay
 */
function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Verify account with external HUB system
 * In real system, this validates account exists and can receive funds
 */
async function verifyAccount(accountNumber, bankCode) {
  // Simulate network delay (100-300ms)
  await delay(100 + Math.random() * 200);
  
  console.log(`[MOCK HUB] Verifying account ${accountNumber} at ${bankCode}`);
  
  // Mock: 95% success rate
  if (Math.random() < 0.95) {
    return {
      verified: true,
      accountNumber,
      bankCode,
      status: 'ACTIVE',
      message: 'Account verified by HUB',
      verifiedAt: new Date().toISOString()
    };
  }
  
  return {
    verified: false,
    accountNumber,
    bankCode,
    status: 'UNKNOWN',
    message: 'HUB verification failed - account not found',
    verifiedAt: new Date().toISOString()
  };
}

/**
 * Check if account can be debited (has sufficient funds, not frozen, etc.)
 */
async function checkDebitEligibility(accountNumber, bankCode, amount, currency) {
  await delay(50 + Math.random() * 100);
  
  console.log(`[MOCK HUB] Checking debit eligibility for ${amount} ${currency}`);
  
  // Mock: Always eligible (actual balance check done in account-service)
  return {
    eligible: true,
    accountNumber,
    amount,
    currency,
    message: 'Account eligible for debit',
    checkedAt: new Date().toISOString()
  };
}

/**
 * Reserve funds for a pending transfer
 */
async function reserveFunds(accountNumber, bankCode, amount, currency, paymentId) {
  await delay(100 + Math.random() * 150);
  
  console.log(`[MOCK HUB] Reserving ${amount} ${currency} for payment ${paymentId}`);
  
  return {
    reserved: true,
    reservationId: `RES-${Date.now()}`,
    accountNumber,
    amount,
    currency,
    paymentId,
    expiresAt: new Date(Date.now() + 30 * 60 * 1000).toISOString() // 30 min expiry
  };
}

/**
 * Release reserved funds (on failure or timeout)
 */
async function releaseFunds(reservationId) {
  await delay(50 + Math.random() * 100);
  
  console.log(`[MOCK HUB] Releasing reservation ${reservationId}`);
  
  return {
    released: true,
    reservationId,
    releasedAt: new Date().toISOString()
  };
}

module.exports = {
  verifyAccount,
  checkDebitEligibility,
  reserveFunds,
  releaseFunds
};
