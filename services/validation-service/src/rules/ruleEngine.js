/**
 * Rule Engine - executes all validation rules against a payment
 */

const amountLimitRule = require('./amountLimitRule');
const countryRule = require('./countryRule');
const duplicateRule = require('./duplicateRule');
const currencyRule = require('./currencyRule');

class RuleEngine {
  constructor() {
    // Register all rule handlers
    this.ruleHandlers = {
      'AMOUNT_LIMIT_SINGLE': amountLimitRule.checkSingleLimit,
      'AMOUNT_LIMIT_DAILY': amountLimitRule.checkDailyLimit,
      'BLOCKED_COUNTRIES': countryRule.checkBlockedCountries,
      'HIGH_RISK_COUNTRIES': countryRule.checkHighRiskCountries,
      'DUPLICATE_CHECK': duplicateRule.checkDuplicate,
      'CURRENCY_PAIRS': currencyRule.checkCurrencyPair
    };
  }

  /**
   * Execute all active rules against a payment
   */
  async executeRules(payment, rules) {
    const results = {
      valid: true,
      rulesChecked: [],
      rulesPassed: [],
      rulesFailed: [],
      warnings: []
    };

    for (const rule of rules) {
      if (!rule.is_active) continue;

      const ruleCode = rule.rule_code;
      results.rulesChecked.push(ruleCode);

      const handler = this.ruleHandlers[ruleCode];
      if (!handler) {
        console.warn(`No handler for rule: ${ruleCode}`);
        continue;
      }

      try {
        const params = JSON.parse(rule.parameters || '{}');
        const ruleResult = await handler(payment, params);

        if (ruleResult.passed) {
          results.rulesPassed.push(ruleCode);
          if (ruleResult.warning) {
            results.warnings.push({
              code: ruleCode,
              message: ruleResult.warning
            });
          }
        } else {
          results.rulesFailed.push({
            code: ruleCode,
            message: ruleResult.message
          });
          results.valid = false;
        }
      } catch (error) {
        console.error(`Error executing rule ${ruleCode}:`, error);
        results.rulesFailed.push({
          code: ruleCode,
          message: `Rule execution error: ${error.message}`
        });
        results.valid = false;
      }
    }

    return results;
  }
}

module.exports = new RuleEngine();
