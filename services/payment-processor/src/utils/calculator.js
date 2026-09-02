/**
 * Fee calculation for cross-border wire transfers
 */

// Fee structure by currency (simplified)
const FEE_RATES = {
  USD: { fixed: 25, percentage: 0.001 },  // $25 + 0.1%
  EUR: { fixed: 20, percentage: 0.001 },  // €20 + 0.1%
  GBP: { fixed: 15, percentage: 0.001 },  // £15 + 0.1%
  SGD: { fixed: 35, percentage: 0.0015 }, // $35 SGD + 0.15%
  JPY: { fixed: 3000, percentage: 0.001 }, // ¥3000 + 0.1%
  CHF: { fixed: 20, percentage: 0.001 },
  AUD: { fixed: 30, percentage: 0.001 },
  CAD: { fixed: 30, percentage: 0.001 },
  HKD: { fixed: 200, percentage: 0.001 }
};

const DEFAULT_FEE = { fixed: 25, percentage: 0.001 };

/**
 * Calculate transfer fee based on amount and currency
 */
function calculateFee(amount, currency) {
  const feeStructure = FEE_RATES[currency] || DEFAULT_FEE;
  const fee = feeStructure.fixed + (amount * feeStructure.percentage);
  return roundAmount(fee);
}

/**
 * Round amount to 2 decimal places
 */
function roundAmount(amount) {
  return Math.round(amount * 100) / 100;
}

/**
 * Calculate total debit (amount + fees)
 */
function calculateTotalDebit(amount, currency) {
  const fee = calculateFee(amount, currency);
  return roundAmount(amount + fee);
}

module.exports = {
  calculateFee,
  roundAmount,
  calculateTotalDebit,
  FEE_RATES
};
