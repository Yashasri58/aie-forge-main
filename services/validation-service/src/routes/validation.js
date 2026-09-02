const express = require('express');
const router = express.Router();
const validationService = require('../services/validationService');

// POST /validate - Validate a payment
router.post('/validate', async (req, res, next) => {
  try {
    const paymentData = req.body;
    
    if (!paymentData || Object.keys(paymentData).length === 0) {
      const error = new Error('Payment data is required');
      error.code = 'VALIDATION_ERROR';
      error.status = 400;
      throw error;
    }

    const result = await validationService.validatePayment(paymentData);
    
    res.json({
      success: true,
      data: result
    });
  } catch (error) {
    next(error);
  }
});

// GET /rules - List all rules
router.get('/rules', async (req, res, next) => {
  try {
    const rules = await validationService.getAllRules();
    res.json({
      success: true,
      data: rules,
      count: rules.length
    });
  } catch (error) {
    next(error);
  }
});

// GET /rules/active - List active rules only
router.get('/rules/active', async (req, res, next) => {
  try {
    const rules = await validationService.getActiveRules();
    res.json({
      success: true,
      data: rules,
      count: rules.length
    });
  } catch (error) {
    next(error);
  }
});

// GET /rules/:id - Get rule by ID
router.get('/rules/:id', async (req, res, next) => {
  try {
    const rule = await validationService.getRuleById(req.params.id);
    res.json({
      success: true,
      data: rule
    });
  } catch (error) {
    next(error);
  }
});

// PUT /rules/:id/toggle - Enable/disable a rule
router.put('/rules/:id/toggle', async (req, res, next) => {
  try {
    const { isActive } = req.body;
    
    if (isActive === undefined) {
      const error = new Error('isActive is required');
      error.code = 'VALIDATION_ERROR';
      error.status = 400;
      throw error;
    }

    const rule = await validationService.toggleRule(req.params.id, isActive);
    res.json({
      success: true,
      data: rule,
      message: `Rule ${isActive ? 'enabled' : 'disabled'}`
    });
  } catch (error) {
    next(error);
  }
});

module.exports = router;
