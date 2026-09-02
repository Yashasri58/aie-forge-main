function formatPaymentResponse(row) {
  if (!row) return null;

  return {
    paymentId: row.payment_id,
    status: row.status,
    sender: {
      accountId: row.sender_account_id,
      accountNumber: row.sender_account_number,
      bankCode: row.sender_bank_code,
      name: row.sender_name,
      country: row.sender_country
    },
    receiver: {
      accountId: row.receiver_account_id,
      accountNumber: row.receiver_account_number,
      bankCode: row.receiver_bank_code,
      name: row.receiver_name,
      country: row.receiver_country
    },
    amount: row.amount,
    currency: row.currency,
    targetAmount: row.target_amount,
    targetCurrency: row.target_currency,
    fxRate: row.fx_rate,
    feeAmount: row.fee_amount,
    totalDebit: row.total_debit,
    reference: row.reference,
    failureReason: row.failure_reason,
    createdAt: row.created_at,
    updatedAt: row.updated_at
  };
}

function formatStatusHistoryResponse(row) {
  if (!row) return null;

  return {
    status: row.status,
    message: row.message,
    timestamp: row.created_at
  };
}

function formatPaymentSummary(payment) {
  return {
    paymentId: payment.paymentId,
    status: payment.status,
    amount: `${payment.amount} ${payment.currency}`,
    targetAmount: payment.targetAmount ? `${payment.targetAmount} ${payment.targetCurrency}` : null,
    sender: payment.sender.name,
    receiver: payment.receiver.name,
    createdAt: payment.createdAt
  };
}

function formatErrorResponse(error) {
  return {
    error: {
      code: error.code || 'INTERNAL_ERROR',
      message: error.message,
      details: error.details || null
    }
  };
}

module.exports = {
  formatPaymentResponse,
  formatStatusHistoryResponse,
  formatPaymentSummary,
  formatErrorResponse
};
