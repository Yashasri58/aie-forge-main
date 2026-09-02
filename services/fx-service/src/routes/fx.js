const express = require('express');
const conversionService = require('../services/conversionService');

const ratesRouter = express.Router();
const convertRouter = express.Router();

// GET /rates - Get all exchange rates
ratesRouter.get('/', (req, res, next) => {
  try {
    const rates = conversionService.getAllRates();
    res.json({
      success: true,
      data: rates,
      count: rates.length
    });
  } catch (error) {
    next(error);
  }
});

// GET /rates/:from/:to - Get specific exchange rate
ratesRouter.get('/:from/:to', (req, res, next) => {
  try {
    const { from, to } = req.params;
    const rate = conversionService.getRate(from, to);
    res.json({
      success: true,
      data: rate
    });
  } catch (error) {
    next(error);
  }
});

// GET /rates/:from - Get all rates for a currency
ratesRouter.get('/:from', (req, res, next) => {
  try {
    const { from } = req.params;
    const rates = conversionService.getRatesForCurrency(from);
    res.json({
      success: true,
      data: rates,
      count: rates.length
    });
  } catch (error) {
    next(error);
  }
});

// POST /convert - Convert amount between currencies
convertRouter.post('/', (req, res, next) => {
  try {
    const { from, to, amount } = req.body;

    if (!from || !to || amount === undefined) {
      const error = new Error('from, to, and amount are required');
      error.code = 'VALIDATION_ERROR';
      error.status = 400;
      throw error;
    }

    const result = conversionService.convert(from, to, parseFloat(amount));
    res.json({
      success: true,
      data: result
    });
  } catch (error) {
    next(error);
  }
});

// GET /convert - Convert via query params
convertRouter.get('/', (req, res, next) => {
  try {
    const { from, to, amount } = req.query;

    if (!from || !to || !amount) {
      const error = new Error('from, to, and amount query params are required');
      error.code = 'VALIDATION_ERROR';
      error.status = 400;
      throw error;
    }

    const result = conversionService.convert(from, to, parseFloat(amount));
    res.json({
      success: true,
      data: result
    });
  } catch (error) {
    next(error);
  }
});

module.exports = { ratesRouter, convertRouter };
