/**
 * Formatters for ledger service
 */

/**
 * Format database row to API response
 */
function formatEntryResponse(row) {
  if (!row) return null;

  return {
    id: row.id,
    entryId: row.entry_id,
    paymentId: row.payment_id,
    accountId: row.account_id,
    entryType: row.entry_type,
    amount: roundAmount(row.amount),
    currency: row.currency,
    balanceBefore: row.balance_before !== null ? roundAmount(row.balance_before) : null,
    balanceAfter: row.balance_after !== null ? roundAmount(row.balance_after) : null,
    description: row.description,
    createdAt: row.created_at
  };
}

/**
 * Round amount to 2 decimal places
 */
function roundAmount(amount) {
  if (amount === undefined || amount === null) {
    return 0;
  }
  return Math.round(amount * 100) / 100;
}

/**
 * Format entry for display
 */
function formatEntryDisplay(entry) {
  const sign = entry.entryType === 'DEBIT' ? '-' : '+';
  return `${sign}${entry.amount.toFixed(2)} ${entry.currency}`;
}

module.exports = {
  formatEntryResponse,
  roundAmount,
  formatEntryDisplay
};
