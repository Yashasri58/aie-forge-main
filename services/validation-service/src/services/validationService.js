const ruleRepository = require('../repositories/ruleRepository');
const ruleEngine = require('../rules/ruleEngine');
const { validatePaymentData } = require('../utils/validators');

class ValidationService {

  async getAllRules() {
    return ruleRepository.findAll();
  }

  async getRuleById(id) {
    const rule = ruleRepository.findById(id);
    if (!rule) {
      const error = new Error(`Rule not found: ${id}`);
      error.code = 'RULE_NOT_FOUND';
      error.status = 404;
      throw error;
    }
    return rule;
  }

  async getRuleByCode(code) {
    const rule = ruleRepository.findByCode(code);
    if (!rule) {
      const error = new Error(`Rule not found: ${code}`);
      error.code = 'RULE_NOT_FOUND';
      error.status = 404;
      throw error;
    }
    return rule;
  }

  async validatePayment(paymentData) {
    // Basic validation first
    const basicValidation = validatePaymentData(paymentData);
    if (!basicValidation.valid) {
      return {
        valid: false,
        rulesChecked: ['BASIC_VALIDATION'],
        rulesPassed: [],
        rulesFailed: [{
          code: 'BASIC_VALIDATION',
          message: basicValidation.message
        }],
        warnings: []
      };
    }

    // Get all active rules
    const rules = ruleRepository.findAllActive();

    // Execute rules
    const results = await ruleEngine.executeRules(paymentData, rules);

    // Log validation (optional)
    this.logValidation(paymentData.paymentId, results);

    return results;
  }

  logValidation(paymentId, results) {
    try {
      ruleRepository.logValidation({
        paymentId,
        rulesChecked: JSON.stringify(results.rulesChecked),
        rulesPassed: JSON.stringify(results.rulesPassed),
        rulesFailed: JSON.stringify(results.rulesFailed),
        isValid: results.valid ? 1 : 0
      });
    } catch (error) {
      console.error('Failed to log validation:', error);
    }
  }

  async getActiveRules() {
    return ruleRepository.findAllActive();
  }

  async toggleRule(ruleId, isActive) {
    const rule = await this.getRuleById(ruleId);
    return ruleRepository.updateRuleStatus(ruleId, isActive);
  }
}

module.exports = new ValidationService();
