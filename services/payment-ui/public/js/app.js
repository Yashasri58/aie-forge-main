/**
 * Payment UI Application
 * Supports both Admin and Account Holder logins
 */

let accountsCache = [];
let currentUser = null; // { type: 'admin' | 'customer', account?: {...} }

document.addEventListener('DOMContentLoaded', () => {
  initLoginTabs();
  initLogin();
  initTabs();
  initPaymentForm();
  initModal();
  initAdmin();
  initFxConverter();
});

// ========== LOGIN TABS ==========
function initLoginTabs() {
  const tabs = document.querySelectorAll('.login-tab');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      
      const type = tab.dataset.loginType;
      document.getElementById('customer-login-form').classList.toggle('hidden', type !== 'customer');
      document.getElementById('admin-login-form').classList.toggle('hidden', type !== 'admin');
    });
  });
}

// ========== LOGIN ==========
function initLogin() {
  const customerForm = document.getElementById('customer-login-form');
  const adminForm = document.getElementById('admin-login-form');
  const logoutBtn = document.getElementById('logout-btn');
  
  // Check if already logged in
  const savedUser = sessionStorage.getItem('currentUser');
  if (savedUser) {
    currentUser = JSON.parse(savedUser);
    showApp();
  }
  
  // Customer login
  customerForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const accountNumber = document.getElementById('account-number').value.trim();
    const bankCode = document.getElementById('bank-code').value.trim().toUpperCase();
    
    try {
      // Look up account
      const data = await api.accounts.list();
      const accounts = data.data || data.accounts || data;
      const account = accounts.find(a => 
        a.accountNumber === accountNumber && a.bankCode === bankCode
      );
      
      if (!account) {
        alert('Account not found. Please check your account number and bank code.');
        return;
      }
      
      currentUser = { type: 'customer', account };
      sessionStorage.setItem('currentUser', JSON.stringify(currentUser));
      showApp();
    } catch (error) {
      alert('Login failed: ' + error.message);
    }
  });
  
  // Admin login
  adminForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    
    if (username === 'admin' && password === 'admin') {
      currentUser = { type: 'admin', username };
      sessionStorage.setItem('currentUser', JSON.stringify(currentUser));
      showApp();
    } else {
      alert('Invalid credentials. Use admin/admin');
    }
  });
  
  logoutBtn.addEventListener('click', () => {
    currentUser = null;
    sessionStorage.clear();
    document.getElementById('login-page').classList.remove('hidden');
    document.getElementById('app-page').classList.add('hidden');
    // Reset to customer tab
    document.querySelectorAll('.login-tab').forEach(t => t.classList.remove('active'));
    document.querySelector('.login-tab[data-login-type="customer"]').classList.add('active');
    document.getElementById('customer-login-form').classList.remove('hidden');
    document.getElementById('admin-login-form').classList.add('hidden');
  });
}

function showApp() {
  document.getElementById('login-page').classList.add('hidden');
  document.getElementById('app-page').classList.remove('hidden');
  
  const isAdmin = currentUser.type === 'admin';
  
  // Update header
  if (isAdmin) {
    document.getElementById('current-user').textContent = `Admin: ${currentUser.username}`;
  } else {
    document.getElementById('current-user').textContent = `${currentUser.account.holderName}`;
  }
  
  // Show/hide admin-only tabs
  document.querySelectorAll('.admin-only').forEach(el => {
    el.classList.toggle('hidden', !isAdmin);
  });
  
  // Load initial data
  loadAccounts();
  
  // For customers, load their account details
  if (!isAdmin) {
    loadMyAccount();
  }
}

