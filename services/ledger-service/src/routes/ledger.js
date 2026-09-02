const express = require('express');
const router = express.Router();
const ledgerService = require('../services/ledgerService');

// GET /entries - List all entries
router.get('/', (req, res, next) => {
  try {
    const limit = parseInt(req.query.limit) || 100;
    const offset = parseInt(req.query.offset) || 0;
    
    const entries = ledgerService.getAllEntries(limit, offset);
    res.json({
      success: true,
      data: entries,
      count: entries.length,
      pagination: { limit, offset }
    });
  } catch (error) {
    next(error);
  }
});

// POST /entries - Create posting entries for a payment
router.post('/', (req, res, next) => {
  try {
    const postingRequest = req.body;
    
    if (!postingRequest || !postingRequest.paymentId) {
      const error = new Error('Posting request with paymentId is required');
      error.code = 'VALIDATION_ERROR';
      error.status = 400;
      throw error;
    }

    const result = ledgerService.createPostingEntries(postingRequest);
    
    res.status(201).json({
      success: true,
      data: result,
      message: 'Ledger entries created successfully'
    });
  } catch (error) {
    next(error);
  }
});

// GET /entries/payment/:paymentId - Get entries for a payment
router.get('/payment/:paymentId', (req, res, next) => {
  try {
    const entries = ledgerService.getEntriesByPaymentId(req.params.paymentId);
    res.json({
      success: true,
      data: entries,
      count: entries.length
    });
  } catch (error) {
    next(error);
  }
});

// GET /entries/payment/:paymentId/summary - Get posting summary
router.get('/payment/:paymentId/summary', (req, res, next) => {
  try {
    const summary = ledgerService.getPostingSummary(req.params.paymentId);
    
    if (!summary) {
      const error = new Error(`No entries found for payment: ${req.params.paymentId}`);
      error.code = 'NOT_FOUND';
      error.status = 404;
      throw error;
    }

    res.json({
      success: true,
      data: summary
    });
  } catch (error) {
    next(error);
  }
});

// GET /entries/account/:accountId - Get entries for an account
router.get('/account/:accountId', (req, res, next) => {
  try {
    const limit = parseInt(req.query.limit) || 50;
    const entries = ledgerService.getEntriesByAccountId(req.params.accountId, limit);
    res.json({
      success: true,
      data: entries,
      count: entries.length
    });
  } catch (error) {
    next(error);
  }
});

// GET /entries/account/:accountId/balance - Get calculated balance
router.get('/account/:accountId/balance', (req, res, next) => {
  try {
    const balance = ledgerService.calculateAccountBalance(req.params.accountId);
    res.json({
      success: true,
      data: {
        accountId: req.params.accountId,
        calculatedBalance: balance
      }
    });
  } catch (error) {
    next(error);
  }
});

// GET /entries/:entryId - Get single entry
router.get('/:entryId', (req, res, next) => {
  try {
    const entry = ledgerService.getEntryById(req.params.entryId);
    res.json({
      success: true,
      data: entry
    });
  } catch (error) {
    next(error);
  }
});

module.exports = router;
