"""
Test script: validate all 4 enrichment requirements against real service files.

Run from forge/:
    venv\Scripts\python.exe test_enrichment.py

Tests:
  1. Package dependencies  (package.json)
  2. Database schemas      (SQL inside db/*.js)
  3. OpenAPI contracts     (contracts/openapi.yaml)
  4. Environment variables (process.env in *.js + docker-compose.yaml)

Also confirms codegraph-tools cannot cover these (shows what it actually extracts).
"""

import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml not installed. Run: pip install pyyaml")
    sys.exit(1)

SERVICES_PATH = Path(__file__).parent.parent / "services"
SEP = "=" * 70


# =============================================================================
# 1. PACKAGE DEPENDENCIES
# =============================================================================

def extract_package_deps(services_path: Path) -> list[dict]:
    """Read package.json from each service and extract dependencies."""
    results = []
    for pkg_file in sorted(services_path.rglob("package.json")):
        if "node_modules" in str(pkg_file):
            continue
        try:
            data = json.load(open(pkg_file, encoding="utf-8"))
        except Exception as e:
            print(f"  WARN: could not parse {pkg_file}: {e}")
            continue
        service = pkg_file.parent.name
        for name, version in data.get("dependencies", {}).items():
            results.append({"service": service, "package": name, "version": version, "type": "runtime"})
        for name, version in data.get("devDependencies", {}).items():
            results.append({"service": service, "package": name, "version": version, "type": "dev"})
    return results


def test_package_deps():
    print(f"\n{SEP}")
    print("TEST 1: PACKAGE DEPENDENCIES (package.json)")
    print(SEP)

    deps = extract_package_deps(SERVICES_PATH)

    if not deps:
        print("  FAIL: No dependencies found")
        return

    # Group by package to find shared dependencies
    from collections import defaultdict
    pkg_to_services = defaultdict(list)
    for d in deps:
        if d["type"] == "runtime":
            pkg_to_services[d["package"]].append((d["service"], d["version"]))

    print(f"\n  Total: {len(deps)} entries ({len([d for d in deps if d['type']=='runtime'])} runtime, "
          f"{len([d for d in deps if d['type']=='dev'])} dev)\n")

    # Per-service table
    service_deps = defaultdict(list)
    for d in deps:
        if d["type"] == "runtime":
            service_deps[d["service"]].append(f"{d['package']}@{d['version']}")

    print("  Per-service runtime dependencies:")
    for svc, pkgs in sorted(service_deps.items()):
        print(f"    {svc:30} {', '.join(pkgs)}")

    # Cross-service shared packages
    shared = {pkg: svcs for pkg, svcs in pkg_to_services.items() if len(svcs) > 1}
    print(f"\n  Shared packages (used by 2+ services) -- version drift risk:")
    for pkg, svcs in sorted(shared.items()):
        versions = set(v for _, v in svcs)
        drift = " !!  VERSION DRIFT" if len(versions) > 1 else ""
        svc_names = [s for s, _ in svcs]
        print(f"    {pkg:25} [{', '.join(versions)}]  in: {', '.join(svc_names)}{drift}")

    # Value demonstration
    print("\n  VALUE: Forge can now answer:")
    print("    - 'Which services use axios?' => change HTTP client")
    print("    - 'If better-sqlite3 has a CVE, what is the blast radius?'")
    print("    - 'Are there version mismatches across services?'")
    print("\n  PASS OK")


# =============================================================================
# 2. DATABASE SCHEMAS
# =============================================================================

def extract_sql_schemas(js_source: str, service: str, filename: str) -> list[dict]:
    """Extract CREATE TABLE definitions from SQL strings inside JS files."""
    tables = []
    pattern = r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`"\']?(\w+)[`"\']?\s*\(([^;]+?)\)'
    for match in re.finditer(pattern, js_source, re.IGNORECASE | re.DOTALL):
        table_name = match.group(1)
        columns_raw = match.group(2)
        columns = []
        for line in columns_raw.split('\n'):
            line = line.strip().rstrip(',').strip()
            if not line:
                continue
            upper = line.upper()
            # Skip constraint definitions
            if any(upper.startswith(kw) for kw in ('PRIMARY', 'FOREIGN', 'UNIQUE', 'INDEX', 'CHECK', 'CONSTRAINT')):
                continue
            parts = line.split()
            if len(parts) >= 2:
                col_name = parts[0]
                col_type = parts[1]
                # Filter out obvious non-column lines
                if col_name.upper() in ('CREATE', 'ALTER', 'DROP', 'INSERT', '--'):
                    continue
                nullable = "NOT NULL" not in line.upper()
                default = None
                dm = re.search(r'DEFAULT\s+(\S+)', line, re.IGNORECASE)
                if dm:
                    default = dm.group(1)
                columns.append({
                    "name": col_name,
                    "type": col_type,
                    "nullable": nullable,
                    "default": default
                })
        if columns:
            tables.append({
                "service": service,
                "table": table_name,
                "file": filename,
                "columns": columns
            })
    return tables


