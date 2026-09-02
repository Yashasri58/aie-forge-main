/**
 * Payment Orchestrator
 * Coordinates the entire cross-border wire transfer flow
 * This is the core service that calls all other services
 */

const paymentRepository = require('../repositories/paymentRepository');
const accountClient = require('../clients/accountClient');
const validationClient = require('../clients/validationClient');
const fxClient = require('../clients/fxClient');
const ledgerClient = require('../clients/ledgerClient');
const auditClient = require('../clients/auditClient');
const mockHubClient = require('../clients/mockHubClient');
const mockWolfClient = require('../clients/mockWolfClient');
const { generatePaymentId } = require('../utils/idGenerator');
const { calculateFee, roundAmount } = require('../utils/calculator');
const { validatePaymentRequest } = require('../utils/validators');

// Payment statuses
const STATUS = {
  INITIATED: 'INITIATED',
  VALIDATING: 'VALIDATING',
  SCREENING: 'SCREENING',
  PROCESSING: 'PROCESSING',
  POSTING: 'POSTING',
  COMPLETING: 'COMPLETING',
  COMPLETED: 'COMPLETED',
  FAILED: 'FAILED',
  REJECTED: 'REJECTED',
  ON_HOLD: 'ON_HOLD'
};

class PaymentOrchestrator {

  /**
   * Process a new payment request
   * This orchestrates the entire payment flow
   */
  async processPayment(request) {
    const paymentId = generatePaymentId();
    let payment = null;

    try {
      // Step 1: Validate request structure
      console.log(`[${paymentId}] Step 1: Validating request`);
      const validation = validatePaymentRequest(request);
      if (!validation.valid) {
        throw new Error(validation.message);
      }

      // Step 2: Lookup sender account
      console.log(`[${paymentId}] Step 2: Looking up sender account`);
      const sender = await accountClient.lookupAccount(
        request.senderAccountNumber,
        request.senderBankCode
      );

      // Step 3: Lookup receiver account
      console.log(`[${paymentId}] Step 3: Looking up receiver account`);
      const receiver = await accountClient.lookupAccount(
        request.receiverAccountNumber,
        request.receiverBankCode
      );

      // Step 4: Create initial payment record
      console.log(`[${paymentId}] Step 4: Creating payment record`);
      payment = await this.createPaymentRecord(paymentId, request, sender, receiver);
      
      // Log audit event
      await auditClient.logPaymentEvent(paymentId, 'PAYMENT_INITIATED', {
        amount: request.amount,
        currency: request.currency,
        sender: sender.holderName,
        receiver: receiver.holderName
      });

      // Step 5: Run validation rules
      console.log(`[${paymentId}] Step 5: Running validation rules`);
      payment = await paymentRepository.updateStatus(paymentId, STATUS.VALIDATING);
      
      const validationResult = await validationClient.validatePayment({
        paymentId,
        amount: request.amount,
        currency: request.currency,
        targetCurrency: receiver.currency,
        senderAccountId: sender.id,
        senderAccountNumber: sender.accountNumber,
        senderCountry: sender.country,
        receiverAccountId: receiver.id,
        receiverAccountNumber: receiver.accountNumber,
        receiverCountry: receiver.country
      });

      if (!validationResult.valid) {
        await auditClient.logPaymentEvent(paymentId, 'PAYMENT_VALIDATION_FAILED', {
          failedRules: validationResult.rulesFailed
        });
        return this.rejectPayment(paymentId, 'Validation failed: ' + 
          validationResult.rulesFailed.map(r => r.message).join('; '));
      }

      await auditClient.logPaymentEvent(paymentId, 'PAYMENT_VALIDATED', {
        rulesPassed: validationResult.rulesPassed
      });

      // Step 6: Sanctions screening (WOLF)
      console.log(`[${paymentId}] Step 6: Sanctions screening`);
      payment = await paymentRepository.updateStatus(paymentId, STATUS.SCREENING);
      
      const screeningResult = await mockWolfClient.screenPayment({
        paymentId,
        senderName: sender.holderName,
        senderCountry: sender.country,
        receiverName: receiver.holderName,
        receiverCountry: receiver.country,
        amount: request.amount,
        currency: request.currency
      });

      if (screeningResult.result === 'HIT') {
        await auditClient.logPaymentEvent(paymentId, 'PAYMENT_SCREENING_HIT', {
          screeningId: screeningResult.screeningId,
          hits: screeningResult.hits
        });
        return this.holdPayment(paymentId, 'Sanctions screening hit - manual review required');
      }

      await auditClient.logPaymentEvent(paymentId, 'PAYMENT_SCREENED', {
        screeningId: screeningResult.screeningId,
        result: 'CLEAR'
      });

      // Step 7: FX conversion (if cross-currency)
      console.log(`[${paymentId}] Step 7: Processing FX conversion`);
      payment = await paymentRepository.updateStatus(paymentId, STATUS.PROCESSING);
      
      let fxResult = null;
      let targetAmount = request.amount;
      let targetCurrency = request.currency;
      let fxRate = 1;

      if (request.currency !== receiver.currency) {
        fxResult = await fxClient.convertCurrency(
          request.currency,
          receiver.currency,
          request.amount
        );
        targetAmount = fxResult.convertedAmount;
        targetCurrency = receiver.currency;
        fxRate = fxResult.effectiveRate;
      }

      // Step 8: Calculate fees
      const feeAmount = calculateFee(request.amount, request.currency);
      const totalDebit = roundAmount(request.amount + feeAmount);

      // Update payment with FX and fee details
      payment = await paymentRepository.updatePaymentDetails(paymentId, {
        targetAmount,
        targetCurrency,
        fxRate,
        feeAmount,
        totalDebit
      });

      // Step 9: Verify with HUB
      console.log(`[${paymentId}] Step 9: Verifying with HUB`);
      const hubVerification = await mockHubClient.verifyAccount(
        sender.accountNumber,
        sender.bankCode
      );

      if (!hubVerification.verified) {
        return this.failPayment(paymentId, 'HUB verification failed');
      }

      // Step 10: Check sender balance
      console.log(`[${paymentId}] Step 10: Checking sender balance`);
      const balanceInfo = await accountClient.getBalance(sender.id);
      
      if (balanceInfo.balance < totalDebit) {
        return this.failPayment(paymentId, 
          `Insufficient balance. Required: ${totalDebit}, Available: ${balanceInfo.balance}`);
      }

      // Step 11: Create ledger entries
      console.log(`[${paymentId}] Step 11: Creating ledger entries`);
      payment = await paymentRepository.updateStatus(paymentId, STATUS.POSTING);
      
      const ledgerResult = await ledgerClient.createPostingEntries({
        paymentId,
        senderAccountId: sender.id,
        receiverAccountId: receiver.id,
        amount: request.amount,
        currency: request.currency,
        targetAmount,
        targetCurrency,
        feeAmount,
        senderBalanceBefore: balanceInfo.balance,
        receiverBalanceBefore: (await accountClient.getBalance(receiver.id)).balance
      });

      await auditClient.logPaymentEvent(paymentId, 'PAYMENT_POSTED', {
        entryCount: ledgerResult.entries.length,
        debitTotal: ledgerResult.summary.debitTotal,
        creditTotal: ledgerResult.summary.creditTotal
      });

      // Step 12: Execute account updates
      console.log(`[${paymentId}] Step 12: Executing account updates`);
      payment = await paymentRepository.updateStatus(paymentId, STATUS.COMPLETING);
      
      // Debit sender
      await accountClient.debitAccount(sender.id, totalDebit);
      await auditClient.logPaymentEvent(paymentId, 'ACCOUNT_DEBITED', {
        accountId: sender.id,
        amount: totalDebit,
        currency: request.currency
      });

      // Credit receiver
      await accountClient.creditAccount(receiver.id, targetAmount);
      await auditClient.logPaymentEvent(paymentId, 'ACCOUNT_CREDITED', {
        accountId: receiver.id,
        amount: targetAmount,
        currency: targetCurrency
      });

      // Step 13: Complete payment
      console.log(`[${paymentId}] Step 13: Completing payment`);
      payment = await paymentRepository.updateStatus(paymentId, STATUS.COMPLETED);
      
      await auditClient.logPaymentEvent(paymentId, 'PAYMENT_COMPLETED', {
        totalDebit,
        totalCredit: targetAmount,
        fxRate,
        feeAmount
      });

      console.log(`[${paymentId}] Payment completed successfully`);
      return payment;

    } catch (error) {
      console.error(`[${paymentId}] Payment failed:`, error.message);
      
      if (payment) {
        return this.failPayment(paymentId, error.message);
      }
      
      throw error;
    }
  }

