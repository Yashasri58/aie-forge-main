/**
 * ID generators for ledger service
 */

const { v4: uuidv4 } = require('uuid');

let entryCounter = 0;

/**
 * Generate unique entry ID
 * Format: ENT-{timestamp}-{counter}
 */
function generateEntryId() {
  entryCounter++;
  const timestamp = Date.now().toString(36);
  return `ENT-${timestamp}-${String(entryCounter).padStart(4, '0')}`;
}

/**
 * Generate UUID
 */
function generateUUID() {
  return uuidv4();
}

module.exports = {
  generateEntryId,
  generateUUID
};
