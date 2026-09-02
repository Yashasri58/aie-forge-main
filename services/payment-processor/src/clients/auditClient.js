/**
 * HTTP Client for Audit Service
 * Makes HTTP calls to audit-service
 */

const AUDIT_SERVICE_URL = process.env.AUDIT_SERVICE_URL || 'http://localhost:3006';

/**
 * Log an audit event
 */
async function logEvent(eventData) {
  try {
    const response = await fetch(`${AUDIT_SERVICE_URL}/events`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(eventData)
    });
    
    const data = await response.json();
    
    if (!response.ok) {
      console.error('Audit log failed:', data.error?.message);
      return null;
    }
    
    return data.data;
  } catch (error) {
    // Don't fail payment if audit logging fails
    console.error('Audit service unavailable:', error.message);
    return null;
  }
}

/**
 * Log payment event
 */
async function logPaymentEvent(paymentId, eventType, details = {}) {
  return logEvent({
    eventType,
    entityType: 'PAYMENT',
    entityId: paymentId,
    actor: 'PAYMENT_PROCESSOR',
    details
  });
}

/**
 * Get audit trail for a payment
 */
async function getPaymentAuditTrail(paymentId) {
  try {
    const response = await fetch(`${AUDIT_SERVICE_URL}/events/payment/${paymentId}/trail`);
    const data = await response.json();
    
    if (!response.ok) {
      return null;
    }
    
    return data.data;
  } catch (error) {
    console.error('Failed to get audit trail:', error.message);
    return null;
  }
}

module.exports = {
  logEvent,
  logPaymentEvent,
  getPaymentAuditTrail
};