// ========== TABS ==========
function initTabs() {
  const tabs = document.querySelectorAll('.tab');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      if (tab.classList.contains('hidden')) return;
      
      tabs.forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      
      tab.classList.add('active');
      document.getElementById(tab.dataset.tab).classList.add('active');
      
      switch (tab.dataset.tab) {
        case 'payments': loadPayments(); break;
        case 'my-accounts': loadMyAccount(); break;
        case 'accounts': loadAccountsTab(); break;
        case 'fx-rates': loadRates(); break;
        case 'admin': loadAdmin(); break;
      }
    });
  });

  document.getElementById('refresh-payments').addEventListener('click', loadPayments);
  document.getElementById('refresh-accounts').addEventListener('click', loadAccountsTab);
  document.getElementById('refresh-rates').addEventListener('click', loadRates);
  document.getElementById('payment-status-filter').addEventListener('change', loadPayments);
}

// ========== MY ACCOUNT (for account holders) ==========
async function loadMyAccount() {
  if (!currentUser || currentUser.type === 'admin') return;
  
  const cardDiv = document.getElementById('my-account-card');
  const transDiv = document.getElementById('my-transactions');
  
  try {
    // Refresh account data
    const data = await api.accounts.list();
    const accounts = data.data || data.accounts || data;
    const account = accounts.find(a => a.id === currentUser.account.id);
    
    if (account) {
      currentUser.account = account;
      sessionStorage.setItem('currentUser', JSON.stringify(currentUser));
    }
    
    const acc = currentUser.account;
    
    cardDiv.innerHTML = `
      <div class="account-header">
        <div class="account-name">${acc.holderName}</div>
        <div class="account-status">✓ ${acc.status || 'ACTIVE'}</div>
      </div>
      <div class="account-balance">
        <div class="balance-label">Available Balance</div>
        <div class="balance-value">${formatCurrency(acc.balance, acc.currency)}</div>
      </div>
      <div class="account-details">
        <div class="detail">
          <span class="detail-label">Account Number</span>
          <span class="detail-value">${acc.accountNumber}</span>
        </div>
        <div class="detail">
          <span class="detail-label">Bank Code</span>
          <span class="detail-value">${acc.bankCode}</span>
        </div>
        <div class="detail">
          <span class="detail-label">Currency</span>
          <span class="detail-value">${acc.currency}</span>
        </div>
        <div class="detail">
          <span class="detail-label">Country</span>
          <span class="detail-value">${acc.country}</span>
        </div>
      </div>
    `;
    
    // Load transactions for this account
    loadMyTransactions(acc.id, transDiv);
  } catch (error) {
    cardDiv.innerHTML = `<div class="result error">${error.message}</div>`;
  }
}

async function loadMyTransactions(accountId, container) {
  try {
    const data = await api.payments.list();
    const payments = data.payments || [];
    
    // Filter payments where this account is sender or receiver
    const myPayments = payments.filter(p => 
      p.sender?.accountId === accountId || p.receiver?.accountId === accountId
    );
    
    if (myPayments.length === 0) {
      container.innerHTML = '<div class="empty">No transactions yet</div>';
      return;
    }
    
    container.innerHTML = myPayments.map(p => {
      const isSender = p.sender?.accountId === accountId;
      return `
        <div class="card" data-payment-id="${p.paymentId}">
          <div class="card-header">
            <h3>${isSender ? '📤 Sent' : '📥 Received'}</h3>
            <span class="status status-${p.status}">${p.status}</span>
          </div>
          <div class="card-body">
            <div class="card-field">
              <label>${isSender ? 'To' : 'From'}</label>
              <span>${isSender ? p.receiver?.name : p.sender?.name}</span>
            </div>
            <div class="card-field">
              <label>Amount</label>
              <span style="color: ${isSender ? '#e53e3e' : '#38a169'}">
                ${isSender ? '-' : '+'}${formatCurrency(isSender ? p.amount : p.targetAmount, isSender ? p.currency : p.targetCurrency)}
              </span>
            </div>
            <div class="card-field">
              <label>Date</label>
              <span>${formatDate(p.createdAt)}</span>
            </div>
          </div>
        </div>
      `;
    }).join('');
    
    container.querySelectorAll('.card').forEach(card => {
      card.addEventListener('click', () => showPaymentDetails(card.dataset.paymentId));
    });
  } catch (error) {
    container.innerHTML = `<div class="result error">${error.message}</div>`;
  }
}

