const express = require('express');
const router = express.Router();
const axios = require('axios');

const ACCOUNT_SERVICE = process.env.ACCOUNT_SERVICE_URL || 'http://localhost:3001';

/**
 * GET /api/accounts - List all accounts
 */
router.get('/', async (req, res) => {
  try {
    const response = await axios.get(`${ACCOUNT_SERVICE}/accounts`, { params: req.query });
    res.json(response.data);
  } catch (error) {
    handleError(res, error, 'Failed to list accounts');
  }
});

/**
 * POST /api/accounts - Create new account
 */
router.post('/', async (req, res) => {
  try {
    const response = await axios.post(`${ACCOUNT_SERVICE}/accounts`, req.body);
    res.status(201).json(response.data);
  } catch (error) {
    handleError(res, error, 'Failed to create account');
  }
});

/**
 * GET /api/accounts/:accountId - Get account by ID
 */
router.get('/:accountId', async (req, res) => {
  try {
    const response = await axios.get(`${ACCOUNT_SERVICE}/accounts/${req.params.accountId}`);
    res.json(response.data);
  } catch (error) {
    handleError(res, error, 'Failed to get account');
  }
});

/**
 * GET /api/accounts/:accountId/balance - Get account balance
 */
router.get('/:accountId/balance', async (req, res) => {
  try {
    const response = await axios.get(`${ACCOUNT_SERVICE}/accounts/${req.params.accountId}/balance`);
    res.json(response.data);
  } catch (error) {
    handleError(res, error, 'Failed to get balance');
  }
});

/**
 * GET /api/accounts/lookup/:accountNumber/:bankCode - Lookup by account number and bank code
 */
router.get('/lookup/:accountNumber/:bankCode', async (req, res) => {
  try {
    const response = await axios.get(
      `${ACCOUNT_SERVICE}/accounts/lookup/${req.params.accountNumber}/${req.params.bankCode}`
    );
    res.json(response.data);
  } catch (error) {
    handleError(res, error, 'Failed to lookup account');
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