  /**
   * Create initial payment record
   */
  async createPaymentRecord(paymentId, request, sender, receiver) {
    return paymentRepository.create({
      paymentId,
      senderAccountId: sender.id,
      senderAccountNumber: sender.accountNumber,
      senderBankCode: sender.bankCode,
      senderName: sender.holderName,
      senderCountry: sender.country,
      receiverAccountId: receiver.id,
      receiverAccountNumber: receiver.accountNumber,
      receiverBankCode: receiver.bankCode,
      receiverName: receiver.holderName,
      receiverCountry: receiver.country,
      amount: request.amount,
      currency: request.currency,
      targetCurrency: receiver.currency,
      reference: request.reference,
      status: STATUS.INITIATED
    });
  }

  /**
   * Mark payment as rejected
   */
  async rejectPayment(paymentId, reason) {
    const payment = await paymentRepository.updateStatus(paymentId, STATUS.REJECTED, reason);
    await auditClient.logPaymentEvent(paymentId, 'PAYMENT_REJECTED', { reason });
    return payment;
  }

  /**
   * Mark payment as failed
   */
  async failPayment(paymentId, reason) {
    const payment = await paymentRepository.updateStatus(paymentId, STATUS.FAILED, reason);
    await auditClient.logPaymentEvent(paymentId, 'PAYMENT_FAILED', { reason });
    return payment;
  }

  /**
   * Put payment on hold
   */
  async holdPayment(paymentId, reason) {
    const payment = await paymentRepository.updateStatus(paymentId, STATUS.ON_HOLD, reason);
    return payment;
  }

  /**
   * Get payment by ID
   */
  async getPayment(paymentId) {
    const payment = paymentRepository.findByPaymentId(paymentId);
    if (!payment) {
      const error = new Error(`Payment not found: ${paymentId}`);
      error.code = 'PAYMENT_NOT_FOUND';
      error.status = 404;
      throw error;
    }
    return payment;
  }

  /**
   * Get payment with full details including audit trail
   */
  async getPaymentDetails(paymentId) {
    const payment = await this.getPayment(paymentId);
    const statusHistory = paymentRepository.getStatusHistory(paymentId);
    const auditTrail = await auditClient.getPaymentAuditTrail(paymentId);
    
    return {
      ...payment,
      statusHistory,
      auditTrail
    };
  }

  /**
   * Get all payments
   */
  getAllPayments(limit, offset) {
    return paymentRepository.findAll(limit, offset);
  }

  /**
   * Get payments by status
   */
  getPaymentsByStatus(status, limit) {
    return paymentRepository.findByStatus(status, limit);
  }
}

module.exports = new PaymentOrchestrator();