// ========== ACCOUNTS ==========
async function loadAccounts() {
  const senderSelect = document.getElementById('sender-account');
  const receiverSelect = document.getElementById('receiver-account');
  
  try {
    const data = await api.accounts.list();
    accountsCache = data.data || data.accounts || data;
    
    const isAdmin = currentUser?.type === 'admin';
    
    // For customers, only show their account as sender
    let senderAccounts = accountsCache;
    if (!isAdmin && currentUser?.account) {
      senderAccounts = accountsCache.filter(a => a.id === currentUser.account.id);
    }
    
    const senderOptions = senderAccounts.map(acc => 
      `<option value="${acc.accountNumber}|${acc.bankCode}" data-currency="${acc.currency}" data-balance="${acc.balance}" data-name="${acc.holderName}" data-id="${acc.id}">${acc.holderName} - ${acc.accountNumber} (${acc.currency})</option>`
    ).join('');
    
    const receiverOptions = accountsCache.map(acc => 
      `<option value="${acc.accountNumber}|${acc.bankCode}" data-currency="${acc.currency}" data-balance="${acc.balance}" data-name="${acc.holderName}" data-id="${acc.id}">${acc.holderName} - ${acc.accountNumber} (${acc.currency})</option>`
    ).join('');
    
    senderSelect.innerHTML = '<option value="">Select sender account...</option>' + senderOptions;
    receiverSelect.innerHTML = '<option value="">Select receiver account...</option>' + receiverOptions;
    
    // For customers, pre-select their account as sender
    if (!isAdmin && currentUser?.account) {
      const value = `${currentUser.account.accountNumber}|${currentUser.account.bankCode}`;
      senderSelect.value = value;
      updateSenderInfo();
    }
    
    senderSelect.addEventListener('change', updateSenderInfo);
    receiverSelect.addEventListener('change', updateReceiverInfo);
  } catch (error) {
    console.error('Failed to load accounts:', error);
  }
}

function updateSenderInfo() {
  const select = document.getElementById('sender-account');
  const balanceDiv = document.getElementById('sender-balance');
  const option = select.selectedOptions[0];
  
  if (option && option.value) {
    balanceDiv.textContent = `Balance: ${formatCurrency(option.dataset.balance, option.dataset.currency)}`;
  } else {
    balanceDiv.textContent = '';
  }
}

function updateReceiverInfo() {
  const select = document.getElementById('receiver-account');
  const infoDiv = document.getElementById('receiver-info');
  const option = select.selectedOptions[0];
  
  if (option && option.value) {
    infoDiv.textContent = `Currency: ${option.dataset.currency}`;
  } else {
    infoDiv.textContent = '';
  }
}

async function loadAccountsTab() {
  const list = document.getElementById('accounts-list');
  const stats = document.getElementById('account-stats');
  
  list.innerHTML = '<div class="loading">Loading accounts</div>';
  
  try {
    const data = await api.accounts.list();
    const accounts = data.data || data.accounts || data;
    accountsCache = accounts;
    
    const totalBalance = accounts.reduce((sum, a) => sum + a.balance, 0);
    const currencies = [...new Set(accounts.map(a => a.currency))];
    
    stats.innerHTML = `
      <div class="stat-card blue">
        <div class="stat-value">${accounts.length}</div>
        <div class="stat-label">Total Accounts</div>
      </div>
      <div class="stat-card green">
        <div class="stat-value">${currencies.length}</div>
        <div class="stat-label">Currencies</div>
      </div>
      <div class="stat-card orange">
        <div class="stat-value">${accounts.filter(a => a.status === 'ACTIVE').length}</div>
        <div class="stat-label">Active</div>
      </div>
    `;
    
    list.innerHTML = accounts.map(acc => `
      <div class="card">
        <div class="card-header">
          <h3>${acc.holderName}</h3>
          <span class="status status-${acc.status || 'ACTIVE'}">${acc.status || 'Active'}</span>
        </div>
        <div class="card-body">
          <div class="card-field"><label>Account Number</label><span>${acc.accountNumber}</span></div>
          <div class="card-field"><label>Bank Code</label><span>${acc.bankCode}</span></div>
          <div class="card-field"><label>Currency</label><span>${acc.currency}</span></div>
          <div class="card-field"><label>Balance</label><span style="font-weight:600;color:#48bb78">${formatCurrency(acc.balance, acc.currency)}</span></div>
          <div class="card-field"><label>Country</label><span>${acc.country}</span></div>
        </div>
      </div>
    `).join('') || '<div class="empty">No accounts found</div>';
  } catch (error) {
    list.innerHTML = `<div class="result error">Failed to load accounts: ${error.message}</div>`;
  }
}

