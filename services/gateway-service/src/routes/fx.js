const express = require('express');
const router = express.Router();
const axios = require('axios');

const FX_SERVICE = process.env.FX_SERVICE_URL || 'http://localhost:3005';

/**
 * GET /api/fx/rates - Get all FX rates
 */
router.get('/rates', async (req, res) => {
  try {
    const response = await axios.get(`${FX_SERVICE}/rates`, { params: req.query });
    res.json(response.data);
  } catch (error) {
    handleError(res, error, 'Failed to get FX rates');
  }
});

/**
 * GET /api/fx/rates/:baseCurrency/:targetCurrency - Get specific rate
 */
router.get('/rates/:baseCurrency/:targetCurrency', async (req, res) => {
  try {
    const response = await axios.get(
      `${FX_SERVICE}/rates/${req.params.baseCurrency}/${req.params.targetCurrency}`
    );
    res.json(response.data);
  } catch (error) {
    handleError(res, error, 'Failed to get FX rate');
  }
});

/**
 * POST /api/fx/convert - Convert currency
 */
router.post('/convert', async (req, res) => {
  try {
    const response = await axios.post(`${FX_SERVICE}/convert`, req.body);
    res.json(response.data);
  } catch (error) {
    handleError(res, error, 'Failed to convert currency');
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
