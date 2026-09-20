"""
Import Resolver
===============

Verifies that all require() and import statements can be resolved.
Detects hallucinated imports - modules/files that don't exist.

Checks:
1. Relative imports (./foo, ../bar) - file must exist
2. Package imports (axios, express) - must be in package.json
3. Node.js builtins (fs, path) - allowed
"""

import re
import os
import json
from typing import List, Set, Optional, Dict
from pathlib import Path

from .models import (
    HarnessViolation,
    ViolationSeverity,
    CheckType,
    FileDiff,
    CheckResult,
)


# Node.js builtin modules
NODE_BUILTINS = {
    'assert', 'async_hooks', 'buffer', 'child_process', 'cluster',
    'console', 'constants', 'crypto', 'dgram', 'dns', 'domain',
    'events', 'fs', 'http', 'http2', 'https', 'inspector', 'module',
    'net', 'os', 'path', 'perf_hooks', 'process', 'punycode',
    'querystring', 'readline', 'repl', 'stream', 'string_decoder',
    'sys', 'timers', 'tls', 'trace_events', 'tty', 'url', 'util',
    'v8', 'vm', 'wasi', 'worker_threads', 'zlib',
    # Node.js prefixed
    'node:fs', 'node:path', 'node:url', 'node:util', 'node:http',
    'node:https', 'node:stream', 'node:crypto', 'node:events',
}


