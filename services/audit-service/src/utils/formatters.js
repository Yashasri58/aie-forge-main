/**
 * Formatters for audit service
 */

/**
 * Format database row to API response
 */
function formatEventResponse(row) {
  if (!row) return null;

  let details = null;
  let previousState = null;
  let newState = null;

  try {
    details = row.details ? JSON.parse(row.details) : null;
    previousState = row.previous_state ? JSON.parse(row.previous_state) : null;
    newState = row.new_state ? JSON.parse(row.new_state) : null;
  } catch (e) {
    // Keep as string if not valid JSON
    details = row.details;
    previousState = row.previous_state;
    newState = row.new_state;
  }

  return {
    id: row.id,
    eventId: row.event_id,
    eventType: row.event_type,
    entityType: row.entity_type,
    entityId: row.entity_id,
    actor: row.actor,
    action: row.action,
    details,
    previousState,
    newState,
    ipAddress: row.ip_address,
    integrityHash: row.integrity_hash,
    createdAt: row.created_at
  };
}

/**
 * Format event for console logging
 */
function formatEventForLog(event) {
  return `${event.eventType} | ${event.entityType}:${event.entityId} | Actor: ${event.actor}`;
}

/**
 * Format event for timeline display
 */
function formatEventForTimeline(event) {
  return {
    time: event.createdAt,
    type: event.eventType,
    description: getEventDescription(event),
    actor: event.actor
  };
}

/**
 * Get human-readable description for event
 */
function getEventDescription(event) {
  const descriptions = {
    PAYMENT_INITIATED: 'Payment was initiated',
    PAYMENT_VALIDATED: 'Payment passed validation',
    PAYMENT_VALIDATION_FAILED: 'Payment failed validation',
    PAYMENT_SCREENED: 'Payment passed sanctions screening',
    PAYMENT_SCREENING_HIT: 'Payment flagged by sanctions screening',
    PAYMENT_PROCESSING: 'Payment is being processed',
    PAYMENT_POSTED: 'Payment entries posted to ledger',
    PAYMENT_COMPLETED: 'Payment completed successfully',
    PAYMENT_FAILED: 'Payment failed',
    PAYMENT_REJECTED: 'Payment was rejected',
    ACCOUNT_CREATED: 'Account was created',
    ACCOUNT_DEBITED: 'Account was debited',
    ACCOUNT_CREDITED: 'Account was credited',
    ACCOUNT_FROZEN: 'Account was frozen',
    ACCOUNT_ACTIVATED: 'Account was activated'
  };
  return descriptions[event.eventType] || event.eventType;
}

module.exports = {
  formatEventResponse,
  formatEventForLog,
  formatEventForTimeline,
  getEventDescription
};
