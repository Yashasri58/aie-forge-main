const rateRepository = require('../repositories/rateRepository');
const { roundToDecimal, applyMarkup, calculateMarkupAmount } = require('../utils/rateCalculator');
const { isValidCurrency, isValidAmount } = require('../utils/currencyValidator');

// Default markup (spread) - 0.5%
const DEFAULT_MARKUP = 0.005;

class ConversionService {

  getAllRates() {
    const rates = rateRepository.findAll();
    return rates.map(r => ({
      from: r.from_currency,
      to: r.to_currency,
      rate: r.rate,
      updatedAt: r.updated_at
    }));
  }

  getRate(fromCurrency, toCurrency) {
    // Validate currencies
    if (!isValidCurrency(fromCurrency)) {
      const error = new Error(`Invalid source currency: ${fromCurrency}`);
      error.code = 'INVALID_CURRENCY';
      error.status = 400;
      throw error;
    }

    if (!isValidCurrency(toCurrency)) {
      const error = new Error(`Invalid target currency: ${toCurrency}`);
      error.code = 'INVALID_CURRENCY';
      error.status = 400;
      throw error;
    }

    // Same currency - rate is 1
    if (fromCurrency.toUpperCase() === toCurrency.toUpperCase()) {
      return {
        from: fromCurrency.toUpperCase(),
        to: toCurrency.toUpperCase(),
        baseRate: 1,
        effectiveRate: 1,
        markup: 0
      };
    }

    const rateData = rateRepository.findByPair(fromCurrency, toCurrency);
    
    if (!rateData) {
      const error = new Error(`No exchange rate found for ${fromCurrency} to ${toCurrency}`);
      error.code = 'RATE_NOT_FOUND';
      error.status = 404;
      throw error;
    }

    const effectiveRate = applyMarkup(rateData.rate, DEFAULT_MARKUP);

    return {
      from: rateData.from_currency,
      to: rateData.to_currency,
      baseRate: rateData.rate,
      effectiveRate: effectiveRate,
      markup: DEFAULT_MARKUP,
      updatedAt: rateData.updated_at
    };
  }

  convert(fromCurrency, toCurrency, amount) {
    // Validate amount
    if (!isValidAmount(amount)) {
      const error = new Error('Invalid amount. Must be a positive number.');
      error.code = 'INVALID_AMOUNT';
      error.status = 400;
      throw error;
    }

    // Get rate
    const rateInfo = this.getRate(fromCurrency, toCurrency);

    // Calculate converted amount
    const convertedAmount = roundToDecimal(amount * rateInfo.effectiveRate, 2);
    const markupAmount = calculateMarkupAmount(amount, rateInfo.baseRate, DEFAULT_MARKUP);

    return {
      from: rateInfo.from,
      to: rateInfo.to,
      originalAmount: amount,
      convertedAmount: convertedAmount,
      baseRate: rateInfo.baseRate,
      effectiveRate: rateInfo.effectiveRate,
      markup: rateInfo.markup,
      markupAmount: markupAmount
    };
  }

  getRatesForCurrency(currency) {
    if (!isValidCurrency(currency)) {
      const error = new Error(`Invalid currency: ${currency}`);
      error.code = 'INVALID_CURRENCY';
      error.status = 400;
      throw error;
    }

    const rates = rateRepository.findByFromCurrency(currency);
    return rates.map(r => ({
      from: r.from_currency,
      to: r.to_currency,
      baseRate: r.rate,
      effectiveRate: applyMarkup(r.rate, DEFAULT_MARKUP),
      updatedAt: r.updated_at
    }));
  }
}

module.exports = new ConversionService();
