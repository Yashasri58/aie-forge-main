"""
Test script for Verifier Agent.
Tests the agent in isolation without running the full server.
"""

import asyncio
import os
import sys

# Load environment variables BEFORE importing modules that use them
from dotenv import load_dotenv
load_dotenv()

# Verify API key is loaded
api_key = os.environ.get("GOOGLE_API_KEY")
if not api_key:
    print("ERROR: GOOGLE_API_KEY not found in environment!")
    print("Make sure .env file exists with GOOGLE_API_KEY=...")
    sys.exit(1)
print(f"API Key found: {api_key[:12]}...")

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from modules.codegen.verifier_agent import VerifierAgent
from modules.codegen.schemas import (
    Plan,
    Task,
    Contract,
    ContractType,
    ExecutionPhase,
    AgentOutput,
)


async def test_verifier():
    """Test the Verifier Agent."""
    print("=" * 60)
    print("VERIFIER AGENT TEST")
    print("=" * 60)
    
    # Create verifier with services path
    services_path = os.path.join(os.path.dirname(__file__), '..', 'services')
    print(f"\n1. Creating VerifierAgent with services path: {services_path}")
    
    verifier = VerifierAgent(services_path)
    
    # Create a test plan
    print("\n2. Creating test plan and diffs...")
    
    tasks = {
        "task-1": Task(
            id="task-1",
            file="payment-processor/src/utils/retry.js",
            service="payment-processor",
            action="CREATE",
            description="Create retry utility with exponential backoff",
            changes=[],
            phase=1,
            language="javascript",
            uses_contracts=[],
            defines_contracts=["fetchWithRetry"],
        ),
        "task-2": Task(
            id="task-2",
            file="payment-processor/src/clients/validationClient.js",
            service="payment-processor",
            action="MODIFY",
            description="Add retry logic to validation client",
            changes=[],
            phase=2,
            language="javascript",
            uses_contracts=["fetchWithRetry"],
            defines_contracts=[],
            depends_on=["task-1"],
        ),
    }
    
    contracts = {
        "fetchWithRetry": Contract(
            name="fetchWithRetry",
            type=ContractType.FUNCTION,
            signature="async function fetchWithRetry(url, options, maxRetries = 3)",
            defined_in="task-1",
            is_new=True,
            used_by=["task-2"],
        ),
    }
    
    execution = [
        ExecutionPhase(phase=1, description="Create retry utility", tasks=["task-1"]),
        ExecutionPhase(phase=2, description="Update validation client", tasks=["task-2"]),
    ]
    
    plan = Plan(
        id="test-plan-001",
        created_at=1234567890.0,
        change_request="Add retry logic to validation client",
        tasks=tasks,
        contracts=contracts,
        execution=execution,
    )
    
    # Create test diffs
    diffs = [
        AgentOutput(
            task_id="task-1",
            file="payment-processor/src/utils/retry.js",
            status="success",
            diff="""--- /dev/null
+++ b/payment-processor/src/utils/retry.js
@@ -0,0 +1,35 @@
+/**
+ * Retry utility with exponential backoff
+ */
+
+async function fetchWithRetry(url, options, maxRetries = 3) {
+  let lastError;
+  
+  for (let attempt = 0; attempt < maxRetries; attempt++) {
+    try {
+      const response = await fetch(url, options);
+      
+      if (!response.ok) {
+        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
+      }
+      
+      return response;
+    } catch (error) {
+      lastError = error;
+      
+      if (attempt < maxRetries - 1) {
+        const delay = Math.pow(2, attempt) * 1000;
+        await new Promise(resolve => setTimeout(resolve, delay));
+      }
+    }
+  }
+  
+  throw lastError;
+}
+
+module.exports = {
+  fetchWithRetry,
+};
""",
        ),
        AgentOutput(
            task_id="task-2",
            file="payment-processor/src/clients/validationClient.js",
            status="success",
            diff="""--- a/payment-processor/src/clients/validationClient.js
+++ b/payment-processor/src/clients/validationClient.js
@@ -1,5 +1,6 @@
 const axios = require('axios');
 const config = require('../config');
+const { fetchWithRetry } = require('../utils/retry');
 
 class ValidationClient {
   constructor() {
@@ -15,7 +16,12 @@ class ValidationClient {
    */
   async validatePayment(paymentData) {
     try {
-      const response = await axios.post(`${this.baseUrl}/validate`, paymentData);
+      const response = await fetchWithRetry(
+        `${this.baseUrl}/validate`,
+        {
+          method: 'POST',
+          body: JSON.stringify(paymentData),
+        }
+      );
       return response.data;
     } catch (error) {
       console.error('Payment validation failed:', error);
""",
        ),
    ]
    
    print(f"   - Diffs: {len(diffs)}")
    print(f"   - Tasks: {list(tasks.keys())}")
    
    # Call verify
    print("\n3. Calling verifier.verify(plan, diffs)...")
    print("-" * 40)
    
    result = await verifier.verify(plan, diffs)
    
    print("-" * 40)
    
    # Print result
    print("\n4. RESULT:")
    print(f"   Passed: {result.passed}")
    print(f"   Issues: {len(result.issues)}")
    
    if result.issues:
        print("\n   ISSUES:")
        for issue in result.issues:
            print(f"     - [{issue.severity}] {issue.task_id}: {issue.issue[:80]}")
            if issue.fix_instruction:
                print(f"       Fix: {issue.fix_instruction[:60]}...")
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)
    
    return result


if __name__ == "__main__":
    asyncio.run(test_verifier())