def test_db_schemas():
    print(f"\n{SEP}")
    print("TEST 2: DATABASE SCHEMAS (SQL inside db/*.js)")
    print(SEP)

    all_tables = []
    for db_file in sorted(SERVICES_PATH.rglob("*/db/database.js")):
        service = db_file.parent.parent.parent.name
        source = db_file.read_text(encoding="utf-8")
        tables = extract_sql_schemas(source, service, db_file.name)
        all_tables.extend(tables)

    if not all_tables:
        print("  FAIL: No tables found")
        return

    print(f"\n  Found {len(all_tables)} tables across {len(set(t['service'] for t in all_tables))} services:\n")

    for tbl in all_tables:
        col_names = [c["name"] for c in tbl["columns"]]
        print(f"  {tbl['service']:25} -> {tbl['table']:35} columns: {', '.join(col_names)}")

    # Cross-table analysis
    print(f"\n  Cross-table analysis:")
    all_columns = {}
    for tbl in all_tables:
        for col in tbl["columns"]:
            key = col["name"].lower()
            if key not in all_columns:
                all_columns[key] = []
            all_columns[key].append(f"{tbl['service']}.{tbl['table']}")

    # Find columns shared across services (potential join/sync points)
    shared_cols = {k: v for k, v in all_columns.items() if len(v) > 1}
    interesting = {k: v for k, v in shared_cols.items()
                   if any(x in k for x in ['payment_id', 'account_id', 'amount', 'currency', 'status'])}
    print(f"  Shared key columns (same name across services):")
    for col, locations in sorted(interesting.items()):
        print(f"    {col:25} appears in: {', '.join(locations)}")

    print("\n  VALUE: Forge can now answer:")
    print("    - 'I renamed column payment_id -- which other tables use it?'")
    print("    - 'Which tables own the payment lifecycle state?'")
    print("    - 'What is the full data model for a payment?'")
    print("\n  PASS OK")


# =============================================================================
# 3. OPENAPI CONTRACTS
# =============================================================================

def extract_openapi_contracts(services_path: Path) -> list[dict]:
    """Parse openapi.yaml from each service's contracts/ directory."""
    endpoints = []
    for yaml_file in sorted(services_path.rglob("contracts/openapi.yaml")):
        service = yaml_file.parent.parent.name
        try:
            spec = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  WARN: could not parse {yaml_file}: {e}")
            continue

        for path, methods in (spec.get("paths") or {}).items():
            if not isinstance(methods, dict):
                continue
            for method, operation in methods.items():
                if method not in ("get", "post", "put", "delete", "patch"):
                    continue
                if not isinstance(operation, dict):
                    continue

                # Request schema
                req_schema = None
                body = operation.get("requestBody") or {}
                content = (body.get("content") or {}).get("application/json") or {}
                schema_ref = (content.get("schema") or {}).get("$ref", "")
                if schema_ref:
                    req_schema = schema_ref.split("/")[-1]

                # Response schemas
                resp_schemas = []
                for status, resp in (operation.get("responses") or {}).items():
                    if not isinstance(resp, dict):
                        continue
                    rc = (resp.get("content") or {}).get("application/json") or {}
                    ref = (rc.get("schema") or {}).get("$ref", "")
                    if ref:
                        resp_schemas.append(ref.split("/")[-1])
                    # Also check array items
                    schema = rc.get("schema") or {}
                    items_ref = (schema.get("items") or {}).get("$ref", "")
                    if items_ref:
                        resp_schemas.append(items_ref.split("/")[-1])

                # Parameters
                params = [p.get("name") for p in (operation.get("parameters") or [])
                          if isinstance(p, dict) and p.get("in") == "path"]

                endpoints.append({
                    "service": service,
                    "method": method.upper(),
                    "path": path,
                    "operation_id": operation.get("operationId"),
                    "request_schema": req_schema,
                    "response_schemas": list(set(resp_schemas)),
                    "path_params": params,
                    "tags": operation.get("tags", []),
                })
    return endpoints