class ImportResolver:
    """
    Validates that imports can be resolved to actual files/packages.
    
    This catches one of the most common LLM hallucinations:
    inventing modules that don't exist.
    """
    
    def __init__(self, services_path: str):
        """
        Args:
            services_path: Path to the services directory
        """
        self.services_path = Path(services_path)
        self._package_cache: Dict[str, Set[str]] = {}
    
    def check(self, service_id: str, diffs: List[FileDiff]) -> CheckResult:
        """
        Validate imports for all modified files.
        
        Args:
            service_id: Service being checked
            diffs: List of file changes to validate
        
        Returns:
            CheckResult with import violations
        """
        violations = []
        
        # Load package.json dependencies for this service
        dependencies = self._get_service_dependencies(service_id)
        
        for diff in diffs:
            if not self._is_javascript_file(diff.file_path):
                continue
            
            file_violations = self._check_file_imports(
                service_id, diff, dependencies, diffs
            )
            violations.extend(file_violations)
        
        return CheckResult(
            check_type=CheckType.IMPORT,
            passed=len([v for v in violations if v.severity == ViolationSeverity.ERROR]) == 0,
            violations=violations,
        )
    
    def _is_javascript_file(self, path: str) -> bool:
        """Check if file is JavaScript/TypeScript."""
        return path.endswith(('.js', '.ts', '.jsx', '.tsx', '.mjs', '.cjs'))
    
    def _get_service_dependencies(self, service_id: str) -> Set[str]:
        """Get installed dependencies from package.json."""
        if service_id in self._package_cache:
            return self._package_cache[service_id]
        
        dependencies = set()
        package_path = self.services_path / service_id / 'package.json'
        
        try:
            if package_path.exists():
                with open(package_path, 'r', encoding='utf-8') as f:
                    pkg = json.load(f)
                
                # Collect all dependency types
                for dep_type in ['dependencies', 'devDependencies', 'peerDependencies']:
                    if dep_type in pkg:
                        dependencies.update(pkg[dep_type].keys())
        except Exception:
            pass
        
        self._package_cache[service_id] = dependencies
        return dependencies
    
    def _check_file_imports(
        self,
        service_id: str,
        diff: FileDiff,
        dependencies: Set[str],
        all_diffs: List[FileDiff]
    ) -> List[HarnessViolation]:
        """Check all imports in a single file."""
        violations = []
        content = diff.modified_content
        
        if not content:
            return violations
        
        # Extract all imports
        imports = self._extract_imports(content)
        
        for import_spec, line_num in imports:
            violation = self._validate_import(
                service_id, diff, import_spec, line_num, dependencies, all_diffs
            )
            if violation:
                violations.append(violation)
        
        return violations
    
    def _extract_imports(self, content: str) -> List[tuple]:
        """
        Extract all import/require statements.
        
        Returns list of (module_path, line_number) tuples.
        """
        imports = []
        lines = content.split('\n')
        
        for line_num, line in enumerate(lines, 1):
            # CommonJS require
            # const x = require('module')
            # require('module')
            for match in re.finditer(r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", line):
                imports.append((match.group(1), line_num))
            
            # ES6 import
            # import x from 'module'
            # import { x } from 'module'
            # import 'module'
            for match in re.finditer(r"import\s+(?:.*\s+from\s+)?['\"]([^'\"]+)['\"]", line):
                imports.append((match.group(1), line_num))
            
            # Dynamic import
            # import('module')
            for match in re.finditer(r"import\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", line):
                imports.append((match.group(1), line_num))
        
        return imports
    
    def _validate_import(
        self,
        service_id: str,
        diff: FileDiff,
        import_path: str,
        line_num: int,
        dependencies: Set[str],
        all_diffs: List[FileDiff]
    ) -> Optional[HarnessViolation]:
        """
        Validate a single import.
        
        Returns HarnessViolation if invalid, None if valid.
        """
        # Node.js builtins are always valid
        if import_path in NODE_BUILTINS or import_path.startswith('node:'):
            return None
        
        # Relative imports
        if import_path.startswith('.'):
            return self._validate_relative_import(
                service_id, diff, import_path, line_num, all_diffs
            )
        
        # Package imports
        return self._validate_package_import(
            service_id, diff, import_path, line_num, dependencies
        )
    
    def _validate_relative_import(
        self,
        service_id: str,
        diff: FileDiff,
        import_path: str,
        line_num: int,
        all_diffs: List[FileDiff]
    ) -> Optional[HarnessViolation]:
        """Validate a relative import (./foo, ../bar)."""
        # Get the directory of the importing file
        file_path = Path(diff.file_path)
        
        # For service-relative paths like "audit-service/src/utils/logger.js"
        # Extract just the relative part within the service
        parts = file_path.parts
        service_idx = None
        for i, part in enumerate(parts):
            if part == service_id:
                service_idx = i
                break
        
        if service_idx is not None:
            relative_parts = parts[service_idx:]
            file_dir = Path(*relative_parts[:-1])
        else:
            file_dir = file_path.parent
        
        # Resolve the import path
        resolved = (file_dir / import_path).resolve()
        
        # Try different extensions
        extensions = ['', '.js', '.ts', '.jsx', '.tsx', '.json', '/index.js', '/index.ts']
        
        for ext in extensions:
            # Check if file exists on disk
            full_path = self.services_path / service_id / str(resolved) + ext
            if full_path.exists():
                return None
            
            # Check relative to service root
            service_root = self.services_path / service_id
            test_path = service_root / (str(resolved) + ext).lstrip('/')
            if test_path.exists():
                return None
        
        # Check if file is being created in this diff set
        for d in all_diffs:
            if import_path in d.file_path or d.file_path.endswith(import_path.lstrip('./')):
                return None
        
        # File not found
        return HarnessViolation(
            severity=ViolationSeverity.ERROR,
            check=CheckType.IMPORT,
            service_id=service_id,
            file_path=diff.file_path,
            description=f"Cannot resolve import '{import_path}' - file not found",
            line_number=line_num,
            fix_hint=f"Create the file or fix the import path",
            details={"import_path": import_path, "resolved": str(resolved)},
        )
    
    def _validate_package_import(
        self,
        service_id: str,
        diff: FileDiff,
        import_path: str,
        line_num: int,
        dependencies: Set[str]
    ) -> Optional[HarnessViolation]:
        """Validate a package import (axios, lodash)."""
        # Get the package name (first part before /)
        package_name = import_path.split('/')[0]
        
        # Handle scoped packages (@org/package)
        if package_name.startswith('@') and '/' in import_path:
            parts = import_path.split('/')
            if len(parts) >= 2:
                package_name = f"{parts[0]}/{parts[1]}"
        
        # Check if package is a dependency
        if package_name in dependencies:
            return None
        
        # Check if node_modules exists (installed)
        node_modules = self.services_path / service_id / 'node_modules' / package_name
        if node_modules.exists():
            return None
        
        # Package not found
        return HarnessViolation(
            severity=ViolationSeverity.WARNING,  # Warning because might be peer dep
            check=CheckType.IMPORT,
            service_id=service_id,
            file_path=diff.file_path,
            description=f"Package '{package_name}' not found in dependencies",
            line_number=line_num,
            fix_hint=f"Add '{package_name}' to package.json or verify package name",
            details={"package_name": package_name, "import_path": import_path},
        )
