const auditRepository = require('../repositories/auditRepository');
const { generateEventId, generateIntegrityHash } = require('../utils/idGenerator');
const { validateEventData } = require('../utils/validators');
const { formatEventForLog } = require('../utils/formatters');

// Valid event types for cross-border wire transfers
const EVENT_TYPES = {
  // Payment events
  PAYMENT_INITIATED: 'PAYMENT_INITIATED',
  PAYMENT_VALIDATED: 'PAYMENT_VALIDATED',
  PAYMENT_VALIDATION_FAILED: 'PAYMENT_VALIDATION_FAILED',
  PAYMENT_SCREENED: 'PAYMENT_SCREENED',
  PAYMENT_SCREENING_HIT: 'PAYMENT_SCREENING_HIT',
  PAYMENT_PROCESSING: 'PAYMENT_PROCESSING',
  PAYMENT_POSTED: 'PAYMENT_POSTED',
  PAYMENT_COMPLETED: 'PAYMENT_COMPLETED',
  PAYMENT_FAILED: 'PAYMENT_FAILED',
  PAYMENT_REJECTED: 'PAYMENT_REJECTED',
  
  // Account events
  ACCOUNT_CREATED: 'ACCOUNT_CREATED',
  ACCOUNT_DEBITED: 'ACCOUNT_DEBITED',
  ACCOUNT_CREDITED: 'ACCOUNT_CREDITED',
  ACCOUNT_FROZEN: 'ACCOUNT_FROZEN',
  ACCOUNT_ACTIVATED: 'ACCOUNT_ACTIVATED',
  
  // System events
  RATE_UPDATED: 'RATE_UPDATED',
  RULE_MODIFIED: 'RULE_MODIFIED'
};

class AuditService {

  getAllEvents(limit, offset) {
    return auditRepository.findAll(limit, offset);
  }

  getEventById(eventId) {
    const event = auditRepository.findByEventId(eventId);
    if (!event) {
      const error = new Error(`Event not found: ${eventId}`);
      error.code = 'EVENT_NOT_FOUND';
      error.status = 404;
      throw error;
    }
    return event;
  }

  getEventsByPaymentId(paymentId) {
    return auditRepository.findByEntityId('PAYMENT', paymentId);
  }

  getEventsByAccountId(accountId) {
    return auditRepository.findByEntityId('ACCOUNT', accountId);
  }

  getEventsByType(eventType) {
    return auditRepository.findByEventType(eventType);
  }

  /**
   * Log an audit event
   */
  logEvent(eventData) {
    // Validate event data
    const validation = validateEventData(eventData);
    if (!validation.valid) {
      const error = new Error(validation.message);
      error.code = 'VALIDATION_ERROR';
      error.status = 400;
      throw error;
    }

    // Generate event ID and integrity hash
    const eventId = generateEventId();
    const integrityHash = generateIntegrityHash({
      eventId,
      eventType: eventData.eventType,
      entityType: eventData.entityType,
      entityId: eventData.entityId,
      details: eventData.details,
      timestamp: new Date().toISOString()
    });

    const event = {
      eventId,
      eventType: eventData.eventType,
      entityType: eventData.entityType,
      entityId: eventData.entityId,
      actor: eventData.actor || 'SYSTEM',
      action: eventData.action || eventData.eventType,
      details: eventData.details,
      previousState: eventData.previousState,
      newState: eventData.newState,
      ipAddress: eventData.ipAddress,
      integrityHash
    };

    const created = auditRepository.create(event);
    
    // Log to console for visibility
    console.log(`[AUDIT] ${formatEventForLog(created)}`);

    return created;
  }

  /**
   * Log payment status change
   */
  logPaymentStatusChange(paymentId, eventType, details = {}) {
    return this.logEvent({
      eventType,
      entityType: 'PAYMENT',
      entityId: paymentId,
      actor: 'PAYMENT_PROCESSOR',
      details
    });
  }

  /**
   * Log account balance change
   */
  logAccountChange(accountId, eventType, details = {}) {
    return this.logEvent({
      eventType,
      entityType: 'ACCOUNT',
      entityId: accountId,
      actor: 'ACCOUNT_SERVICE',
      details
    });
  }

  /**
   * Get event types
   */
  getEventTypes() {
    return EVENT_TYPES;
  }

  /**
   * Get audit trail for a payment
   */
  getPaymentAuditTrail(paymentId) {
    const events = this.getEventsByPaymentId(paymentId);
    return {
      paymentId,
      eventCount: events.length,
      timeline: events.map(e => ({
        eventId: e.eventId,
        eventType: e.eventType,
        action: e.action,
        timestamp: e.createdAt,
        details: e.details
      }))
    };
  }
}

module.exports = new AuditService();