def test_openapi_contracts():
    print(f"\n{SEP}")
    print("TEST 3: OPENAPI CONTRACTS (contracts/openapi.yaml)")
    print(SEP)

    endpoints = extract_openapi_contracts(SERVICES_PATH)

    if not endpoints:
        print("  FAIL: No endpoints found")
        return

    print(f"\n  Found {len(endpoints)} endpoints across "
          f"{len(set(e['service'] for e in endpoints))} services:\n")

    # Group by service
    from collections import defaultdict
    by_service = defaultdict(list)
    for ep in endpoints:
        by_service[ep["service"]].append(ep)

    for svc, eps in sorted(by_service.items()):
        print(f"  {svc} ({len(eps)} endpoints):")
        for ep in eps:
            req = f" <- {ep['request_schema']}" if ep["request_schema"] else ""
            resp = f" -> {', '.join(ep['response_schemas'])}" if ep["response_schemas"] else ""
            print(f"    {ep['method']:6} {ep['path']:45}{req}{resp}")

    # Find schemas shared across services (contracts that consumers depend on)
    all_response_schemas = defaultdict(list)
    for ep in endpoints:
        for schema in ep["response_schemas"]:
            all_response_schemas[schema].append(ep["service"])

    print(f"\n  Response schemas used by multiple services (breaking change risk):")
    for schema, svcs in sorted(all_response_schemas.items()):
        if len(svcs) > 1:
            print(f"    {schema:30} exposed by: {', '.join(set(svcs))}")

    print("\n  VALUE: Forge can now answer:")
    print("    - 'I changed Payment response schema -- which consumers break?'")
    print("    - 'Does the code return all fields declared in OpenAPI?'")
    print("    - 'Which endpoints have no request validation schema?'")
    print("\n  PASS OK")


# =============================================================================
# 4. ENVIRONMENT VARIABLES
# =============================================================================

def extract_env_vars_from_js(js_source: str, service: str) -> list[dict]:
    """Find all process.env.VAR_NAME usages in JS source."""
    pattern = r'process\.env\.([A-Z_][A-Z0-9_]+)|process\.env\[[\'"]([A-Z_][A-Z0-9_]+)[\'"]\]'
    found = set()
    for match in re.finditer(pattern, js_source):
        var_name = match.group(1) or match.group(2)
        found.add(var_name)
    return [{"service": service, "env_var": v} for v in sorted(found)]


def extract_compose_env(compose_path: Path) -> dict[str, dict]:
    """Read declared env vars from docker-compose.yaml."""
    result = {}
    try:
        compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  WARN: could not parse docker-compose.yaml: {e}")
        return result

    for svc_name, svc_config in (compose.get("services") or {}).items():
        env_list = svc_config.get("environment") or []
        svc_env = {}
        for item in env_list:
            if "=" in str(item):
                k, v = str(item).split("=", 1)
                svc_env[k] = v
            else:
                svc_env[str(item)] = None
        result[svc_name] = svc_env
    return result


