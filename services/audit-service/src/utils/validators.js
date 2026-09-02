/**
 * Validators for audit service
 */

const VALID_EVENT_TYPES = [
  'PAYMENT_INITIATED', 'PAYMENT_VALIDATED', 'PAYMENT_VALIDATION_FAILED',
  'PAYMENT_SCREENED', 'PAYMENT_SCREENING_HIT', 'PAYMENT_PROCESSING',
  'PAYMENT_POSTED', 'PAYMENT_COMPLETED', 'PAYMENT_FAILED', 'PAYMENT_REJECTED',
  'ACCOUNT_CREATED', 'ACCOUNT_DEBITED', 'ACCOUNT_CREDITED',
  'ACCOUNT_FROZEN', 'ACCOUNT_ACTIVATED',
  'RATE_UPDATED', 'RULE_MODIFIED'
];

const VALID_ENTITY_TYPES = ['PAYMENT', 'ACCOUNT', 'RATE', 'RULE'];

/**
 * Validate event data
 */
function validateEventData(data) {
  if (!data) {
    return { valid: false, message: 'Event data is required' };
  }

  if (!data.eventType) {
    return { valid: false, message: 'eventType is required' };
  }

  if (!VALID_EVENT_TYPES.includes(data.eventType)) {
    return { valid: false, message: `Invalid eventType. Valid types: ${VALID_EVENT_TYPES.join(', ')}` };
  }

  if (!data.entityType) {
    return { valid: false, message: 'entityType is required' };
  }

  if (!VALID_ENTITY_TYPES.includes(data.entityType)) {
    return { valid: false, message: `Invalid entityType. Valid types: ${VALID_ENTITY_TYPES.join(', ')}` };
  }

  if (!data.entityId) {
    return { valid: false, message: 'entityId is required' };
  }

  return { valid: true };
}

/**
 * Check if event type is valid
 */
function isValidEventType(type) {
  return VALID_EVENT_TYPES.includes(type);
}

module.exports = {
  validateEventData,
  isValidEventType,
  VALID_EVENT_TYPES,
  VALID_ENTITY_TYPES
};
