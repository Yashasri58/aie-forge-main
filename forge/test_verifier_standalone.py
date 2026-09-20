"""
Standalone test for the Verifier Agent.

Run: python test_verifier_standalone.py
"""

import asyncio
import sys
from pathlib import Path

# Add paths
sys.path.insert(0, str(Path(__file__).parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from modules.codegen.verifier_agent import VerifierAgent
from modules.codegen.schemas import (
    Plan,
    PlanAnalysis,
    PlanDesign,
    Contract,
    ContractType,
    ExecutionPhase,
    Task,
    TaskChange,
    TaskAction,
    ChangeLocation,
    LocationType,
    ChangeType,
    AgentOutput,
)


def create_test_plan() -> Plan:
    """Create a simple test plan."""
    plan = Plan.create("Add logAuditEvent function to audit-service")
    
    plan.analysis = PlanAnalysis(
        summary="Add a new logging utility function",
        reasoning="Centralize audit logging for consistency",
        existing_patterns=[],
        risks=[],
        assumptions=[],
    )
    
    plan.design = PlanDesign(
        decisions=[],
        conventions=None,
    )
    
    plan.contracts = {
        "logAuditEvent": Contract(
            name="logAuditEvent",
            type=ContractType.FUNCTION,
            defined_in="audit-service/src/utils/logger.js",
            is_new=True,
            signature="function logAuditEvent(eventName, details)",
            implementation="function logAuditEvent(eventName, details) { console.log(`[${new Date().toISOString()}] ${eventName}`, details); }",
            used_by=["task-2"],
        ),
    }
    
    plan.tasks = {
        "task-1": Task(
            id="task-1",
            phase=0,
            file="audit-service/src/utils/logger.js",
            service="audit-service",
            language="javascript",
            action=TaskAction.CREATE,
            description="Create logger.js with logAuditEvent function",
            changes=[
                TaskChange(
                    location=ChangeLocation(type=LocationType.FILE_START, target="logger.js"),
                    change_type=ChangeType.ADD,
                    description="Create logAuditEvent function",
                )
            ],
            depends_on=[],
            uses_contracts=[],
            defines_contracts=["logAuditEvent"],
        ),
        "task-2": Task(
            id="task-2",
            phase=1,
            file="audit-service/src/services/auditService.js",
            service="audit-service",
            language="javascript",
            action=TaskAction.MODIFY,
            description="Import and use logAuditEvent",
            changes=[
                TaskChange(
                    location=ChangeLocation(type=LocationType.IMPORT_SECTION, target="auditService.js"),
                    change_type=ChangeType.ADD,
                    description="Add import for logAuditEvent",
                )
            ],
            depends_on=["task-1"],
            uses_contracts=["logAuditEvent"],
            defines_contracts=[],
        ),
    }
    
    plan.execution = [
        ExecutionPhase(phase=0, description="Create logger", tasks=["task-1"]),
        ExecutionPhase(phase=1, description="Update service", tasks=["task-2"]),
    ]
    
    return plan


def create_test_diffs() -> list[AgentOutput]:
    """Create test diffs that are large enough to trigger LLM verification."""
    # Make the diffs larger to exceed the 2000 char threshold for fast path
    return [
        AgentOutput(
            task_id="task-1",
            file="audit-service/src/utils/logger.js",
            status="success",
            diff="""--- /dev/null
+++ b/audit-service/src/utils/logger.js
@@ -0,0 +1,45 @@
+/**
+ * Logger utility for audit events.
+ * 
+ * This module provides centralized logging functionality for audit events
+ * across the audit-service. All audit events should be logged through
+ * this utility to ensure consistent formatting and timestamp handling.
+ * 
+ * @module logger
+ * @author Forge Code Generator
+ * @version 1.0.0
+ */
+
+'use strict';
+
+/**
+ * Logs an audit event to the console with a timestamp.
+ * 
+ * @param {string} eventName - The name of the event to log.
+ * @param {object} details - The details of the event.
+ * @returns {void}
+ * 
+ * @example
+ * logAuditEvent('USER_LOGIN', { userId: '123', ip: '192.168.1.1' });
+ * // Output: [2024-01-15T10:30:00.000Z] AUDIT: USER_LOGIN { userId: '123', ip: '192.168.1.1' }
+ */
+function logAuditEvent(eventName, details) {
+  if (!eventName || typeof eventName !== 'string') {
+    throw new Error('eventName must be a non-empty string');
+  }
+  
+  const timestamp = new Date().toISOString();
+  const formattedDetails = details ? JSON.stringify(details) : '';
+  
+  console.log(`[${timestamp}] AUDIT: ${eventName}`, formattedDetails);
+  
+  // Also log to structured format for log aggregation
+  console.log(JSON.stringify({
+    timestamp,
+    level: 'AUDIT',
+    event: eventName,
+    details: details || {}
+  }));
+}
+
+module.exports = { logAuditEvent };
""",
        ),
        AgentOutput(
            task_id="task-2",
            file="audit-service/src/services/auditService.js",
            status="success",
            diff="""--- a/audit-service/src/services/auditService.js
+++ b/audit-service/src/services/auditService.js
@@ -1,8 +1,10 @@
 const auditRepository = require('../repositories/auditRepository');
 const { generateEventId, generateIntegrityHash } = require('../utils/idGenerator');
 const { validateEventData } = require('../utils/validators');
+const { logAuditEvent } = require('../utils/logger');
 
 /**
  * AuditService handles all audit logging operations.
+ * Now uses centralized logAuditEvent for consistent logging.
  */
 class AuditService {
@@ -15,6 +17,7 @@ class AuditService {
    */
   async logEvent(eventData) {
     validateEventData(eventData);
+    logAuditEvent('AUDIT_EVENT', eventData);
     
     const eventId = generateEventId();
     const integrityHash = generateIntegrityHash(eventData);
@@ -35,6 +38,7 @@ class AuditService {
    * @returns {Promise<object>} The logged account change record
    */
   async logAccountChange(accountId, changeType, oldValue, newValue) {
+    logAuditEvent('ACCOUNT_CHANGE', { accountId, changeType, oldValue, newValue });
     return this.logEvent({
       type: 'ACCOUNT_CHANGE',
       accountId,
@@ -52,6 +56,7 @@ class AuditService {
    * @returns {Promise<object>} The logged payment status record
    */
   async logPaymentStatusChange(paymentId, oldStatus, newStatus, reason) {
+    logAuditEvent('PAYMENT_STATUS_CHANGE', { paymentId, oldStatus, newStatus, reason });
     return this.logEvent({
       type: 'PAYMENT_STATUS_CHANGE',
       paymentId,
""",
        ),
    ]


async def test_verifier():
    """Test the verifier agent."""
    print("=" * 60)
    print("VERIFIER AGENT STANDALONE TEST")
    print("=" * 60)
    
    # Path to services
    services_path = Path(__file__).parent / ".." / "services"
    if not services_path.exists():
        services_path = Path(__file__).parent / "services"
    
    print(f"\nServices path: {services_path}")
    print(f"Services exists: {services_path.exists()}")
    
    # Create verifier
    print("\n1. Creating VerifierAgent...")
    verifier = VerifierAgent(str(services_path))
    print("   OK - VerifierAgent created")
    
    # Create test data
    print("\n2. Creating test plan and diffs...")
    plan = create_test_plan()
    diffs = create_test_diffs()
    print(f"   OK - Plan: {len(plan.tasks)} tasks, {len(plan.contracts)} contracts")
    print(f"   OK - Diffs: {len(diffs)} diffs")
    for d in diffs:
        print(f"      - {d.task_id}: {d.file} ({len(d.diff)} chars)")
    
    # Run verification
    print("\n3. Running verification...")
    print("-" * 40)
    
    result = await verifier.verify(plan, diffs)
    
    print("-" * 40)
    print("\n4. Results:")
    print(f"   Passed: {result.passed}")
    print(f"   Issues: {len(result.issues)}")
    
    if result.issues:
        print("\n   Issues found:")
        for issue in result.issues:
            print(f"      [{issue.severity}] {issue.file}: {issue.issue}")
            if issue.suggestion:
                print(f"         -> {issue.suggestion}")
    
    if result.llm_results:
        print(f"\n   LLM Summary: {result.llm_results.get('summary', 'N/A')}")
    
    print("\n" + "=" * 60)
    print(f"TEST {'PASSED' if result.passed else 'COMPLETED WITH ISSUES'}")
    print("=" * 60)
    
    return result


if __name__ == "__main__":
    result = asyncio.run(test_verifier())
