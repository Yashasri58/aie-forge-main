const VALID_CURRENCIES = ['USD', 'EUR', 'GBP', 'SGD', 'JPY', 'CHF', 'AUD', 'CAD', 'HKD'];

function validatePaymentRequest(request) {
  const errors = [];

  // Required fields
  if (!request.senderAccountNumber) {
    errors.push('Sender account number is required');
  }
  if (!request.senderBankCode) {
    errors.push('Sender bank code is required');
  }
  if (!request.receiverAccountNumber) {
    errors.push('Receiver account number is required');
  }
  if (!request.receiverBankCode) {
    errors.push('Receiver bank code is required');
  }
  if (!request.amount) {
    errors.push('Amount is required');
  }
  if (!request.currency) {
    errors.push('Currency is required');
  }

  // Type validations
  if (request.amount && (typeof request.amount !== 'number' || request.amount <= 0)) {
    errors.push('Amount must be a positive number');
  }

  // Currency validation
  if (request.currency && !VALID_CURRENCIES.includes(request.currency.toUpperCase())) {
    errors.push(`Currency must be one of: ${VALID_CURRENCIES.join(', ')}`);
  }

  // Bank code format (basic SWIFT/BIC validation)
  if (request.senderBankCode && !/^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$/.test(request.senderBankCode)) {
    errors.push('Sender bank code must be a valid SWIFT/BIC code');
  }
  if (request.receiverBankCode && !/^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$/.test(request.receiverBankCode)) {
    errors.push('Receiver bank code must be a valid SWIFT/BIC code');
  }

  return {
    valid: errors.length === 0,
    errors,
    message: errors.join('; ')
  };
}

function validatePaymentId(paymentId) {
  if (!paymentId) {
    return { valid: false, message: 'Payment ID is required' };
  }
  if (!/^PAY-\d{8}-[A-Z0-9]{6}$/.test(paymentId)) {
    return { valid: false, message: 'Invalid payment ID format' };
  }
  return { valid: true };
}

module.exports = {
  validatePaymentRequest,
  validatePaymentId,
  VALID_CURRENCIES
};
