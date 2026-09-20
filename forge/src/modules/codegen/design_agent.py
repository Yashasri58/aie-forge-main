"""
Design Agent.

The "Brain" of code generation. Has access to the codebase and code graph.
Explores the code, finds patterns, and creates the complete execution plan.

Tools available:
- query_code_graph: Query symbols, calls, HTTP connections
- read_file: Read any file in the codebase
- grep: Search for patterns
- find_symbol: Locate symbol definitions
"""

import os
import re
import json
import time
import glob as glob_module
from pathlib import Path
from typing import Optional

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from .schemas import Plan
from .prompts import DESIGN_AGENT_SYSTEM_PROMPT
from .logging_config import (
    design_logger as logger,
    log_tool_call,
    log_llm_call,
)


# =============================================================================
# TOOL IMPLEMENTATIONS
# =============================================================================

class DesignAgentTools:
    """Tools available to the Design Agent."""
    
    def __init__(self, graph_store, services_path: str):
        """
        Args:
            graph_store: KuzuGraphStore instance
            services_path: Path to the services directory
        """
        self._store = graph_store
        self._services_path = Path(services_path)
    
    def query_code_graph(
        self, 
        query_type: str, 
        service: str = None,
        file: str = None,
        symbol: str = None,
        limit: int = 50
    ) -> dict:
        """
        Query the code graph for symbols, calls, or connections.
        
        Args:
            query_type: One of:
                "symbols"          - functions/classes by service/file/name
                "calls"            - call edges between symbols
                "callers"          - what calls a given symbol (requires symbol=)
                "callees"          - what a given symbol calls (requires symbol=)
                "http_connections" - HTTP service-to-service edges
                "packages"         - npm package dependencies (requires service=)
                "db_tables"        - DB tables owned by a service (requires service=)
                "api_endpoints"    - OpenAPI endpoints for a service (requires service=)
                "env_vars"         - env vars read by a service (requires service=)
            service: Filter by service name
            file: Filter by file path (symbols only)
            symbol: Filter by symbol name
            limit: Max results
            
        Returns:
            Query results
        """
        log_tool_call(logger, "query_code_graph", {
            "query_type": query_type, "service": service, "file": file, "symbol": symbol
        })
        try:
            if query_type == "symbols":
                # Get all symbols, optionally filtered
                cypher = "MATCH (s:Symbol)"
                conditions = []
                if service:
                    conditions.append(f"s.service = '{service}'")
                if file:
                    conditions.append(f"s.file CONTAINS '{file}'")
                if symbol:
                    conditions.append(f"s.name CONTAINS '{symbol}'")
                
                if conditions:
                    cypher += " WHERE " + " AND ".join(conditions)
                cypher += f" RETURN s.name, s.kind, s.file, s.service LIMIT {limit}"
                
                result = self._store.query(cypher)
                return {
                    "type": "symbols",
                    "count": len(result),
                    "results": [
                        {"name": r[0], "kind": r[1], "file": r[2], "service": r[3]}
                        for r in result
                    ]
                }
            
            elif query_type == "calls":
                # Get call relationships
                cypher = "MATCH (caller:Symbol)-[:CALLS]->(callee:Symbol)"
                conditions = []
                if service:
                    conditions.append(f"(caller.service = '{service}' OR callee.service = '{service}')")
                if symbol:
                    conditions.append(f"(caller.name = '{symbol}' OR callee.name = '{symbol}')")
                
                if conditions:
                    cypher += " WHERE " + " AND ".join(conditions)
                cypher += f" RETURN caller.name, caller.service, callee.name, callee.service LIMIT {limit}"
                
                result = self._store.query(cypher)
                return {
                    "type": "calls",
                    "count": len(result),
                    "results": [
                        {
                            "caller": r[0], 
                            "caller_service": r[1], 
                            "callee": r[2], 
                            "callee_service": r[3]
                        }
                        for r in result
                    ]
                }
            
            elif query_type == "callers":
                # Get all callers of a symbol
                if not symbol:
                    return {"error": "symbol parameter required for callers query"}
                
                cypher = f"""
                MATCH (caller:Symbol)-[:CALLS]->(callee:Symbol)
                WHERE callee.name = '{symbol}'
                RETURN caller.name, caller.kind, caller.file, caller.service
                LIMIT {limit}
                """
                result = self._store.query(cypher)
                return {
                    "type": "callers",
                    "symbol": symbol,
                    "count": len(result),
                    "results": [
                        {"name": r[0], "kind": r[1], "file": r[2], "service": r[3]}
                        for r in result
                    ]
                }
            
            elif query_type == "callees":
                # Get all callees of a symbol
                if not symbol:
                    return {"error": "symbol parameter required for callees query"}
                
                cypher = f"""
                MATCH (caller:Symbol)-[:CALLS]->(callee:Symbol)
                WHERE caller.name = '{symbol}'
                RETURN callee.name, callee.kind, callee.file, callee.service
                LIMIT {limit}
                """
                result = self._store.query(cypher)
                return {
                    "type": "callees",
                    "symbol": symbol,
                    "count": len(result),
                    "results": [
                        {"name": r[0], "kind": r[1], "file": r[2], "service": r[3]}
                        for r in result
                    ]
                }
            
            elif query_type == "http_connections":
                # Get HTTP service connections
                cypher = """
                MATCH (s1:Service)-[r:HTTP_CALLS]->(s2:Service)
                RETURN s1.name, r.method, r.endpoint, s2.name
                LIMIT 100
                """
                try:
                    result = self._store.query(cypher)
                    return {
                        "type": "http_connections",
                        "count": len(result),
                        "results": [
                            {
                                "from_service": r[0],
                                "method": r[1],
                                "endpoint": r[2],
                                "to_service": r[3]
                            }
                            for r in result
                        ]
                    }
                except Exception:
                    # HTTP connections might not exist
                    return {"type": "http_connections", "count": 0, "results": []}
            
            elif query_type == "packages":
                # npm package dependencies for a service
                cypher = "MATCH (s:Service)-[r:DEPENDS_ON]->(p:Package)"
                if service:
                    cypher += f" WHERE s.name = '{service}'"
                cypher += " RETURN s.name AS service, p.name AS package, r.version AS version, r.dep_type AS dep_type"
                cypher += f" LIMIT {limit}"
                result = self._store.query(cypher)
                return {
                    "type": "packages",
                    "count": len(result),
                    "results": result,
                }

            elif query_type == "db_tables":
                # DB tables owned by a service
                cypher = "MATCH (s:Service)-[:OWNS_TABLE]->(t:DbTable)"
                if service:
                    cypher += f" WHERE s.name = '{service}'"
                cypher += " RETURN s.name AS service, t.table_name AS table"
                cypher += f" LIMIT {limit}"
                result = self._store.query(cypher)
                return {
                    "type": "db_tables",
                    "count": len(result),
                    "results": result,
                }

            elif query_type == "api_endpoints":
                # OpenAPI endpoints for a service
                cypher = "MATCH (s:Service)-[:EXPOSES_ENDPOINT]->(e:ApiEndpoint)"
                if service:
                    cypher += f" WHERE s.name = '{service}'"
                cypher += " RETURN s.name AS service, e.method AS method, e.path AS path, e.operation_id AS operation_id"
                cypher += f" LIMIT {limit}"
                result = self._store.query(cypher)
                return {
                    "type": "api_endpoints",
                    "count": len(result),
                    "results": result,
                }

            elif query_type == "env_vars":
                # Env vars read by a service
                cypher = "MATCH (s:Service)-[:READS_ENV]->(e:EnvVar)"
                if service:
                    cypher += f" WHERE s.name = '{service}'"
                cypher += " RETURN s.name AS service, e.name AS env_var"
                cypher += f" LIMIT {limit}"
                result = self._store.query(cypher)
                return {
                    "type": "env_vars",
                    "count": len(result),
                    "results": result,
                }

            else:
                return {"error": f"Unknown query_type: {query_type}"}
                
        except Exception as e:
            return {"error": str(e)}
    
    def read_file(self, file_path: str) -> dict:
        """
        Read a file from the services directory.
        
        Args:
            file_path: Relative path from services directory
            
        Returns:
            File content or error
        """
        log_tool_call(logger, "read_file", {"file_path": file_path})
        try:
            # Handle both absolute and relative paths
            if os.path.isabs(file_path):
                full_path = Path(file_path)
            else:
                full_path = self._services_path / file_path
            
            # Security check: ensure we're within services
            try:
                full_path.resolve().relative_to(self._services_path.resolve())
            except ValueError:
                return {"error": f"Path {file_path} is outside services directory"}
            
            if not full_path.exists():
                return {"error": f"File not found: {file_path}"}
            
            if not full_path.is_file():
                return {"error": f"Not a file: {file_path}"}
            
            content = full_path.read_text(encoding="utf-8", errors="replace")
            
            return {
                "path": file_path,
                "content": content,
                "lines": len(content.splitlines()),
                "size": len(content),
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    def grep(
        self, 
        pattern: str, 
        file_glob: str = "**/*.js",
        max_results: int = 50,
        include_context: bool = True
    ) -> dict:
        """
        Search for a pattern in files.
        
        Args:
            pattern: Regex pattern to search for
            file_glob: Glob pattern for files (default: **/*.js)
            max_results: Maximum number of results
            include_context: Include surrounding lines
            
        Returns:
            Search results
        """
        log_tool_call(logger, "grep", {"pattern": pattern, "file_glob": file_glob})
        try:
            results = []
            regex = re.compile(pattern, re.IGNORECASE)
            
            # Search files
            for file_path in self._services_path.glob(file_glob):
                if not file_path.is_file():
                    continue
                
                # Skip node_modules and other irrelevant directories
                if any(part in str(file_path) for part in ["node_modules", ".git", "dist", "build"]):
                    continue
                
                try:
                    content = file_path.read_text(encoding="utf-8", errors="replace")
                    lines = content.splitlines()
                    
                    for i, line in enumerate(lines):
                        if regex.search(line):
                            result = {
                                "file": str(file_path.relative_to(self._services_path)),
                                "line_number": i + 1,
                                "line": line.strip(),
                            }
                            
                            if include_context:
                                start = max(0, i - 2)
                                end = min(len(lines), i + 3)
                                result["context"] = "\n".join(lines[start:end])
                            
                            results.append(result)
                            
                            if len(results) >= max_results:
                                return {
                                    "pattern": pattern,
                                    "count": len(results),
                                    "truncated": True,
                                    "results": results,
                                }
                                
                except Exception:
                    continue  # Skip unreadable files
            
            return {
                "pattern": pattern,
                "count": len(results),
                "truncated": False,
                "results": results,
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    def find_symbol(self, name: str) -> dict:
        """
        Find where a symbol is defined.
        
        Args:
            name: Symbol name (can be partial)
            
        Returns:
            Symbol definitions
        """
        log_tool_call(logger, "find_symbol", {"name": name})
        try:
            cypher = f"""
            MATCH (s:Symbol)
            WHERE s.name CONTAINS '{name}'
            RETURN s.name, s.kind, s.file, s.service, s.start_line
            LIMIT 20
            """
            result = self._store.query(cypher)
            
            return {
                "query": name,
                "count": len(result),
                "results": [
                    {
                        "name": r[0],
                        "kind": r[1],
                        "file": r[2],
                        "service": r[3],
                        "line": r[4] if len(r) > 4 else None,
                    }
                    for r in result
                ]
            }
            
        except Exception as e:
            return {"error": str(e)}

    def list_services(self) -> dict:
        """List all indexed services."""
        log_tool_call(logger, "list_services", {})
        try:
            cypher = "MATCH (s:Service) RETURN s.name"
            result = self._store.query(cypher)
            services = [r[0] for r in result]

            if not services:
                # Fallback: list directories
                services = [
                    d.name for d in self._services_path.iterdir()
                    if d.is_dir() and not d.name.startswith(".")
                ]

            return {
                "count": len(services),
                "services": services,
            }
        except Exception as e:
            return {"error": str(e)}

    def find_tests(self, symbol_or_file: str) -> dict:
        """
        Find test files related to a symbol or source file.

        Use this before planning changes to:
        - Know if tests exist that need updating
        - Understand the test pattern used (jest, mocha, etc.)
        - Include test updates in the plan tasks

        Args:
            symbol_or_file: Function name, class name, or source file path

        Returns:
            Matching test files with snippets, test framework detected
        """
        log_tool_call(logger, "find_tests", {"symbol_or_file": symbol_or_file})
        try:
            # Strip extension for file-based search
            base_name = Path(symbol_or_file).stem if "." in symbol_or_file else symbol_or_file

            # Common test file patterns
            test_globs = ["**/*.test.js", "**/*.spec.js", "**/*.test.ts", "**/*.spec.ts", "**/__tests__/*.js"]
            results = []

            for glob_pattern in test_globs:
                for test_file in self._services_path.glob(glob_pattern):
                    if any(part in str(test_file) for part in ["node_modules", "dist", "build"]):
                        continue
                    try:
                        content = test_file.read_text(encoding="utf-8", errors="replace")
                        if base_name.lower() in content.lower():
                            # Detect framework
                            framework = "unknown"
                            if "describe(" in content or "it(" in content:
                                framework = "jest/mocha"
                            if "test(" in content:
                                framework = "jest"

                            # Find matching lines for context
                            lines = content.splitlines()
                            snippets = []
                            for i, line in enumerate(lines):
                                if base_name.lower() in line.lower():
                                    start = max(0, i - 1)
                                    end = min(len(lines), i + 4)
                                    snippets.append("\n".join(lines[start:end]))
                                    if len(snippets) >= 3:
                                        break

                            results.append({
                                "test_file": str(test_file.relative_to(self._services_path)),
                                "framework": framework,
                                "snippets": snippets,
                            })
                    except Exception:
                        continue

            return {
                "query": symbol_or_file,
                "test_files_found": len(results),
                "results": results,
                "tip": "Include test file updates in your plan tasks if tests exist" if results else "No tests found — consider whether tests should be added"
            }
        except Exception as e:
            return {"error": str(e)}

    def get_similar_patterns(self, pattern_type: str, service: str = None) -> dict:
        """
        Find existing code patterns in the codebase to reuse.
        
        Useful for: finding existing retry logic, error handling, logging patterns
        before designing new ones from scratch.
        
        Args:
            pattern_type: One of "retry", "error_handling", "logging", "http_client",
                          "validation", "auth", "caching", "event"
            service: Optionally limit search to a specific service
            
        Returns:
            Matching patterns with file paths and code snippets
        """
        log_tool_call(logger, "get_similar_patterns", {"pattern_type": pattern_type, "service": service})
        
        pattern_map = {
            "retry":          [r"retry\s*\(", r"retryWithBackoff", r"maxAttempts", r"exponential"],
            "error_handling": [r"try\s*{", r"catch\s*\(", r"\.catch\(", r"handleError"],
            "logging":        [r"logger\.", r"console\.(log|error|warn)", r"winston", r"log\."],
            "http_client":    [r"axios\.", r"fetch\(", r"http\.get", r"http\.post", r"request\("],
            "validation":     [r"validate\(", r"schema\.", r"\.isValid", r"Joi\.", r"zod\."],
            "auth":           [r"jwt\.", r"token", r"authorize", r"authenticate", r"bearer"],
            "caching":        [r"cache\.", r"redis\.", r"\.get\(key", r"\.set\(key", r"memoize"],
            "event":          [r"emit\(", r"on\(", r"EventEmitter", r"publish\(", r"subscribe\("],
        }
        
        patterns = pattern_map.get(pattern_type, [r"unknown"])
        combined_pattern = "|".join(patterns)
        
        file_glob = f"{service}/**/*.js" if service else "**/*.js"
        
        results = self.grep(combined_pattern, file_glob=file_glob, max_results=20, include_context=True)
        
        return {
            "pattern_type": pattern_type,
            "service_filter": service,
            "matches": results.get("results", []),
            "count": results.get("count", 0),
            "tip": f"Reuse these existing {pattern_type} patterns instead of writing new ones"
        }

    def get_http_topology(self) -> dict:
        """
        Get the full HTTP dependency map between services.
        
        Use this when designing cross-service changes to understand:
        - Which services call which
        - What routes are exposed
        - What HTTP methods are used
        
        Returns:
            Full HTTP call graph between services
        """
        log_tool_call(logger, "get_http_topology", {})
        try:
            cypher = """
            MATCH (s1:Service)-[r:HTTP_CALLS]->(s2:Service)
            RETURN s1.name AS caller, r.method AS method, r.path AS path, s2.name AS target
            ORDER BY s1.name
            """
            results = self._store.query(cypher)
            
            # Build adjacency map
            topology = {}
            for row in results:
                caller, method, path, target = row[0], row[1], row[2], row[3]
                if caller not in topology:
                    topology[caller] = []
                topology[caller].append({
                    "calls": target,
                    "method": method,
                    "path": path,
                })
            
            return {
                "http_calls": [
                    {"from": caller, "to": edge["calls"], "method": edge["method"], "path": edge["path"]}
                    for caller, edges in topology.items()
                    for edge in edges
                ],
                "adjacency": topology,
                "total_connections": sum(len(v) for v in topology.values()),
            }
        except Exception as e:
            return {"error": str(e), "http_calls": [], "adjacency": {}}


        try:
            cypher = "MATCH (s:Service) RETURN s.name"
            result = self._store.query(cypher)
            services = [r[0] for r in result]
            
            return {
                "count": len(services),
                "services": services,
            }
        except Exception:
            # Fallback: list directories
            services = [
                d.name for d in self._services_path.iterdir()
                if d.is_dir() and not d.name.startswith(".")
            ]
            return {
                "count": len(services),
                "services": services,
            }
    
    def list_directory(self, path: str, recursive: bool = False) -> dict:
        """
        List contents of a directory.
        
        Args:
            path: Relative path from services directory
            recursive: If True, list subdirectories recursively (max 2 levels)
            
        Returns:
            Directory contents with files and subdirectories
        """
        log_tool_call(logger, "list_directory", {"path": path, "recursive": recursive})
        try:
            if path == "" or path == ".":
                full_path = self._services_path
            else:
                full_path = self._services_path / path
            
            # Security check
            try:
                full_path.resolve().relative_to(self._services_path.resolve())
            except ValueError:
                return {"error": f"Path {path} is outside services directory"}
            
            if not full_path.exists():
                return {"error": f"Directory not found: {path}"}
            
            if not full_path.is_dir():
                return {"error": f"Not a directory: {path}"}
            
            files = []
            directories = []
            
            for item in sorted(full_path.iterdir()):
                # Skip hidden and common non-essential directories
                if item.name.startswith(".") or item.name in ["node_modules", "dist", "build", "__pycache__"]:
                    continue
                
                rel_path = str(item.relative_to(self._services_path))
                
                if item.is_file():
                    files.append({
                        "name": item.name,
                        "path": rel_path,
                        "size": item.stat().st_size,
                    })
                elif item.is_dir():
                    dir_info = {
                        "name": item.name,
                        "path": rel_path,
                    }
                    
                    # If recursive, list contents (max 2 levels)
                    if recursive:
                        subfiles = []
                        subdirs = []
                        try:
                            for subitem in sorted(item.iterdir()):
                                if subitem.name.startswith(".") or subitem.name in ["node_modules", "dist", "build"]:
                                    continue
                                sub_rel = str(subitem.relative_to(self._services_path))
                                if subitem.is_file():
                                    subfiles.append({"name": subitem.name, "path": sub_rel})
                                elif subitem.is_dir():
                                    subdirs.append({"name": subitem.name, "path": sub_rel})
                        except PermissionError:
                            pass
                        dir_info["files"] = subfiles
                        dir_info["subdirectories"] = subdirs
                    
                    directories.append(dir_info)
            
            return {
                "path": path or ".",
                "files": files,
                "directories": directories,
                "file_count": len(files),
                "directory_count": len(directories),
            }
            
        except Exception as e:
            return {"error": str(e)}


# =============================================================================
# MODULE-LEVEL TOOL FUNCTIONS (for ADK)
# =============================================================================

_tools: Optional[DesignAgentTools] = None


def query_code_graph(
    query_type: str, 
    service: str = None,
    file: str = None,
    symbol: str = None,
    limit: int = 50
) -> dict:
    """Query the code graph for symbols, calls, or connections."""
    return _tools.query_code_graph(query_type, service, file, symbol, limit)


def read_file(file_path: str) -> dict:
    """Read a file from the codebase."""
    return _tools.read_file(file_path)


def grep(
    pattern: str, 
    file_glob: str = "**/*.js",
    max_results: int = 50,
    include_context: bool = True
) -> dict:
    """Search for a pattern in files."""
    return _tools.grep(pattern, file_glob, max_results, include_context)


def find_symbol(name: str) -> dict:
    """Find where a symbol is defined."""
    return _tools.find_symbol(name)


def list_services() -> dict:
    """List all indexed services."""
    return _tools.list_services()


def list_directory(path: str, recursive: bool = False) -> dict:
    """List contents of a directory in the codebase."""
    return _tools.list_directory(path, recursive)


def get_similar_patterns(pattern_type: str, service: str = None) -> dict:
    """Find existing code patterns (retry, error_handling, logging, http_client, validation, auth, caching, event)."""
    return _tools.get_similar_patterns(pattern_type, service)


def get_http_topology() -> dict:
    """Get the full HTTP dependency map between services."""
    return _tools.get_http_topology()


def find_tests(symbol_or_file: str) -> dict:
    """Find test files related to a symbol or source file. Use before planning to know what tests need updating."""
    return _tools.find_tests(symbol_or_file)


# =============================================================================
# DESIGN AGENT
# =============================================================================

# ponytail: ADK requires model string. OpenRouter/multi-provider routing 
# would need a custom BaseLlm implementation. For now, make model configurable
# and use appropriate Gemini model for complexity. Upgrade path: implement
# custom BaseLlm that wraps LLMRouter.

def _create_design_agent(model: str = "gemini-2.5-pro") -> Agent:
    """
    Create the ADK agent with tools.
    
    Uses gemini-2.5-pro by default for design tasks (complex reasoning needed).
    """
    return Agent(
        model=model,
        name="forge_design_agent",
        instruction=DESIGN_AGENT_SYSTEM_PROMPT,
        description="Designs code changes and creates execution plans",
        tools=[
            query_code_graph,
            read_file,
            grep,
            find_symbol,
            list_services,
            list_directory,
            get_similar_patterns,
            get_http_topology,
            find_tests,
        ],
    )


class DesignAgent:
    """
    The Design Agent - creates the execution plan.
    
    Has access to:
    - Code graph (query_code_graph)
    - File system (read_file)
    - Search (grep, find_symbol)
    
    Outputs:
    - plan.json (Plan object)
    
    Model Selection:
    - Uses gemini-2.5-pro by default (reasoning model for complex design)
    - Can be overridden via model parameter
    
    Usage:
        agent = DesignAgent(graph_store, services_path)
        plan = await agent.create_plan(impact_report)
    """
    
    def __init__(self, graph_store, services_path: str, model: str = None):
        """
        Args:
            graph_store: KuzuGraphStore instance
            services_path: Path to the services directory
            model: Optional model override (default: gemini-2.5-pro)
        """
        global _tools
        
        self._store = graph_store
        self._services_path = services_path
        _tools = DesignAgentTools(graph_store, services_path)
        
        # Design tasks need reasoning model
        self._model = model or "gemini-2.5-pro"
        self._agent = _create_design_agent(self._model)
        self._session_service = InMemorySessionService()
        self._runner = None
        self._session = None
    
    async def _ensure_session(self):
        """Ensure we have an active session."""
        if self._session is None:
            self._session = await self._session_service.create_session(
                app_name="forge_design",
                user_id="developer"
            )
            self._runner = Runner(
                agent=self._agent,
                app_name="forge_design",
                session_service=self._session_service
            )
    
    async def _query(self, prompt: str) -> str:
        """Send a query to the agent and get response."""
        await self._ensure_session()
        
        content = types.Content(
            role='user',
            parts=[types.Part(text=prompt)]
        )
        
        import time as _t
        _start = _t.time()
        tool_calls = 0
        logger.info(f"🤖 LLM: {self._agent.model}")
        logger.debug(f"   └─ Prompt ({len(prompt)} chars): {prompt[:150].replace(chr(10),' ')!r}...")
        
        response_text = ""
        async for event in self._runner.run_async(
            user_id="developer",
            session_id=self._session.id,
            new_message=content
        ):
            if hasattr(event, 'tool_calls') and event.tool_calls:
                for tc in event.tool_calls:
                    tool_calls += 1
                    logger.info(f"   └─ TOOL #{tool_calls}: {tc.name}({json.dumps(tc.args or {}, default=str)[:120]})")
            if hasattr(event, 'tool_results') and event.tool_results:
                for tr in event.tool_results:
                    name = tr.name if hasattr(tr, 'name') else 'unknown'
                    result_preview = str(tr.result)[:120] if hasattr(tr, 'result') else str(tr)[:120]
                    logger.debug(f"   └─ TOOL RESULT: {name} → {result_preview}")
            if event.is_final_response() and event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        response_text += part.text
        
        duration_ms = (_t.time() - _start) * 1000
        logger.info(f"   └─ LLM done in {duration_ms:.0f}ms | {tool_calls} tool calls | response={len(response_text)} chars")
        return response_text
    
    async def create_plan(self, impact_report: dict) -> Plan:
        """
        Create an execution plan from an impact report.
        
        Args:
            impact_report: The approved impact report containing:
                - change_request: Original user request
                - report: The layered impact report text
                - report_json: Structured impact data (optional)
                - requirements: Original requirements
                
        Returns:
            Plan object (the ultimatum)
        """
        start_time = time.time()
        logger.info("🧠 Design Agent starting plan creation...")
        
        change_request = impact_report.get("change_request", "")
        report_text = impact_report.get("report", "")
        requirements = impact_report.get("requirements", {})
        
        logger.info(f"   └─ Change request: {change_request[:100]}...")
        logger.info(f"   └─ Target services: {requirements.get('services', [])}")
        logger.info(f"   └─ Target functions: {requirements.get('functions', [])}")
        
        # Build the prompt
        prompt = f"""Create a complete execution plan for the following code change.

## CHANGE REQUEST
{change_request}

## IMPACT REPORT
{report_text[:8000]}

## REQUIREMENTS
Target Services: {requirements.get('services', [])}
Target Functions: {requirements.get('functions', [])}
Description: {requirements.get('description', '')}

## INSTRUCTIONS

1. First, use list_services() to see available services

2. Use list_directory() and grep() to explore the codebase:
   - Use list_directory() on the target service's src/ dir to see EXACTLY which directories exist
   - If you plan to create a new file, verify its parent directory exists first
   - Search for similar functionality that might already exist
   - Search for error handling patterns
   - Search for logging patterns

3. Use read_file() to examine key files mentioned in the impact report

4. Use query_code_graph() to understand relationships:
   - query_type="callers" to find who calls a function
   - query_type="callees" to find what a function calls

5. Based on your exploration, create a plan.json with:
   - Analysis: Summary, reasoning, existing patterns, risks, assumptions
   - Design: Key decisions, coding conventions
   - Contracts: Exact signatures for shared interfaces (with full implementation if new)
   - Execution: Phases with task ordering
   - Tasks: Detailed per-file changes

## OUTPUT FORMAT

Return ONLY valid JSON matching this structure:
```json
{{
  "analysis": {{
    "summary": "One-line summary",
    "reasoning": "Why this approach",
    "existing_patterns": [
      {{"pattern": "...", "location": "...", "reuse": true/false, "rationale": "..."}}
    ],
    "risks": ["risk1", "risk2"],
    "assumptions": ["assumption1"]
  }},
  "design": {{
    "decisions": [
      {{"decision": "Use X pattern", "rationale": "Because Y"}}
    ],
    "conventions": {{
      "naming": "camelCase",
      "error_handling": "Throw errors with context",
      "logging": "Use logger.info/warn/error"
    }}
  }},
  "contracts": {{
    "functionName": {{
      "name": "functionName",
      "type": "function",
      "defined_in": "path/to/file.js",
      "is_new": true,
      "signature": "async function functionName(arg1, arg2) {{ ... }}",
      "implementation": "// Full implementation code here",
      "usage_example": "const result = await functionName(x, y);",
      "used_by": ["file1.js", "file2.js"]
    }}
  }},
  "execution": [
    {{
      "phase": 0,
      "description": "Create new utilities",
      "tasks": ["task-1"],
      "parallel": false,
      "wait_for_completion": true
    }},
    {{
      "phase": 1,
      "description": "Modify service files",
      "tasks": ["task-2", "task-3"],
      "parallel": true,
      "wait_for_completion": true
    }}
  ],
  "tasks": {{
    "task-1": {{
      "id": "task-1",
      "phase": 0,
      "file": "service-name/src/utils/file.js",
      "service": "service-name",
      "language": "javascript",
      "action": "create",
      "description": "Create the utility file",
      "changes": [
        {{
          "location": {{"type": "file_start", "target": "entire file"}},
          "change_type": "add",
          "description": "Create new file",
          "after": "// Full file content"
        }}
      ],
      "depends_on": [],
      "uses_contracts": [],
      "defines_contracts": ["functionName"],
      "context": {{
        "read_files": [],
        "relevant_symbols": []
      }},
      "validation": {{
        "must_compile": true,
        "must_pass_lint": true
      }}
    }}
  }}
}}
```

IMPORTANT:
- For NEW code, include the COMPLETE implementation in contracts
- Be SPECIFIC about file paths - use actual paths from the codebase
- Every change must have exact "after" code
- Tasks must have unique IDs
- BEFORE placing a new file in a directory, use list_directory() to verify that directory exists.
  If the directory does NOT exist, place the new file in an existing directory instead (e.g. src/utils/ or src/ directly).
  Do NOT create tasks that write to non-existent directories — the build will fail.
- When adding INPUT VALIDATION, cover ALL forms of input:
  * URL params (req.params.id, req.params.accountId, etc.) — validate ID formats (UUID, numeric, etc.)
  * Request body fields (req.body.amount, req.body.data, etc.) — validate types and ranges
  * Query string params (req.query.*) — validate presence and format
  Do NOT validate only one input type while ignoring others.
"""
        
        # Query the agent
        response = await self._query(prompt)
        
        # Parse the response — retry once with explicit JSON instruction on failure
        plan = self._parse_plan_response(response, change_request)
        
        if not plan.tasks:
            logger.warning("⚠️ Plan parsed but has no tasks — retrying with explicit JSON instruction")
            retry_prompt = prompt + "\n\nYOUR PREVIOUS RESPONSE DID NOT CONTAIN VALID PLAN JSON.\nReturn ONLY a JSON code block starting with ```json and containing the plan. No other text."
            response2 = await self._query(retry_prompt)
            plan2 = self._parse_plan_response(response2, change_request)
            if plan2.tasks:
                logger.info(f"   └─ Retry succeeded: {len(plan2.tasks)} tasks")
                return plan2
            logger.warning("   └─ Retry also produced no tasks — proceeding with empty plan")
        
        return plan
    
    def _parse_plan_response(self, response: str, change_request: str) -> Plan:
        """Parse the agent's response into a Plan object."""
        # Try to extract JSON
        json_patterns = [
            r'```json\s*([\s\S]*?)\s*```',
            r'```\s*([\s\S]*?)\s*```',
            r'\{[\s\S]*"analysis"[\s\S]*\}',
        ]
        
        plan_data = None
        for pattern in json_patterns:
            match = re.search(pattern, response)
            if match:
                try:
                    json_str = match.group(1) if '```' in pattern else match.group(0)
                    plan_data = json.loads(json_str)
                    logger.info("✅ Successfully parsed plan JSON")
                    break
                except (json.JSONDecodeError, IndexError) as e:
                    logger.debug(f"   └─ JSON parse attempt failed: {e}")
                    continue
        
        if not plan_data:
            # Create minimal plan if parsing failed
            logger.warning("⚠️ Failed to parse plan JSON, creating minimal plan")
            plan = Plan.create(change_request)
            plan.analysis = None
            plan.design = None
            return plan
        
        # Create plan from parsed data
        plan_data["change_request"] = change_request
        plan = Plan.from_dict(plan_data)
        logger.info(f"   └─ Plan created: {len(plan.tasks)} tasks, {len(plan.contracts)} contracts")
        return plan
    
    async def refine_plan(self, plan: Plan, feedback: str) -> Plan:
        """
        Refine a plan based on user feedback.
        
        Args:
            plan: Current plan
            feedback: User's feedback
            
        Returns:
            Refined plan
        """
        prompt = f"""Refine this plan based on the user's feedback.

## CURRENT PLAN
```json
{json.dumps(plan.to_dict(), indent=2)[:6000]}
```

## FEEDBACK
{feedback}

## INSTRUCTIONS
Update the plan to address the feedback. Return the complete updated plan as JSON.
"""
        
        response = await self._query(prompt)
        return self._parse_plan_response(response, plan.change_request)
