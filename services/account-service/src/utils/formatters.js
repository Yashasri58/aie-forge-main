/**
 * Formatters for account data
 * These functions are called from multiple places within the service
 */

/**
 * Format database row to API response
 */
function formatAccountResponse(row) {
  if (!row) return null;
  
  return {
    id: row.id,
    accountNumber: row.account_number,
    bankCode: row.bank_code,
    holderName: row.holder_name,
    currency: row.currency,
    balance: formatCurrency(row.balance, row.currency),
    country: row.country,
    status: row.status,
    createdAt: row.created_at,
    updatedAt: row.updated_at
  };
}

/**
 * Format currency amount to 2 decimal places
 */
function formatCurrency(amount, currency) {
  if (amount === undefined || amount === null) {
    return 0;
  }
  return Math.round(amount * 100) / 100;
}

/**
 * Format account number for display (masked)
 */
function maskAccountNumber(accountNumber) {
  if (!accountNumber || accountNumber.length < 8) {
    return accountNumber;
  }
  const visible = accountNumber.slice(-4);
  const masked = '*'.repeat(accountNumber.length - 4);
  return masked + visible;
}

/**
 * Format SWIFT/BIC code for display
 */
function formatBankCode(bankCode) {
  if (!bankCode) return '';
  return bankCode.toUpperCase();
}

/**
 * Format holder name (capitalize)
 */
function formatHolderName(name) {
  if (!name) return '';
  return name
    .split(' ')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ');
}

/**
 * Format account for summary view
 */
function formatAccountSummary(account) {
  return {
    id: account.id,
    holderName: account.holderName,
    maskedAccount: maskAccountNumber(account.accountNumber),
    currency: account.currency,
    balance: account.balance,
    status: account.status
  };
}

/**
 * Format balance change for audit
 */
function formatBalanceChange(accountId, oldBalance, newBalance, currency) {
  const change = newBalance - oldBalance;
  return {
    accountId,
    previousBalance: formatCurrency(oldBalance, currency),
    newBalance: formatCurrency(newBalance, currency),
    change: formatCurrency(change, currency),
    changeType: change >= 0 ? 'CREDIT' : 'DEBIT',
    currency
  };
}

module.exports = {
  formatAccountResponse,
  formatCurrency,
  maskAccountNumber,
  formatBankCode,
  formatHolderName,
  formatAccountSummary,
  formatBalanceChange
};
