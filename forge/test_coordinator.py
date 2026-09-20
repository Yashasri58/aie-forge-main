"""
Test script for Coordinator Agent.
Run: python test_coordinator.py
"""

import asyncio
import sys
import os

# Load environment variables from .env
from dotenv import load_dotenv
load_dotenv()

# Verify API key is set
api_key = os.environ.get("GOOGLE_API_KEY")
if not api_key:
    print("ERROR: GOOGLE_API_KEY environment variable not set")
    print("Please set it in .env file or as environment variable")
    sys.exit(1)
print(f"API Key found: {api_key[:10]}...")

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from modules.codegen.coordinator_agent import CoordinatorAgent
from modules.codegen.schemas import Plan, Task, TaskAction, Contract, ContractType, ExecutionPhase

# Path to services
SERVICES_PATH = os.path.join(os.path.dirname(__file__), '..', 'services')


def create_test_plan() -> Plan:
    """Create a simple test plan similar to what Design Agent produces."""
    plan = Plan.create("Add retry logic to validatePayment and getRules")
    
    # Add a contract
    plan.contracts["fetchWithRetry"] = Contract(
        name="fetchWithRetry",
        type=ContractType.FUNCTION,
        defined_in="payment-processor/src/utils/retry.js",
        is_new=True,
        signature="async function fetchWithRetry(url, options, maxRetries = 3)",
        usage_example="const data = await fetchWithRetry('/api/validate', { method: 'POST' })"
    )
    
    # Add tasks
    plan.tasks["task-1-create-retry"] = Task(
        id="task-1-create-retry",
        phase=0,
        file="payment-processor/src/utils/retry.js",
        service="payment-processor",
        language="javascript",
        action=TaskAction.CREATE,
        description="Create retry utility",
        changes=[],  # Simplified for test
        defines_contracts=["fetchWithRetry"],
    )
    
    plan.tasks["task-2-modify-client"] = Task(
        id="task-2-modify-client",
        phase=1,
        file="payment-processor/src/clients/validationClient.js",
        service="payment-processor",
        language="javascript",
        action=TaskAction.MODIFY,
        description="Update validation client to use retry",
        changes=[],  # Simplified for test
        uses_contracts=["fetchWithRetry"],
        depends_on=["task-1-create-retry"],
    )
    
    # Add execution phases
    plan.execution = [
        ExecutionPhase(
            phase=0,
            description="Create utility",
            tasks=["task-1-create-retry"],
            parallel=False,
        ),
        ExecutionPhase(
            phase=1,
            description="Update client",
            tasks=["task-2-modify-client"],
            parallel=False,
        ),
    ]
    
    return plan


async def test_coordinator():
    """Test the Coordinator Agent validation."""
    print("=" * 60)
    print("COORDINATOR AGENT TEST")
    print("=" * 60)
    
    # Create coordinator
    print(f"\n1. Creating CoordinatorAgent with services path: {SERVICES_PATH}")
    coordinator = CoordinatorAgent(SERVICES_PATH)
    
    # Create test plan
    print("\n2. Creating test plan...")
    plan = create_test_plan()
    print(f"   - Tasks: {list(plan.tasks.keys())}")
    print(f"   - Contracts: {list(plan.contracts.keys())}")
    print(f"   - Phases: {len(plan.execution)}")
    
    # Validate
    print("\n3. Calling coordinator.validate(plan)...")
    print("-" * 40)
    
    try:
        result = await coordinator.validate(plan)
        
        print("-" * 40)
        print("\n4. RESULT:")
        print(f"   Valid: {result.get('valid')}")
        print(f"   Errors: {len(result.get('errors', []))}")
        print(f"   Warnings: {len(result.get('warnings', []))}")
        print(f"   Summary: {result.get('summary', 'N/A')[:200]}")
        
        if result.get('errors'):
            print("\n   ERRORS:")
            for err in result['errors']:
                print(f"     - [{err.get('task')}] {err.get('issue')}")
        
        if result.get('warnings'):
            print("\n   WARNINGS:")
            for warn in result['warnings']:
                print(f"     - [{warn.get('task')}] {warn.get('issue')}")
                
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_coordinator())
