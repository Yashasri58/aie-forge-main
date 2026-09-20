# vallm + Harness Integration

## Status: ✅ INTEGRATED

vallm is now integrated into our harness pipeline. The gate uses:

- **vallm/tree-sitter**: Syntax validation (robust, 165 languages)
- **vallm/lizard**: Complexity metrics (cyclomatic complexity, function length)
- **vallm security**: Base security patterns (eval, innerHTML, etc.)
- **Our SecurityScanner**: Extended patterns (SQL injection for JS, etc.)
- **Our ImportResolver**: Path verification (vallm doesn't do this)
- **Our HallucinationDetector**: Invented methods (vallm doesn't do this)
- **Our ContractChecker**: Plan compliance (vallm doesn't do this)
- **Our NegativeConstraintChecker**: Rules enforcement (vallm doesn't do this)

## Test Results

| Test | vallm | Our Harness | Combined |
|------|-------|-------------|----------|
| Syntax Error | ✅ tree-sitter | ✅ bracket | **vallm used** |
| eval() | ✅ | ✅ | Both detect |
| innerHTML | ✅ | ✅ (fixed) | Both detect |
| SQL Injection | ❌ | ✅ (added) | **Our harness** |
| Complexity | ✅ lizard | ❌ | **vallm used** |
| Hallucination | ❌ | ✅ | **Our harness** |
| Import paths | ❌ | ✅ | **Our harness** |
| Negative constraints | ❌ | ✅ | **Our harness** |

## Pipeline Tiers

```
TIER 1 (fail-fast):
  ├─ syntax:vallm     - tree-sitter parsing (or native fallback)
  └─ import           - our path verification

TIER 2:
  ├─ security:vallm   - vallm patterns (eval, innerHTML, secrets)
  ├─ security:native  - our extended patterns (SQL injection, XSS)
  ├─ complexity:vallm - lizard metrics
  └─ contract         - our plan compliance check

TIER 3:
  ├─ hallucination    - our invented methods detection
  └─ negative_constraint - our rules enforcement
```

## Usage

```python
from modules.codegen.harness import DeterministicGate, GateConfig

config = GateConfig(
    use_vallm=True,           # Enable vallm integration
    vallm_syntax=True,        # Use tree-sitter
    vallm_complexity=True,    # Use lizard
    vallm_security=True,      # Use vallm security patterns
    complexity_threshold=15,  # Max cyclomatic complexity
)

gate = DeterministicGate(services_path, config=config)
result = await gate.run(service_id, diffs, plan)
```

## Files Modified

- `harness/vallm_adapter.py` - New adapter for vallm integration
- `harness/gate.py` - Updated to use vallm when available
- `harness/security_scanner.py` - Added SQL injection + innerHTML patterns
- `harness/__init__.py` - Exports vallm adapter

## Graceful Fallback

If vallm is not installed, the gate automatically falls back to our native checkers:
- Syntax: `node --check` + bracket validation
- Security: Our patterns only
- Complexity: Skipped
