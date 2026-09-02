const express = require('express');
const router = express.Router();
const accountService = require('../services/accountService');

// GET /accounts - List all accounts
router.get('/', (req, res, next) => {
  try {
    const accounts = accountService.getAllAccounts();
    res.json({
      success: true,
      data: accounts,
      count: accounts.length
    });
  } catch (error) {
    next(error);
  }
});

// GET /accounts/:id - Get account by ID
router.get('/:id', (req, res, next) => {
  try {
    const account = accountService.getAccountById(req.params.id);
    res.json({
      success: true,
      data: account
    });
  } catch (error) {
    next(error);
  }
});

// GET /accounts/:id/balance - Get account balance
router.get('/:id/balance', (req, res, next) => {
  try {
    const balanceInfo = accountService.getBalance(req.params.id);
    res.json({
      success: true,
      data: {
        accountId: req.params.id,
        balance: balanceInfo.balance,
        currency: balanceInfo.currency
      }
    });
  } catch (error) {
    next(error);
  }
});

// POST /accounts - Create new account
router.post('/', (req, res, next) => {
  try {
    const account = accountService.createAccount(req.body);
    res.status(201).json({
      success: true,
      data: account,
      message: 'Account created successfully'
    });
  } catch (error) {
    next(error);
  }
});

// POST /accounts/lookup - Lookup account by number and bank code
router.post('/lookup', (req, res, next) => {
  try {
    const { accountNumber, bankCode } = req.body;
    
    if (!accountNumber || !bankCode) {
      const error = new Error('accountNumber and bankCode are required');
      error.code = 'VALIDATION_ERROR';
      error.status = 400;
      throw error;
    }

    const account = accountService.lookupAccount(accountNumber, bankCode);
    res.json({
      success: true,
      data: account
    });
  } catch (error) {
    next(error);
  }
});

// PUT /accounts/:id/balance - Update account balance
router.put('/:id/balance', (req, res, next) => {
  try {
    const { balance } = req.body;
    
    if (balance === undefined) {
      const error = new Error('balance is required');
      error.code = 'VALIDATION_ERROR';
      error.status = 400;
      throw error;
    }

    const account = accountService.updateBalance(req.params.id, balance);
    res.json({
      success: true,
      data: account,
      message: 'Balance updated successfully'
    });
  } catch (error) {
    next(error);
  }
});

// POST /accounts/:id/debit - Debit account
router.post('/:id/debit', (req, res, next) => {
  try {
    const { amount } = req.body;
    
    if (!amount || amount <= 0) {
      const error = new Error('Valid amount is required');
      error.code = 'VALIDATION_ERROR';
      error.status = 400;
      throw error;
    }

    const account = accountService.debitAccount(req.params.id, amount);
    res.json({
      success: true,
      data: account,
      message: `Debited ${amount} from account`
    });
  } catch (error) {
    next(error);
  }
});

// POST /accounts/:id/credit - Credit account
router.post('/:id/credit', (req, res, next) => {
  try {
    const { amount } = req.body;
    
    if (!amount || amount <= 0) {
      const error = new Error('Valid amount is required');
      error.code = 'VALIDATION_ERROR';
      error.status = 400;
      throw error;
    }

    const account = accountService.creditAccount(req.params.id, amount);
    res.json({
      success: true,
      data: account,
      message: `Credited ${amount} to account`
    });
  } catch (error) {
    next(error);
  }
});

// POST /accounts/:id/freeze - Freeze account
router.post('/:id/freeze', (req, res, next) => {
  try {
    const account = accountService.freezeAccount(req.params.id);
    res.json({
      success: true,
      data: account,
      message: 'Account frozen'
    });
  } catch (error) {
    next(error);
  }
});

// POST /accounts/:id/activate - Activate account
router.post('/:id/activate', (req, res, next) => {
  try {
    const account = accountService.activateAccount(req.params.id);
    res.json({
      success: true,
      data: account,
      message: 'Account activated'
    });
  } catch (error) {
    next(error);
  }
});

module.exports = router;
