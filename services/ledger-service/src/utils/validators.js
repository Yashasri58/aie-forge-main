/**
 * Validators for ledger service
 */

/**
 * Validate posting request
 */
function validatePostingRequest(request) {
  if (!request) {
    return { valid: false, message: 'Posting request is required' };
  }

  if (!request.paymentId) {
    return { valid: false, message: 'paymentId is required' };
  }

  if (!request.senderAccountId) {
    return { valid: false, message: 'senderAccountId is required' };
  }

  if (!request.receiverAccountId) {
    return { valid: false, message: 'receiverAccountId is required' };
  }

  if (request.amount === undefined || request.amount <= 0) {
    return { valid: false, message: 'Valid amount is required' };
  }

  if (!request.currency) {
    return { valid: false, message: 'currency is required' };
  }

  return { valid: true };
}

/**
 * Validate entry type
 */
function isValidEntryType(type) {
  return ['DEBIT', 'CREDIT'].includes(type?.toUpperCase());
}

module.exports = {
  validatePostingRequest,
  isValidEntryType
};
