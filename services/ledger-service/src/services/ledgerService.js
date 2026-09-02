const entryRepository = require('../repositories/entryRepository');
const { generateEntryId } = require('../utils/idGenerator');
const { validatePostingRequest } = require('../utils/validators');
const { roundAmount } = require('../utils/formatters');

class LedgerService {

  getAllEntries(limit, offset) {
    return entryRepository.findAll(limit, offset);
  }

  getEntryById(entryId) {
    const entry = entryRepository.findByEntryId(entryId);
    if (!entry) {
      const error = new Error(`Entry not found: ${entryId}`);
      error.code = 'ENTRY_NOT_FOUND';
      error.status = 404;
      throw error;
    }
    return entry;
  }

  getEntriesByPaymentId(paymentId) {
    return entryRepository.findByPaymentId(paymentId);
  }

  getEntriesByAccountId(accountId, limit) {
    return entryRepository.findByAccountId(accountId, limit);
  }

  /**
   * Create ledger entries for a payment
   * Implements double-entry bookkeeping: every debit has a corresponding credit
   */
  createPostingEntries(postingRequest) {
    // Validate request
    const validation = validatePostingRequest(postingRequest);
    if (!validation.valid) {
      const error = new Error(validation.message);
      error.code = 'VALIDATION_ERROR';
      error.status = 400;
      throw error;
    }

    const {
      paymentId,
      senderAccountId,
      receiverAccountId,
      amount,
      currency,
      targetAmount,
      targetCurrency,
      feeAmount = 0,
      senderBalanceBefore,
      receiverBalanceBefore
    } = postingRequest;

    const entries = [];
    const timestamp = new Date().toISOString();

    // Entry 1: DEBIT sender account (reduce balance)
    const senderDebit = {
      entryId: generateEntryId(),
      paymentId,
      accountId: senderAccountId,
      entryType: 'DEBIT',
      amount: roundAmount(amount + feeAmount), // Amount + fees
      currency,
      balanceBefore: senderBalanceBefore,
      balanceAfter: roundAmount(senderBalanceBefore - amount - feeAmount),
      description: `Wire transfer to ${receiverAccountId}`
    };
    entries.push(senderDebit);

    // Entry 2: CREDIT receiver account (increase balance)
    const effectiveAmount = targetAmount || amount;
    const effectiveCurrency = targetCurrency || currency;
    
    const receiverCredit = {
      entryId: generateEntryId(),
      paymentId,
      accountId: receiverAccountId,
      entryType: 'CREDIT',
      amount: roundAmount(effectiveAmount),
      currency: effectiveCurrency,
      balanceBefore: receiverBalanceBefore,
      balanceAfter: roundAmount(receiverBalanceBefore + effectiveAmount),
      description: `Wire transfer from ${senderAccountId}`
    };
    entries.push(receiverCredit);

    // Entry 3: CREDIT fee account (bank revenue) - if there are fees
    if (feeAmount > 0) {
      const feeCredit = {
        entryId: generateEntryId(),
        paymentId,
        accountId: 'FEE_REVENUE',
        entryType: 'CREDIT',
        amount: roundAmount(feeAmount),
        currency,
        balanceBefore: null,
        balanceAfter: null,
        description: `Transfer fee for payment ${paymentId}`
      };
      entries.push(feeCredit);
    }

    // Create all entries atomically
    const createdEntries = entryRepository.createMany(entries);

    return {
      paymentId,
      entries: createdEntries,
      summary: {
        debitTotal: roundAmount(amount + feeAmount),
        creditTotal: roundAmount(effectiveAmount + feeAmount),
        feeTotal: feeAmount,
        entryCount: entries.length
      }
    };
  }

  /**
   * Get posting summary for a payment
   */
  getPostingSummary(paymentId) {
    const entries = entryRepository.findByPaymentId(paymentId);
    
    if (entries.length === 0) {
      return null;
    }

    let debitTotal = 0;
    let creditTotal = 0;

    entries.forEach(entry => {
      if (entry.entryType === 'DEBIT') {
        debitTotal += entry.amount;
      } else {
        creditTotal += entry.amount;
      }
    });

    return {
      paymentId,
      entryCount: entries.length,
      debitTotal: roundAmount(debitTotal),
      creditTotal: roundAmount(creditTotal),
      isBalanced: Math.abs(debitTotal - creditTotal) < 0.01, // Allow small rounding difference
      entries
    };
  }

  /**
   * Calculate running balance for an account from ledger entries
   */
  calculateAccountBalance(accountId) {
    return entryRepository.getAccountBalance(accountId);
  }
}

module.exports = new LedgerService();