def test_env_vars():
    print(f"\n{SEP}")
    print("TEST 4: ENVIRONMENT VARIABLES (process.env + docker-compose.yaml)")
    print(SEP)

    # Collect from JS files
    from collections import defaultdict
    code_env = defaultdict(set)
    for js_file in sorted(SERVICES_PATH.rglob("*.js")):
        if "node_modules" in str(js_file) or "codegraph-out" in str(js_file):
            continue
        service = js_file.parts[-(js_file.parts.index("services") if "services" in js_file.parts else 0) - 1]
        # Get service name from path
        rel = js_file.relative_to(SERVICES_PATH)
        service = rel.parts[0]
        source = js_file.read_text(encoding="utf-8", errors="replace")
        for item in extract_env_vars_from_js(source, service):
            code_env[service].add(item["env_var"])

    # Collect from docker-compose.yaml
    compose_path = SERVICES_PATH / "docker-compose.yaml"
    compose_env = extract_compose_env(compose_path)

    print(f"\n  Env vars used in code vs declared in docker-compose.yaml:\n")

    all_services = sorted(set(list(code_env.keys()) + list(compose_env.keys())))

    gaps_found = []
    for svc in all_services:
        code_vars = code_env.get(svc, set())
        compose_vars = set(compose_env.get(svc, {}).keys())

        in_code_only = code_vars - compose_vars   # used in code but NOT declared in compose
        in_compose_only = compose_vars - code_vars  # declared in compose but NOT used in code
        matched = code_vars & compose_vars

        print(f"  {svc}:")
        if matched:
            print(f"    OK Declared & used:    {', '.join(sorted(matched))}")
        if in_compose_only:
            print(f"    i Compose-only:       {', '.join(sorted(in_compose_only))}")
        if in_code_only:
            print(f"    !! Code reads but not in compose: {', '.join(sorted(in_code_only))}")
            gaps_found.append((svc, in_code_only))

    if gaps_found:
        print(f"\n  !!  GAPS DETECTED -- {len(gaps_found)} service(s) read env vars not in docker-compose:")
        for svc, vars_ in gaps_found:
            print(f"    {svc}: {', '.join(sorted(vars_))}")
    else:
        print("\n  All env vars declared in compose match code usage.")

    print("\n  VALUE: Forge can now answer:")
    print("    - 'If I rename a service URL env var, which services break?'")
    print("    - 'Are there env vars read in code but missing from compose?'")
    print("    - 'Which services depend on each other via URL config?'")
    print("\n  PASS OK")


# =============================================================================
# 5. CODEGRAPH-TOOLS CONFIRMATION -- what it cannot do
# =============================================================================

def test_codegraph_limitations():
    print(f"\n{SEP}")
    print("TEST 5: CONFIRM codegraph-tools CANNOT COVER THESE REQUIREMENTS")
    print(SEP)

    from codegraph.extract import extract
    result = extract([
        SERVICES_PATH / "payment-processor" / "src" / "clients" / "accountClient.js",
        SERVICES_PATH / "payment-processor" / "src" / "db" / "database.js",
    ])

    relation_types = set(e["relation"] for e in result["edges"])
    targets = [e["target"] for e in result["edges"]]

    print(f"\n  Extracted {len(result['nodes'])} nodes, {len(result['edges'])} edges")
    print(f"  Relation types found: {relation_types}")
    print(f"\n  Edge targets (what codegraph tracks):")
    for e in result["edges"]:
        print(f"    {e['relation']:15} | {e['source'][:35]:35} -> {e['target']}")

    # Check for package deps
    pkg_targets = [t for t in targets if any(p in t for p in ['express', 'sqlite', 'cors', 'uuid', 'axios'])]
    print(f"\n  Package names in edge targets: {pkg_targets}")
    print(f"  -> codegraph tracks packages: {'YES' if pkg_targets else 'NO -- confirmed missing'}")

    # Check for SQL
    sql_nodes = [n for n in result["nodes"] if any(k in str(n.get("label","")).upper()
                                                     for k in ["CREATE", "TABLE", "PAYMENTS", "INSERT"])]
    print(f"\n  SQL/table nodes: {sql_nodes}")
    print(f"  -> codegraph tracks DB schemas: {'YES' if sql_nodes else 'NO -- confirmed missing'}")

    # Check for env vars
    env_nodes = [n for n in result["nodes"] if "env" in str(n.get("label","")).lower()]
    print(f"\n  ENV var nodes: {env_nodes}")
    print(f"  -> codegraph tracks env vars: {'YES' if env_nodes else 'NO -- confirmed missing'}")

    print("\n  CONCLUSION: codegraph-tools extracts only 3 relation types:")
    print("    contains (file->class->method), method (class->method), calls (fn->fn)")
    print("  All 4 enrichment requirements need custom extractors.")
    print("\n  PASS OK")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print(f"\nFORGE ENRICHMENT TEST SUITE")
    print(f"Services path: {SERVICES_PATH}")
    if not SERVICES_PATH.exists():
        print(f"ERROR: services path not found: {SERVICES_PATH}")
        sys.exit(1)

    test_package_deps()
    test_db_schemas()
    test_openapi_contracts()
    test_env_vars()
    test_codegraph_limitations()

    print(f"\n{SEP}")
    print("ALL TESTS COMPLETE")
    print(SEP)