// ========== PAYMENT FORM ==========
function initPaymentForm() {
  const form = document.getElementById('payment-form');
  const calculateBtn = document.getElementById('calculate-btn');
  
  calculateBtn.addEventListener('click', calculatePreview);
  form.addEventListener('submit', submitPayment);
}

async function calculatePreview() {
  const preview = document.getElementById('payment-preview');
  const amount = parseFloat(document.getElementById('amount').value);
  const currency = document.getElementById('currency').value;
  const receiverSelect = document.getElementById('receiver-account');
  const receiverOption = receiverSelect.selectedOptions[0];
  
  if (!amount || !currency || !receiverOption?.value) {
    alert('Please fill in amount, currency, and select accounts');
    return;
  }
  
  const receiverCurrency = receiverOption.dataset.currency;
  
  try {
    let targetAmount = amount;
    let rate = 1;
    
    if (currency !== receiverCurrency) {
      const fxResult = await api.fx.convert({ from: currency, to: receiverCurrency, amount });
      targetAmount = fxResult.data?.convertedAmount || fxResult.convertedAmount;
      rate = fxResult.data?.rate || fxResult.rate;
    }
    
    const feeRates = { USD: 25, EUR: 20, GBP: 15, SGD: 35 };
    const fee = (feeRates[currency] || 25) + (amount * 0.001);
    const totalDebit = amount + fee;
    
    document.getElementById('preview-amount').textContent = formatCurrency(amount, currency);
    document.getElementById('preview-target').textContent = formatCurrency(targetAmount, receiverCurrency);
    document.getElementById('preview-rate').textContent = currency === receiverCurrency ? 'Same currency' : rate.toFixed(6);
    document.getElementById('preview-fee').textContent = formatCurrency(fee, currency);
    document.getElementById('preview-total').textContent = formatCurrency(totalDebit, currency);
    
    preview.classList.remove('hidden');
  } catch (error) {
    alert('Error calculating: ' + error.message);
  }
}

