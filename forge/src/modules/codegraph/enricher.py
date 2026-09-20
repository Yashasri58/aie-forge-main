"""
CodeGraph Enricher
==================

Extracts 4 additional enrichment layers from service files that
codegraph-tools does not cover:

  1. Package dependencies  -- package.json  -> Package nodes + DEPENDS_ON edges
  2. Database schemas      -- db/*.js        -> DbTable nodes + OWNS_TABLE edges
  3. OpenAPI contracts     -- contracts/openapi.yaml -> ApiEndpoint + EXPOSES_ENDPOINT
  4. Environment variables -- *.js process.env.* -> EnvVar nodes + READS_ENV edges

All extractors are pure stdlib + pyyaml (already installed as transitive dep).
No new pip dependencies required.

Usage (called from main.py after load_extraction):

    enricher = CodeGraphEnricher(services_path)
    enrichment = enricher.extract_all()
    store.load_enrichment(enrichment)
"""

import json
import re
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Directories to skip when scanning service files
_SKIP_DIRS = {"node_modules", ".git", "dist", "build", "codegraph-out", "__pycache__"}


class CodeGraphEnricher:
    """
    Extracts enrichment data from service source files.

    Works alongside the existing pipeline:
        CodeGraphIndexer  -> AST symbols / call edges   -> Kuzu
        HttpLinker        -> HTTP routes / edges         -> Kuzu
        CodeGraphEnricher -> packages / schemas / APIs / env vars -> Kuzu  (NEW)
    """

    def __init__(self, services_path: str | Path):
        self.services_path = Path(services_path)

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def extract_all(self) -> dict:
        """
        Run all 4 extractors and return a combined dict ready for
        KuzuCodeGraphStore.load_enrichment().
        """
        packages  = self.extract_package_deps()
        db_tables = self.extract_db_schemas()
        endpoints = self.extract_openapi_contracts()
        env_vars  = self.extract_env_vars()

        logger.info(
            "Enricher extracted: %d pkg deps, %d DB tables, "
            "%d API endpoints, %d env var usages",
            len(packages), len(db_tables), len(endpoints), len(env_vars),
        )
        return {
            "packages":  packages,
            "db_tables": db_tables,
            "endpoints": endpoints,
            "env_vars":  env_vars,
        }

    # =========================================================================
    # 1. PACKAGE DEPENDENCIES  (package.json)
    # =========================================================================

    def extract_package_deps(self) -> list[dict]:
        """
        Read package.json from each service directory.

        Returns list of:
            {"service": str, "package": str, "version": str, "dep_type": "runtime"|"dev"}
        """
        results = []
        for pkg_file in sorted(self.services_path.rglob("package.json")):
            if any(skip in pkg_file.parts for skip in _SKIP_DIRS):
                continue
            try:
                data = json.loads(pkg_file.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Could not parse %s: %s", pkg_file, exc)
                continue

            # Service name = immediate subdirectory of services_path
            try:
                service = pkg_file.relative_to(self.services_path).parts[0]
            except ValueError:
                continue

            for name, version in (data.get("dependencies") or {}).items():
                results.append({
                    "service":  service,
                    "package":  name,
                    "version":  version,
                    "dep_type": "runtime",
                })
            for name, version in (data.get("devDependencies") or {}).items():
                results.append({
                    "service":  service,
                    "package":  name,
                    "version":  version,
                    "dep_type": "dev",
                })

        logger.info("Package deps: %d entries from package.json files", len(results))
        return results

    # =========================================================================
    # 2. DATABASE SCHEMAS  (SQL CREATE TABLE inside db/*.js)
    # =========================================================================

    # Matches:  CREATE TABLE [IF NOT EXISTS] tablename (  ...body...  )
    _CREATE_TABLE_RE = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"']?(\w+)[`\"']?\s*\(([^;]+?)\)",
        re.IGNORECASE | re.DOTALL,
    )
    # Column line: first token = name, second = type
    _COLUMN_SKIP_PREFIXES = (
        "PRIMARY", "FOREIGN", "UNIQUE", "INDEX", "CHECK", "CONSTRAINT",
        "--", "/*", "CREATE", "ALTER", "DROP",
    )

    def extract_db_schemas(self) -> list[dict]:
        """
        Scan db/ subdirectories for JS files containing SQL CREATE TABLE.

        Returns list of:
            {"service": str, "table": str, "columns": [{"name": str, "type": str}]}
        """
        results = []
        # Target db/database.js files specifically (all services follow this pattern)
        for db_file in sorted(self.services_path.rglob("*/db/database.js")):
            if any(skip in db_file.parts for skip in _SKIP_DIRS):
                continue
            try:
                service = db_file.relative_to(self.services_path).parts[0]
            except ValueError:
                continue

            source = db_file.read_text(encoding="utf-8", errors="replace")
            for match in self._CREATE_TABLE_RE.finditer(source):
                table_name = match.group(1)
                body = match.group(2)
                columns = self._parse_columns(body)
                if columns:
                    results.append({
                        "service": service,
                        "table":   table_name,
                        "columns": columns,
                    })

        logger.info("DB schemas: %d tables found", len(results))
        return results

    def _parse_columns(self, body: str) -> list[dict]:
        columns = []
        for raw_line in body.split("\n"):
            line = raw_line.strip().rstrip(",").strip()
            if not line:
                continue
            upper = line.upper()
            if any(upper.startswith(kw) for kw in self._COLUMN_SKIP_PREFIXES):
                continue
            parts = line.split()
            if len(parts) >= 2:
                columns.append({"name": parts[0], "type": parts[1]})
        return columns

    # =========================================================================
    # 3. OPENAPI CONTRACTS  (contracts/openapi.yaml)
    # =========================================================================

    def extract_openapi_contracts(self) -> list[dict]:
        """
        Parse OpenAPI 3.x YAML from each service's contracts/ directory.

        Returns list of:
            {
              "service": str, "method": str, "path": str,
              "operation_id": str | None,
              "request_schema": str | None,
              "response_schemas": [str],
            }
        """
        try:
            import yaml
        except ImportError:
            logger.warning("pyyaml not installed -- skipping OpenAPI extraction")
            return []

        results = []
        for yaml_file in sorted(self.services_path.rglob("contracts/openapi.yaml")):
            if any(skip in yaml_file.parts for skip in _SKIP_DIRS):
                continue
            try:
                service = yaml_file.relative_to(self.services_path).parts[0]
            except ValueError:
                continue

            try:
                spec = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Could not parse %s: %s", yaml_file, exc)
                continue

            for path, methods in (spec.get("paths") or {}).items():
                if not isinstance(methods, dict):
                    continue
                for method, operation in methods.items():
                    if method not in ("get", "post", "put", "delete", "patch"):
                        continue
                    if not isinstance(operation, dict):
                        continue

                    # Request schema ($ref name)
                    req_schema = None
                    body = operation.get("requestBody") or {}
                    content = (body.get("content") or {}).get("application/json") or {}
                    ref = (content.get("schema") or {}).get("$ref", "")
                    if ref:
                        req_schema = ref.split("/")[-1]

                    # Response schemas
                    resp_schemas = []
                    for _status, resp in (operation.get("responses") or {}).items():
                        if not isinstance(resp, dict):
                            continue
                        rc = (resp.get("content") or {}).get("application/json") or {}
                        r = (rc.get("schema") or {}).get("$ref", "")
                        if r:
                            resp_schemas.append(r.split("/")[-1])

                    results.append({
                        "service":          service,
                        "method":           method.upper(),
                        "path":             path,
                        "operation_id":     operation.get("operationId"),
                        "request_schema":   req_schema,
                        "response_schemas": list(set(resp_schemas)),
                    })

        logger.info("OpenAPI contracts: %d endpoints found", len(results))
        return results

    # =========================================================================
    # 4. ENVIRONMENT VARIABLES  (process.env in *.js)
    # =========================================================================

    _ENV_VAR_RE = re.compile(
        r"process\.env\.([A-Z_][A-Z0-9_]+)"
        r"|process\.env\[['\"]([A-Z_][A-Z0-9_]+)['\"]\]"
    )

    def extract_env_vars(self) -> list[dict]:
        """
        Scan all JS files for process.env.VAR_NAME references.

        Returns list of:
            {"service": str, "env_var": str}
        """
        results = []
        seen: set[tuple] = set()

        for js_file in sorted(self.services_path.rglob("*.js")):
            if any(skip in js_file.parts for skip in _SKIP_DIRS):
                continue
            try:
                service = js_file.relative_to(self.services_path).parts[0]
            except ValueError:
                continue

            source = js_file.read_text(encoding="utf-8", errors="replace")
            for match in self._ENV_VAR_RE.finditer(source):
                var_name = match.group(1) or match.group(2)
                key = (service, var_name)
                if key not in seen:
                    seen.add(key)
                    results.append({"service": service, "env_var": var_name})

        logger.info("Env vars: %d unique service/var pairs found", len(results))
        return results
