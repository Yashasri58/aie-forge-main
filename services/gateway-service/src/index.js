const express = require('express');
const cors = require('cors');
const paymentRoutes = require('./routes/payments');
const accountRoutes = require('./routes/accounts');
const fxRoutes = require('./routes/fx');
const auditRoutes = require('./routes/audit');

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(cors());
app.use(express.json());

// Request logging
app.use((req, res, next) => {
  console.log(`[${new Date().toISOString()}] ${req.method} ${req.path}`);
  next();
});

// Health check
app.get('/health', (req, res) => {
  res.json({ 
    status: 'healthy', 
    service: 'gateway-service', 
    timestamp: new Date().toISOString() 
  });
});

// API info
app.get('/', (req, res) => {
  res.json({
    name: 'Cross-Border Wire Transfer API',
    version: '1.0.0',
    endpoints: {
      payments: '/api/payments',
      accounts: '/api/accounts',
      fx: '/api/fx',
      audit: '/api/audit'
    }
  });
});

// Routes
app.use('/api/payments', paymentRoutes);
app.use('/api/accounts', accountRoutes);
app.use('/api/fx', fxRoutes);
app.use('/api/audit', auditRoutes);

// Error handler
app.use((err, req, res, next) => {
  console.error('Gateway error:', err.message);
  res.status(err.status || 500).json({
    error: {
      code: err.code || 'GATEWAY_ERROR',
      message: err.message || 'An unexpected error occurred'
    }
  });
});

app.listen(PORT, () => {
  console.log(`Gateway Service running on port ${PORT}`);
});

module.exports = app;
