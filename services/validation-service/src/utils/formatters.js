/**
 * Formatters for validation service
 * Called from repository and services
 */

/**
 * Format rule database row to API response
 */
function formatRuleResponse(row) {
  if (!row) return null;

  let parameters = {};
  try {
    parameters = JSON.parse(row.parameters || '{}');
  } catch (e) {
    parameters = {};
  }

  return {
    id: row.id,
    ruleCode: row.rule_code,
    ruleName: row.rule_name,
    description: row.description,
    ruleType: row.rule_type,
    parameters: parameters,
    isActive: row.is_active === 1,
    createdAt: row.created_at
  };
}

/**
 * Format currency amount to 2 decimal places
 */
function formatCurrency(amount) {
  if (amount === undefined || amount === null) {
    return '0.00';
  }
  return (Math.round(amount * 100) / 100).toFixed(2);
}

/**
 * Format validation result for logging
 */
function formatValidationResult(result) {
  return {
    valid: result.valid,
    checkedCount: result.rulesChecked.length,
    passedCount: result.rulesPassed.length,
    failedCount: result.rulesFailed.length,
    warningCount: result.warnings.length
  };
}

module.exports = {
  formatRuleResponse,
  formatCurrency,
  formatValidationResult
};
