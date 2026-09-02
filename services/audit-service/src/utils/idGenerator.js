/**
 * ID generators for audit service
 */

const { v4: uuidv4 } = require('uuid');
const crypto = require('crypto');

let eventCounter = 0;

/**
 * Generate unique event ID
 * Format: EVT-{timestamp}-{counter}
 */
function generateEventId() {
  eventCounter++;
  const timestamp = Date.now().toString(36);
  return `EVT-${timestamp}-${String(eventCounter).padStart(4, '0')}`;
}

/**
 * Generate integrity hash for event data
 * Used to detect tampering with audit records
 */
function generateIntegrityHash(data) {
  const content = JSON.stringify(data);
  return crypto.createHash('sha256').update(content).digest('hex');
}

/**
 * Verify integrity hash
 */
function verifyIntegrityHash(data, hash) {
  const computed = generateIntegrityHash(data);
  return computed === hash;
}

/**
 * Generate UUID
 */
function generateUUID() {
  return uuidv4();
}

module.exports = {
  generateEventId,
  generateIntegrityHash,
  verifyIntegrityHash,
  generateUUID
};
