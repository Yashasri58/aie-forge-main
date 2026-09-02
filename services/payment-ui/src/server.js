const express = require('express');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 8080;

// Serve static files
app.use(express.static(path.join(__dirname, '../public')));

// Inject API_BASE if needed
app.get('/config.js', (req, res) => {
  const apiBase = process.env.API_BASE || 'http://localhost:3000/api';
  res.type('application/javascript');
  res.send(`window.API_BASE = '${apiBase}';`);
});

// SPA fallback
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, '../public/index.html'));
});

app.listen(PORT, () => {
  console.log(`Payment UI running on port ${PORT}`);
});
