const accountRepository = require('../repositories/accountRepository');
const { validateAccountData, validateBalanceUpdate } = require('../utils/validators');

class AccountService {

  getAllAccounts() {
    return accountRepository.findAll();
  }

  getAccountById(id) {
    const account = accountRepository.findById(id);
    if (!account) {
      const error = new Error(`Account not found: ${id}`);
      error.code = 'ACCOUNT_NOT_FOUND';
      error.status = 404;
      throw error;
    }
    return account;
  }

  getAccountByNumber(accountNumber) {
    const account = accountRepository.findByAccountNumber(accountNumber);
    if (!account) {
      const error = new Error(`Account not found: ${accountNumber}`);
      error.code = 'ACCOUNT_NOT_FOUND';
      error.status = 404;
      throw error;
    }
    return account;
  }

  lookupAccount(accountNumber, bankCode) {
    const account = accountRepository.findByAccountNumberAndBankCode(accountNumber, bankCode);
    if (!account) {
      const error = new Error(`Account not found: ${accountNumber} at ${bankCode}`);
      error.code = 'ACCOUNT_NOT_FOUND';
      error.status = 404;
      throw error;
    }
    return account;
  }

  createAccount(accountData) {
    // Validate input
    const validation = validateAccountData(accountData);
    if (!validation.valid) {
      const error = new Error(validation.message);
      error.code = 'VALIDATION_ERROR';
      error.status = 400;
      throw error;
    }

    // Check for duplicate account number
    const existing = accountRepository.findByAccountNumber(accountData.accountNumber);
    if (existing) {
      const error = new Error(`Account already exists: ${accountData.accountNumber}`);
      error.code = 'ACCOUNT_EXISTS';
      error.status = 409;
      throw error;
    }

    return accountRepository.create(accountData);
  }

  getBalance(id) {
    const balanceInfo = accountRepository.getBalance(id);
    if (!balanceInfo) {
      const error = new Error(`Account not found: ${id}`);
      error.code = 'ACCOUNT_NOT_FOUND';
      error.status = 404;
      throw error;
    }
    return balanceInfo;
  }

  updateBalance(id, newBalance) {
    // Validate balance
    const validation = validateBalanceUpdate(newBalance);
    if (!validation.valid) {
      const error = new Error(validation.message);
      error.code = 'VALIDATION_ERROR';
      error.status = 400;
      throw error;
    }

    // Check account exists
    const existing = accountRepository.findById(id);
    if (!existing) {
      const error = new Error(`Account not found: ${id}`);
      error.code = 'ACCOUNT_NOT_FOUND';
      error.status = 404;
      throw error;
    }

    // Check account is active
    if (existing.status !== 'ACTIVE') {
      const error = new Error(`Account is not active: ${id}`);
      error.code = 'ACCOUNT_INACTIVE';
      error.status = 400;
      throw error;
    }

    return accountRepository.updateBalance(id, newBalance);
  }

  debitAccount(id, amount) {
    const account = this.getAccountById(id);
    
    if (account.status !== 'ACTIVE') {
      const error = new Error(`Account is not active: ${id}`);
      error.code = 'ACCOUNT_INACTIVE';
      error.status = 400;
      throw error;
    }

    if (account.balance < amount) {
      const error = new Error(`Insufficient balance. Available: ${account.balance}, Required: ${amount}`);
      error.code = 'INSUFFICIENT_BALANCE';
      error.status = 400;
      throw error;
    }

    const newBalance = Math.round((account.balance - amount) * 100) / 100;
    return accountRepository.updateBalance(id, newBalance);
  }

  creditAccount(id, amount) {
    const account = this.getAccountById(id);
    
    if (account.status !== 'ACTIVE') {
      const error = new Error(`Account is not active: ${id}`);
      error.code = 'ACCOUNT_INACTIVE';
      error.status = 400;
      throw error;
    }

    const newBalance = Math.round((account.balance + amount) * 100) / 100;
    return accountRepository.updateBalance(id, newBalance);
  }

  freezeAccount(id) {
    const account = this.getAccountById(id);
    return accountRepository.updateStatus(id, 'FROZEN');
  }

  activateAccount(id) {
    const account = this.getAccountById(id);
    return accountRepository.updateStatus(id, 'ACTIVE');
  }
}

module.exports = new AccountService();