async function submitPayment(e) {
  e.preventDefault();
  
  const result = document.getElementById('payment-result');
  const processingPanel = document.getElementById('processing-panel');
  const submitBtn = document.getElementById('submit-btn');
  
  const senderValue = document.getElementById('sender-account').value;
  const receiverValue = document.getElementById('receiver-account').value;
  
  if (!senderValue || !receiverValue) {
    result.className = 'result error';
    result.textContent = 'Please select both sender and receiver accounts';
    result.classList.remove('hidden');
    return;
  }
  
  if (senderValue === receiverValue) {
    result.className = 'result error';
    result.textContent = 'Sender and receiver cannot be the same account';
    result.classList.remove('hidden');
    return;
  }
  
  const [senderAcc, senderBank] = senderValue.split('|');
  const [receiverAcc, receiverBank] = receiverValue.split('|');
  
  const paymentData = {
    senderAccountNumber: senderAcc,
    senderBankCode: senderBank,
    receiverAccountNumber: receiverAcc,
    receiverBankCode: receiverBank,
    amount: parseFloat(document.getElementById('amount').value),
    currency: document.getElementById('currency').value,
    reference: document.getElementById('reference').value || undefined
  };
  
  result.classList.add('hidden');
  processingPanel.classList.remove('hidden');
  submitBtn.disabled = true;
  resetProcessingSteps();
  
  const steps = [
    { num: 1, msg: 'Validating payment request structure...', delay: 200 },
    { num: 2, msg: 'Looking up sender and receiver accounts...', delay: 300 },
    { num: 3, msg: 'Running validation rules (amount limits, blocked countries)...', delay: 400 },
    { num: 4, msg: 'Performing sanctions screening via WOLF...', delay: 600 },
    { num: 5, msg: 'Converting currency via FX service...', delay: 300 },
    { num: 6, msg: 'Calculating transfer fees...', delay: 200 },
    { num: 7, msg: 'Verifying account with HUB...', delay: 300 },
    { num: 8, msg: 'Checking sender balance...', delay: 200 },
    { num: 9, msg: 'Creating double-entry ledger postings...', delay: 300 },
    { num: 10, msg: 'Debiting sender account...', delay: 200 },
    { num: 11, msg: 'Crediting receiver account...', delay: 200 },
    { num: 12, msg: 'Finalizing payment...', delay: 200 }
  ];
  
  animateProcessingSteps(steps, paymentData, result, processingPanel, submitBtn);
}

async function animateProcessingSteps(steps, paymentData, result, processingPanel, submitBtn) {
  const messageDiv = document.getElementById('processing-message');
  
  for (let i = 0; i < steps.length; i++) {
    const step = steps[i];
    const stepEl = document.querySelector(`.step[data-step="${step.num}"]`);
    
    if (i > 0) {
      const prevEl = document.querySelector(`.step[data-step="${steps[i-1].num}"]`);
      prevEl.classList.remove('active');
      prevEl.classList.add('completed');
    }
    
    stepEl.classList.add('active');
    messageDiv.textContent = step.msg;
    
    await sleep(step.delay);
  }
  
  try {
    const payment = await api.payments.create(paymentData);
    
    document.querySelector('.step[data-step="12"]').classList.remove('active');
    document.querySelector('.step[data-step="12"]').classList.add('completed');
    
    messageDiv.innerHTML = `<strong>✅ Payment completed successfully!</strong>`;
    
    setTimeout(() => {
      processingPanel.classList.add('hidden');
      result.className = 'result success';
      result.innerHTML = `
        <strong>✅ Payment Completed!</strong><br><br>
        <strong>Payment ID:</strong> ${payment.paymentId}<br>
        <strong>Status:</strong> ${payment.status}<br>
        <strong>Sent:</strong> ${formatCurrency(payment.amount, payment.currency)}<br>
        <strong>Received:</strong> ${formatCurrency(payment.targetAmount, payment.targetCurrency)}<br>
        <strong>FX Rate:</strong> ${payment.fxRate || 'N/A'}<br>
        <strong>Fee:</strong> ${formatCurrency(payment.feeAmount, payment.currency)}<br>
        <strong>Total Debited:</strong> ${formatCurrency(payment.totalDebit, payment.currency)}
      `;
      result.classList.remove('hidden');
      
      document.getElementById('payment-form').reset();
      document.getElementById('payment-preview').classList.add('hidden');
      document.getElementById('sender-balance').textContent = '';
      document.getElementById('receiver-info').textContent = '';
      
      loadAccounts();
      if (currentUser?.type === 'customer') {
        loadMyAccount();
      }
    }, 1000);
    
  } catch (error) {
    document.querySelectorAll('.step.active').forEach(s => {
      s.classList.remove('active');
      s.classList.add('failed');
    });
    
    messageDiv.innerHTML = `<strong>❌ Error:</strong> ${error.message}`;
    
    setTimeout(() => {
      processingPanel.classList.add('hidden');
      result.className = 'result error';
      result.textContent = 'Payment failed: ' + error.message;
      result.classList.remove('hidden');
    }, 2000);
  }
  
  submitBtn.disabled = false;
}

