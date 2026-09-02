const express = require('express');
const router = express.Router();
const axios = require('axios');

const AUDIT_SERVICE = process.env.AUDIT_SERVICE_URL || 'http://localhost:3006';

/**
 * GET /api/audit/events - List audit events
 */
router.get('/events', async (req, res) => {
  try {
    const response = await axios.get(`${AUDIT_SERVICE}/events`, { params: req.query });
    res.json(response.data);
  } catch (error) {
    handleError(res, error, 'Failed to list audit events');
  }
});

/**
 * GET /api/audit/events/:eventId - Get specific audit event
 */
router.get('/events/:eventId', async (req, res) => {
  try {
    const response = await axios.get(`${AUDIT_SERVICE}/events/${req.params.eventId}`);
    res.json(response.data);
  } catch (error) {
    handleError(res, error, 'Failed to get audit event');
  }
});

/**
 * GET /api/audit/payments/:paymentId - Get audit trail for a payment
 */
router.get('/payments/:paymentId', async (req, res) => {
  try {
    const response = await axios.get(`${AUDIT_SERVICE}/events/payment/${req.params.paymentId}/trail`);
    res.json(response.data);
  } catch (error) {
    handleError(res, error, 'Failed to get payment audit trail');
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
