/**
 * Country Rules
 * Validates sender/receiver countries against blocked and high-risk lists
 */

/**
 * Check if either country is in blocked list
 */
async function checkBlockedCountries(payment, params) {
  const { senderCountry, receiverCountry } = payment;
  const blockedList = params.blocked || [];

  if (blockedList.includes(senderCountry)) {
    return {
      passed: false,
      message: `Sender country ${senderCountry} is blocked for transfers`
    };
  }

  if (blockedList.includes(receiverCountry)) {
    return {
      passed: false,
      message: `Receiver country ${receiverCountry} is blocked for transfers`
    };
  }

  return { passed: true };
}

/**
 * Check if either country is in high-risk list
 * High-risk doesn't fail, but generates a warning
 */
async function checkHighRiskCountries(payment, params) {
  const { senderCountry, receiverCountry } = payment;
  const highRiskList = params.highRisk || [];

  const warnings = [];

  if (highRiskList.includes(senderCountry)) {
    warnings.push(`Sender country ${senderCountry} is classified as high-risk`);
  }

  if (highRiskList.includes(receiverCountry)) {
    warnings.push(`Receiver country ${receiverCountry} is classified as high-risk`);
  }

  if (warnings.length > 0) {
    return {
      passed: true,
      warning: warnings.join('; ')
    };
  }

  return { passed: true };
}

/**
 * Validate country code format
 */
function isValidCountryCode(code) {
  return typeof code === 'string' && /^[A-Z]{2}$/.test(code);
}

/**
 * Get country name from code (simplified)
 */
function getCountryName(code) {
  const countries = {
    'GB': 'United Kingdom',
    'DE': 'Germany',
    'US': 'United States',
    'SG': 'Singapore',
    'ES': 'Spain',
    'FR': 'France',
    'IT': 'Italy',
    'JP': 'Japan',
    'CH': 'Switzerland',
    'AU': 'Australia',
    'CA': 'Canada',
    'NK': 'North Korea',
    'IR': 'Iran',
    'SY': 'Syria',
    'CU': 'Cuba',
    'RU': 'Russia',
    'BY': 'Belarus',
    'VE': 'Venezuela',
    'MM': 'Myanmar'
  };
  return countries[code] || code;
}

module.exports = {
  checkBlockedCountries,
  checkHighRiskCountries,
  isValidCountryCode,
  getCountryName
};
