/**
 * Rate calculation utilities
 * Called from conversionService and other modules
 */

/**
 * Round a number to specified decimal places
 */
function roundToDecimal(value, decimals = 2) {
  const multiplier = Math.pow(10, decimals);
  return Math.round(value * multiplier) / multiplier;
}

/**
 * Apply markup (spread) to a rate
 * Markup reduces the effective rate for the customer
 */
function applyMarkup(baseRate, markupPercent) {
  // For selling currency (customer buys foreign), reduce the rate
  const effectiveRate = baseRate * (1 - markupPercent);
  return roundToDecimal(effectiveRate, 6);
}

/**
 * Calculate the markup amount in source currency
 */
function calculateMarkupAmount(amount, baseRate, markupPercent) {
  const withoutMarkup = amount * baseRate;
  const withMarkup = amount * applyMarkup(baseRate, markupPercent);
  const markupAmount = withoutMarkup - withMarkup;
  return roundToDecimal(markupAmount, 2);
}

/**
 * Calculate inverse rate
 */
function calculateInverseRate(rate) {
  if (rate === 0) return 0;
  return roundToDecimal(1 / rate, 6);
}

/**
 * Calculate mid-market rate from bid and ask
 */
function calculateMidMarketRate(bidRate, askRate) {
  return roundToDecimal((bidRate + askRate) / 2, 6);
}

/**
 * Calculate percentage difference between two rates
 */
function calculateRateDifference(rate1, rate2) {
  if (rate1 === 0) return 0;
  const diff = ((rate2 - rate1) / rate1) * 100;
  return roundToDecimal(diff, 4);
}

module.exports = {
  roundToDecimal,
  applyMarkup,
  calculateMarkupAmount,
  calculateInverseRate,
  calculateMidMarketRate,
  calculateRateDifference
};
