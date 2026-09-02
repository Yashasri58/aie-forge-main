/**
 * API client for gateway-service
 */

const API_BASE = window.API_BASE || 'http://localhost:3000/api';

const api = {
  async get(endpoint) {
    const response = await fetch(`${API_BASE}${endpoint}`);
    if (!response.ok) {
      const error = await response.json().catch(() => ({ message: response.statusText }));
      throw new Error(error.error?.message || error.message);
    }
    return response.json();
  },

  async post(endpoint, data) {
    const response = await fetch(`${API_BASE}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({ message: response.statusText }));
      throw new Error(error.error?.message || error.message);
    }
    return response.json();
  },

  async healthCheck(url) {
    try {
      const response = await fetch(url, { method: 'GET', timeout: 3000 });
      return response.ok;
    } catch {
      return false;
    }
  },

  // Payments
  payments: {
    list: (status) => api.get(status ? `/payments?status=${status}` : '/payments'),
    get: (id) => api.get(`/payments/${id}`),
    getDetails: (id) => api.get(`/payments/${id}/details`),
    create: (data) => api.post('/payments', data)
  },

  // Accounts
  accounts: {
    list: () => api.get('/accounts'),
    get: (id) => api.get(`/accounts/${id}`),
    getBalance: (id) => api.get(`/accounts/${id}/balance`),
    create: (data) => api.post('/accounts', data)
  },

  // FX
  fx: {
    getRates: () => api.get('/fx/rates'),
    getRate: (from, to) => api.get(`/fx/rates/${from}/${to}`),
    convert: (data) => api.post('/fx/convert', { from: data.from, to: data.to, amount: data.amount })
  },

  // Audit
  audit: {
    list: () => api.get('/audit/events'),
    getPaymentTrail: (paymentId) => api.get(`/audit/payments/${paymentId}`)
  },

  // Health checks
  health: {
    gateway: () => api.healthCheck('http://localhost:3000/health'),
    account: () => api.healthCheck('http://localhost:3001/health'),
    payment: () => api.healthCheck('http://localhost:3002/health'),
    validation: () => api.healthCheck('http://localhost:3003/health'),
    ledger: () => api.healthCheck('http://localhost:3004/health'),
    fx: () => api.healthCheck('http://localhost:3005/health'),
    audit: () => api.healthCheck('http://localhost:3006/health')
  }
};

window.api = api;
