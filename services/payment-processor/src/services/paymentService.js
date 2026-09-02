/**
 * Payment Service
 * Public API facade for payment operations
 */

const orchestrator = require('./orchestrator');

class PaymentService {

  /**
   * Initiate a new cross-border wire transfer
   */
  async initiatePayment(request) {
    return orchestrator.processPayment(request);
  }

  /**
   * Get payment by ID
   */
  async getPayment(paymentId) {
    return orchestrator.getPayment(paymentId);
  }

  /**
   * Get payment with full details (audit trail, status history)
   */
  async getPaymentDetails(paymentId) {
    return orchestrator.getPaymentDetails(paymentId);
  }

  /**
   * List payments with pagination
   */
  listPayments(options = {}) {
    const { limit = 50, offset = 0, status } = options;
    
    if (status) {
      return orchestrator.getPaymentsByStatus(status, limit);
    }
    
    return orchestrator.getAllPayments(limit, offset);
  }
}

module.exports = new PaymentService();
