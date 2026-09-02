const express = require('express');
const router = express.Router();
const paymentService = require('../services/paymentService');
const { formatErrorResponse, formatPaymentSummary } = require('../utils/formatters');

/**
 * POST /payments - Initiate a new payment
 */
router.post('/', async (req, res) => {
  try {
    const payment = await paymentService.initiatePayment(req.body);
    res.status(201).json(payment);
  } catch (error) {
    console.error('Payment initiation failed:', error.message);
    
    if (error.code === 'ACCOUNT_NOT_FOUND') {
      return res.status(404).json(formatErrorResponse(error));
    }
    if (error.code === 'VALIDATION_ERROR') {
      return res.status(400).json(formatErrorResponse(error));
    }
    
    res.status(500).json(formatErrorResponse(error));
  }
});

/**
 * GET /payments - List all payments
 */
router.get('/', async (req, res) => {
  try {
    const { limit = 50, offset = 0, status } = req.query;
    const payments = paymentService.listPayments({
      limit: parseInt(limit),
      offset: parseInt(offset),
      status
    });
    
    res.json({
      payments,
      count: payments.length,
      limit: parseInt(limit),
      offset: parseInt(offset)
    });
  } catch (error) {
    console.error('Failed to list payments:', error.message);
    res.status(500).json(formatErrorResponse(error));
  }
});

/**
 * GET /payments/:paymentId - Get payment by ID
 */
router.get('/:paymentId', async (req, res) => {
  try {
    const payment = await paymentService.getPayment(req.params.paymentId);
    res.json(payment);
  } catch (error) {
    console.error('Failed to get payment:', error.message);
    
    if (error.code === 'PAYMENT_NOT_FOUND') {
      return res.status(404).json(formatErrorResponse(error));
    }
    
    res.status(500).json(formatErrorResponse(error));
  }
});

/**
 * GET /payments/:paymentId/details - Get payment with full details
 */
router.get('/:paymentId/details', async (req, res) => {
  try {
    const details = await paymentService.getPaymentDetails(req.params.paymentId);
    res.json(details);
  } catch (error) {
    console.error('Failed to get payment details:', error.message);
    
    if (error.code === 'PAYMENT_NOT_FOUND') {
      return res.status(404).json(formatErrorResponse(error));
    }
    
    res.status(500).json(formatErrorResponse(error));
  }
});

/**
 * GET /payments/status/:status - Get payments by status
 */
router.get('/status/:status', async (req, res) => {
  try {
    const { limit = 50 } = req.query;
    const payments = paymentService.listPayments({
      status: req.params.status,
      limit: parseInt(limit)
    });
    
    res.json({
      status: req.params.status,
      payments,
      count: payments.length
    });
  } catch (error) {
    console.error('Failed to get payments by status:', error.message);
    res.status(500).json(formatErrorResponse(error));
  }
});

module.exports = router;
