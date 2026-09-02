const express = require('express');
const router = express.Router();
const axios = require('axios');

const PAYMENT_SERVICE = process.env.PAYMENT_SERVICE_URL || 'http://localhost:3002';

/**
 * POST /api/payments - Initiate a new payment
 */
router.post('/', async (req, res) => {
  try {
    const response = await axios.post(`${PAYMENT_SERVICE}/payments`, req.body);
    res.status(201).json(response.data);
  } catch (error) {
    handleError(res, error, 'Failed to initiate payment');
  }
});

/**
 * GET /api/payments - List all payments
 */
router.get('/', async (req, res) => {
  try {
    const response = await axios.get(`${PAYMENT_SERVICE}/payments`, { params: req.query });
    res.json(response.data);
  } catch (error) {
    handleError(res, error, 'Failed to list payments');
  }
});

/**
 * GET /api/payments/:paymentId - Get payment by ID
 */
router.get('/:paymentId', async (req, res) => {
  try {
    const response = await axios.get(`${PAYMENT_SERVICE}/payments/${req.params.paymentId}`);
    res.json(response.data);
  } catch (error) {
    handleError(res, error, 'Failed to get payment');
  }
});

/**
 * GET /api/payments/:paymentId/details - Get payment with full details
 */
router.get('/:paymentId/details', async (req, res) => {
  try {
    const response = await axios.get(`${PAYMENT_SERVICE}/payments/${req.params.paymentId}/details`);
    res.json(response.data);
  } catch (error) {
    handleError(res, error, 'Failed to get payment details');
  }
});

function handleError(res, error, defaultMsg) {
  if (error.response) {
    res.status(error.response.status).json(error.response.data);
  } else {
    res.status(500).json({ error: { code: 'GATEWAY_ERROR', message: defaultMsg } });
  }
}

module.exports = router;
