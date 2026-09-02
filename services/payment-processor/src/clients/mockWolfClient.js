/**
 * Mock WOLF Client
 * Simulates external WOLF (sanctions screening) system
 * In real system, this would call external sanctions API
 */

// Mock blocklist for demo
const BLOCKED_NAMES = [
  'TEST BLOCKED',
  'SANCTIONS TARGET',
  'BLOCKED ENTITY'
];

const BLOCKED_COUNTRIES = ['NK', 'IR', 'SY', 'CU'];

/**
 * Simulate network delay
 */
function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Screen a payment for sanctions
 */
async function screenPayment(payment) {
  // Simulate network delay (200-500ms - sanctions checks are slower)
  await delay(200 + Math.random() * 300);
  
  const screeningId = `SCR-${Date.now()}-${Math.random().toString(36).substr(2, 6)}`;
  const checkedLists = ['OFAC', 'EU', 'UN', 'HMT'];
  
  console.log(`[MOCK WOLF] Screening payment ${payment.paymentId || 'NEW'}`);
  
  const hits = [];
  
  // Check sender name against blocklist
  const senderName = (payment.senderName || '').toUpperCase();
  for (const blocked of BLOCKED_NAMES) {
    if (senderName.includes(blocked)) {
      hits.push({
        type: 'NAME_MATCH',
        party: 'SENDER',
        matchedName: blocked,
        list: 'INTERNAL',
        score: 100
      });
    }
  }
  
  // Check receiver name against blocklist
  const receiverName = (payment.receiverName || '').toUpperCase();
  for (const blocked of BLOCKED_NAMES) {
    if (receiverName.includes(blocked)) {
      hits.push({
        type: 'NAME_MATCH',
        party: 'RECEIVER',
        matchedName: blocked,
        list: 'INTERNAL',
        score: 100
      });
    }
  }
  
  // Check countries
  if (BLOCKED_COUNTRIES.includes(payment.senderCountry)) {
    hits.push({
      type: 'COUNTRY_MATCH',
      party: 'SENDER',
      matchedCountry: payment.senderCountry,
      list: 'OFAC',
      score: 100
    });
  }
  
  if (BLOCKED_COUNTRIES.includes(payment.receiverCountry)) {
    hits.push({
      type: 'COUNTRY_MATCH',
      party: 'RECEIVER',
      matchedCountry: payment.receiverCountry,
      list: 'OFAC',
      score: 100
    });
  }
  
  // Random 2% hit rate for demo (false positives)
  if (hits.length === 0 && Math.random() < 0.02) {
    hits.push({
      type: 'FUZZY_NAME_MATCH',
      party: 'RECEIVER',
      matchedName: 'Similar name on watchlist',
      list: 'EU',
      score: 75
    });
  }
  
  const result = hits.length > 0 ? 'HIT' : 'CLEAR';
  
  return {
    screeningId,
    result,
    checkedLists,
    hits,
    hitCount: hits.length,
    screenedAt: new Date().toISOString(),
    message: result === 'CLEAR' 
      ? 'No sanctions matches found' 
      : `${hits.length} potential match(es) found - review required`
  };
}

/**
 * Get screening result by ID
 */
async function getScreeningResult(screeningId) {
  await delay(50);
  
  // In real system, would fetch from database
  return {
    screeningId,
    status: 'COMPLETED',
    message: 'Screening result retrieved'
  };
}

module.exports = {
  screenPayment,
  getScreeningResult,
  BLOCKED_COUNTRIES
};
