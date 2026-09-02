/**
 * ID generators for account service
 * These functions are called from repositories
 */

const { v4: uuidv4 } = require('uuid');

// Counter for sequential IDs (resets on restart, but that's fine for PoV)
let accountCounter = 5; // Start after seeded accounts

/**
 * Generate a unique account ID
 * Format: ACC + 3-digit number
 */
function generateAccountId() {
  accountCounter++;
  return `ACC${String(accountCounter).padStart(3, '0')}`;
}

/**
 * Generate a UUID
 */
function generateUUID() {
  return uuidv4();
}

/**
 * Generate a unique request ID for tracing
 */
function generateRequestId() {
  return `REQ-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

module.exports = {
  generateAccountId,
  generateUUID,
  generateRequestId
};
