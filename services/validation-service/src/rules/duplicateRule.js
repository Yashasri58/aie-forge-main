/**
 * Duplicate Transaction Rule
 * Detects potential duplicate transactions within a time window
 */

// In-memory store for recent transactions (in production, use Redis or similar)
const recentTransactions = new Map();

/**
 * Check for duplicate transactions
 */
async function checkDuplicate(payment, params) {
  const windowMinutes = params.windowMinutes || 5;
  const windowMs = windowMinutes * 60 * 1000;
  
  // Create a hash key for this transaction
  const txKey = createTransactionKey(payment);
  
  // Clean old entries
  cleanOldEntries(windowMs);
  
  // Check if duplicate exists
  const existing = recentTransactions.get(txKey);
  
  if (existing) {
    const timeSince = Date.now() - existing.timestamp;
    const minutesSince = Math.round(timeSince / 60000);
    
    return {
      passed: false,
      message: `Potential duplicate transaction detected. Similar payment was submitted ${minutesSince} minute(s) ago.`
    };
  }
  
  // Store this transaction
  recentTransactions.set(txKey, {
    timestamp: Date.now(),
    paymentId: payment.paymentId
  });
  
  return { passed: true };
}

/**
 * Create a unique key for transaction based on key fields
 */
function createTransactionKey(payment) {
  const parts = [
    payment.senderAccountNumber || payment.senderAccountId,
    payment.receiverAccountNumber || payment.receiverAccountId,
    payment.amount,
    payment.currency
  ];
  return parts.join('|');
}

/**
 * Remove entries older than the window
 */
function cleanOldEntries(windowMs) {
  const cutoff = Date.now() - windowMs;
  
  for (const [key, value] of recentTransactions.entries()) {
    if (value.timestamp < cutoff) {
      recentTransactions.delete(key);
    }
  }
}

/**
 * Clear all recent transactions (for testing)
 */
function clearRecentTransactions() {
  recentTransactions.clear();
}

/**
 * Get count of tracked transactions
 */
function getRecentTransactionCount() {
  return recentTransactions.size;
}

module.exports = {
  checkDuplicate,
  createTransactionKey,
  clearRecentTransactions,
  getRecentTransactionCount
};