function resetProcessingSteps() {
  document.querySelectorAll('.step').forEach(s => {
    s.classList.remove('active', 'completed', 'failed');
  });
  document.getElementById('processing-message').textContent = 'Initializing...';
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// ========== PAYMENTS LIST ==========
async function loadPayments() {
  const list = document.getElementById('payments-list');
  const status = document.getElementById('payment-status-filter').value;
  
  list.innerHTML = '<div class="loading">Loading payments</div>';
  
  try {
    const data = await api.payments.list(status);
    let payments = data.payments || [];
    
    // For customers, filter to only their payments
    if (currentUser?.type === 'customer' && currentUser.account) {
      const accountId = currentUser.account.id;
      payments = payments.filter(p => 
        p.sender?.accountId === accountId || p.receiver?.accountId === accountId
      );
    }
    
    if (payments.length === 0) {
      list.innerHTML = '<div class="empty">No payments found. Create one in the New Payment tab!</div>';
      return;
    }
    
    list.innerHTML = payments.map(p => {
      const isSender = currentUser?.type === 'customer' && p.sender?.accountId === currentUser.account?.id;
      return `
        <div class="card" data-payment-id="${p.paymentId}">
          <div class="card-header">
            <h3>🧾 ${p.paymentId}</h3>
            <span class="status status-${p.status}">${p.status}</span>
          </div>
          <div class="card-body">
            <div class="card-field"><label>From</label><span>${p.sender?.name || 'N/A'}</span></div>
            <div class="card-field"><label>To</label><span>${p.receiver?.name || 'N/A'}</span></div>
            <div class="card-field"><label>Amount Sent</label><span>${formatCurrency(p.amount, p.currency)}</span></div>
            <div class="card-field"><label>Amount Received</label><span>${formatCurrency(p.targetAmount, p.targetCurrency)}</span></div>
            <div class="card-field"><label>Date</label><span>${formatDate(p.createdAt)}</span></div>
          </div>
        </div>
      `;
    }).join('');
    
    list.querySelectorAll('.card').forEach(card => {
      card.addEventListener('click', () => showPaymentDetails(card.dataset.paymentId));
    });
  } catch (error) {
    list.innerHTML = `<div class="result error">${error.message}</div>`;
  }
}

// ========== FX RATES ==========
function initFxConverter() {
  document.getElementById('convert-btn').addEventListener('click', async () => {
    const amount = parseFloat(document.getElementById('convert-amount').value);
    const from = document.getElementById('convert-from').value;
    const to = document.getElementById('convert-to').value;
    const resultDiv = document.getElementById('convert-result');
    
    if (from === to) {
      resultDiv.innerHTML = `<strong>${formatCurrency(amount, from)}</strong> = <strong>${formatCurrency(amount, to)}</strong>`;
      return;
    }
    
    try {
      const result = await api.fx.convert({ from, to, amount });
      const converted = result.data?.convertedAmount || result.convertedAmount;
      const rate = result.data?.rate || result.rate;
      resultDiv.innerHTML = `<strong>${formatCurrency(amount, from)}</strong> = <strong>${formatCurrency(converted, to)}</strong><br><small>Rate: ${rate.toFixed(6)}</small>`;
    } catch (error) {
      resultDiv.innerHTML = `<span style="color:#e53e3e">Error: ${error.message}</span>`;
    }
  });
}

async function loadRates() {
  const list = document.getElementById('rates-list');
  list.innerHTML = '<div class="loading">Loading rates</div>';
  
  try {
    const data = await api.fx.getRates();
    const rates = data.data || data.rates || [];
    
    list.innerHTML = rates.map(r => `
      <div class="rate-card">
        <div class="rate-pair">${r.from || r.baseCurrency} → ${r.to || r.targetCurrency}</div>
        <div class="rate-value">${(r.rate || r.midRate || 0).toFixed(4)}</div>
      </div>
    `).join('') || '<div class="empty">No rates available</div>';
  } catch (error) {
    list.innerHTML = `<div class="result error">${error.message}</div>`;
  }
}

// ========== ADMIN ==========
function initAdmin() {
  const form = document.getElementById('create-account-form');
  form.addEventListener('submit', createAccount);
  
  document.getElementById('check-status-btn').addEventListener('click', checkAllServices);
  document.getElementById('refresh-audit').addEventListener('click', loadAuditLog);
}

async function loadAdmin() {
  checkAllServices();
  loadAuditLog();
}

async function createAccount(e) {
  e.preventDefault();
  const result = document.getElementById('create-account-result');
  
  const accountData = {
    holderName: document.getElementById('new-holder-name').value,
    accountNumber: document.getElementById('new-account-number').value,
    bankCode: document.getElementById('new-bank-code').value.toUpperCase(),
    currency: document.getElementById('new-currency').value,
    country: document.getElementById('new-country').value.toUpperCase(),
    balance: parseFloat(document.getElementById('new-balance').value) || 0
  };
  
  try {
    const account = await api.accounts.create(accountData);
    const created = account.data || account;
    
    result.className = 'result success';
    result.innerHTML = `
      <strong>✅ Account created successfully!</strong><br>
      <strong>Account ID:</strong> ${created.id}<br>
      <strong>Holder:</strong> ${created.holderName}<br>
      <strong>Account:</strong> ${created.accountNumber}
    `;
    result.classList.remove('hidden');
    
    document.getElementById('create-account-form').reset();
    loadAccounts();
  } catch (error) {
    result.className = 'result error';
    result.textContent = 'Failed to create account: ' + error.message;
    result.classList.remove('hidden');
  }
}

async function checkAllServices() {
  const services = ['gateway', 'account', 'payment', 'validation', 'ledger', 'fx', 'audit'];
  
  for (const service of services) {
    const indicator = document.querySelector(`.status-item[data-service="${service}"] .status-indicator`);
    indicator.textContent = 'Checking...';
    indicator.className = 'status-indicator';
    
    try {
      const healthy = await api.health[service]();
      indicator.textContent = healthy ? '✓ Online' : '✗ Offline';
      indicator.className = `status-indicator ${healthy ? 'online' : 'offline'}`;
    } catch {
      indicator.textContent = '✗ Offline';
      indicator.className = 'status-indicator offline';
    }
  }
}

async function loadAuditLog() {
  const list = document.getElementById('audit-list');
  list.innerHTML = '<div class="loading">Loading audit log</div>';
  
  try {
    const data = await api.audit.list();
    const events = data.data || data.events || [];
    
    if (events.length === 0) {
      list.innerHTML = '<div class="empty">No audit events yet</div>';
      return;
    }
    
    list.innerHTML = events.slice(0, 20).map(e => `
      <div class="card" style="cursor:default">
        <div class="card-header">
          <h3>${e.eventType}</h3>
          <span class="status status-COMPLETED">${e.entityType}</span>
        </div>
        <div class="card-body">
          <div class="card-field"><label>Event ID</label><span>${e.eventId}</span></div>
          <div class="card-field"><label>Entity</label><span>${e.entityId}</span></div>
          <div class="card-field"><label>Actor</label><span>${e.actor || 'SYSTEM'}</span></div>
          <div class="card-field"><label>Time</label><span>${formatDate(e.createdAt)}</span></div>
        </div>
      </div>
    `).join('');
  } catch (error) {
    list.innerHTML = `<div class="result error">${error.message}</div>`;
  }
}

// ========== MODAL ==========
function initModal() {
  const modal = document.getElementById('payment-modal');
  modal.querySelector('.close').addEventListener('click', () => modal.classList.add('hidden'));
  modal.addEventListener('click', (e) => {
    if (e.target === modal) modal.classList.add('hidden');
  });
}

async function showPaymentDetails(paymentId) {
  const modal = document.getElementById('payment-modal');
  const body = document.getElementById('modal-body');
  
  body.innerHTML = '<div class="loading">Loading details</div>';
  modal.classList.remove('hidden');
  
  try {
    const details = await api.payments.getDetails(paymentId);
    
    body.innerHTML = `
      <div class="detail-section">
        <h4>Payment Information</h4>
        <div class="detail-grid">
          <div class="detail-item"><label>Payment ID</label><span>${details.paymentId}</span></div>
          <div class="detail-item"><label>Status</label><span class="status status-${details.status}">${details.status}</span></div>
          <div class="detail-item"><label>Amount Sent</label><span>${formatCurrency(details.amount, details.currency)}</span></div>
          <div class="detail-item"><label>Amount Received</label><span>${formatCurrency(details.targetAmount, details.targetCurrency)}</span></div>
          <div class="detail-item"><label>FX Rate</label><span>${details.fxRate || 'N/A'}</span></div>
          <div class="detail-item"><label>Fee</label><span>${formatCurrency(details.feeAmount, details.currency)}</span></div>
          <div class="detail-item"><label>Total Debited</label><span>${formatCurrency(details.totalDebit, details.currency)}</span></div>
          <div class="detail-item"><label>Reference</label><span>${details.reference || 'N/A'}</span></div>
        </div>
      </div>
      
      <div class="detail-section">
        <h4>Sender</h4>
        <div class="detail-grid">
          <div class="detail-item"><label>Name</label><span>${details.sender?.name || 'N/A'}</span></div>
          <div class="detail-item"><label>Account</label><span>${details.sender?.accountNumber || 'N/A'}</span></div>
          <div class="detail-item"><label>Bank</label><span>${details.sender?.bankCode || 'N/A'}</span></div>
          <div class="detail-item"><label>Country</label><span>${details.sender?.country || 'N/A'}</span></div>
        </div>
      </div>
      
      <div class="detail-section">
        <h4>Receiver</h4>
        <div class="detail-grid">
          <div class="detail-item"><label>Name</label><span>${details.receiver?.name || 'N/A'}</span></div>
          <div class="detail-item"><label>Account</label><span>${details.receiver?.accountNumber || 'N/A'}</span></div>
          <div class="detail-item"><label>Bank</label><span>${details.receiver?.bankCode || 'N/A'}</span></div>
          <div class="detail-item"><label>Country</label><span>${details.receiver?.country || 'N/A'}</span></div>
        </div>
      </div>
      
      ${details.failureReason ? `
      <div class="detail-section">
        <h4>Failure Reason</h4>
        <div class="result error">${details.failureReason}</div>
      </div>` : ''}
      
      ${details.statusHistory && details.statusHistory.length ? `
      <div class="detail-section">
        <h4>Status History</h4>
        ${details.statusHistory.map(s => `
          <div style="padding: 10px 0; border-bottom: 1px solid #e2e8f0;">
            <span class="status status-${s.status}">${s.status}</span>
            <span style="margin-left: 12px; color: #666;">${formatDate(s.timestamp || s.created_at)}</span>
            ${s.message ? `<div style="color: #888; font-size: 0.9rem; margin-top: 4px;">${s.message}</div>` : ''}
          </div>
        `).join('')}
      </div>` : ''}
    `;
  } catch (error) {
    body.innerHTML = `<div class="result error">${error.message}</div>`;
  }
}

// ========== UTILITIES ==========
function formatCurrency(amount, currency) {
  if (amount === null || amount === undefined) return 'N/A';
  try {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: currency || 'USD' }).format(amount);
  } catch {
    return `${amount} ${currency}`;
  }
}

function formatDate(dateStr) {
  if (!dateStr) return 'N/A';
  return new Date(dateStr).toLocaleString();
}
