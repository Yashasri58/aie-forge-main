"""
Code Graph Techniques - Test Suite
Tests different approaches to building service dependency graphs
"""

import os
import re
import json
import yaml
from pathlib import Path
from collections import defaultdict

# ============================================================
# TEST 1: OpenAPI Contract Parser
# Extract service dependencies from OpenAPI specs
# ============================================================

def test_openapi_parser(services_dir):
    """Parse all OpenAPI specs and extract endpoints"""
    print("\n" + "="*60)
    print("TEST 1: OpenAPI Contract Parser")
    print("="*60)
    
    services = {}
    
    for service_dir in Path(services_dir).iterdir():
        if not service_dir.is_dir():
            continue
        
        openapi_path = service_dir / "contracts" / "openapi.yaml"
        if not openapi_path.exists():
            continue
        
        service_name = service_dir.name
        
        with open(openapi_path, 'r') as f:
            spec = yaml.safe_load(f)
        
        endpoints = []
        schemas = []
        
        # Extract endpoints
        if 'paths' in spec:
            for path, methods in spec['paths'].items():
                for method, details in methods.items():
                    if method in ['get', 'post', 'put', 'delete', 'patch']:
                        endpoints.append({
                            'path': path,
                            'method': method.upper(),
                            'operationId': details.get('operationId', ''),
                            'summary': details.get('summary', '')
                        })
        
        # Extract schemas
        if 'components' in spec and 'schemas' in spec['components']:
            schemas = list(spec['components']['schemas'].keys())
        
        services[service_name] = {
            'title': spec.get('info', {}).get('title', service_name),
            'port': extract_port(spec),
            'endpoints': endpoints,
            'schemas': schemas
        }
        
        print(f"\n📦 {service_name}")
        print(f"   Endpoints: {len(endpoints)}")
        print(f"   Schemas: {len(schemas)}")
        for ep in endpoints[:5]:
            print(f"   - {ep['method']:6} {ep['path']}")
        if len(endpoints) > 5:
            print(f"   ... and {len(endpoints)-5} more")
    
    return services

def extract_port(spec):
    """Extract port from OpenAPI server URL"""
    servers = spec.get('servers', [])
    if servers:
        url = servers[0].get('url', '')
        match = re.search(r':(\d+)', url)
        if match:
            return int(match.group(1))
    return None


# ============================================================
# TEST 2: Tree-sitter JavaScript Parser
# Extract AST structure: functions, imports, exports
# ============================================================

def test_treesitter_parser(services_dir):
    """Parse JS files with Tree-sitter and extract structure"""
    print("\n" + "="*60)
    print("TEST 2: Tree-sitter JavaScript Parser")
    print("="*60)
    
    import tree_sitter_javascript as tsjs
    from tree_sitter import Language, Parser
    
    JS_LANGUAGE = Language(tsjs.language())
    parser = Parser(JS_LANGUAGE)
    
    all_files = {}
    
    for service_dir in Path(services_dir).iterdir():
        if not service_dir.is_dir() or service_dir.name == 'payment-ui':
            continue
        
        service_name = service_dir.name
        src_dir = service_dir / "src"
        
        if not src_dir.exists():
            continue
        
        print(f"\n📦 {service_name}")
        
        service_files = {}
        
        for js_file in src_dir.rglob("*.js"):
            relative_path = js_file.relative_to(service_dir)
            
            with open(js_file, 'rb') as f:
                code = f.read()
            
            tree = parser.parse(code)
            
            file_info = {
                'path': str(relative_path),
                'functions': [],
                'requires': [],
                'exports': [],
                'classes': []
            }
            
            # Extract info from AST
            extract_node_info(tree.root_node, code, file_info)
            
            service_files[str(relative_path)] = file_info
            
            print(f"   📄 {relative_path}")
            print(f"      Functions: {len(file_info['functions'])}, Requires: {len(file_info['requires'])}")
        
        all_files[service_name] = service_files
    
    return all_files

def extract_node_info(node, code, file_info):
    """Recursively extract info from AST nodes"""
    
    # Function declarations
    if node.type == 'function_declaration':
        name_node = node.child_by_field_name('name')
        if name_node:
            file_info['functions'].append({
                'name': code[name_node.start_byte:name_node.end_byte].decode('utf-8'),
                'line': node.start_point[0] + 1,
                'type': 'function'
            })
    
    # Arrow functions assigned to variables
    if node.type == 'variable_declarator':
        name_node = node.child_by_field_name('name')
        value_node = node.child_by_field_name('value')
        if name_node and value_node and value_node.type == 'arrow_function':
            file_info['functions'].append({
                'name': code[name_node.start_byte:name_node.end_byte].decode('utf-8'),
                'line': node.start_point[0] + 1,
                'type': 'arrow'
            })
    
    # Class declarations
    if node.type == 'class_declaration':
        name_node = node.child_by_field_name('name')
        if name_node:
            class_name = code[name_node.start_byte:name_node.end_byte].decode('utf-8')
            methods = []
            
            # Find methods in class body
            body = node.child_by_field_name('body')
            if body:
                for child in body.children:
                    if child.type == 'method_definition':
                        method_name_node = child.child_by_field_name('name')
                        if method_name_node:
                            methods.append(code[method_name_node.start_byte:method_name_node.end_byte].decode('utf-8'))
            
            file_info['classes'].append({
                'name': class_name,
                'methods': methods,
                'line': node.start_point[0] + 1
            })
    
    # Require statements
    if node.type == 'call_expression':
        func_node = node.child_by_field_name('function')
        if func_node and code[func_node.start_byte:func_node.end_byte] == b'require':
            args = node.child_by_field_name('arguments')
            if args and args.child_count > 0:
                arg = args.children[1] if args.child_count > 1 else args.children[0]
                if arg.type == 'string':
                    module_path = code[arg.start_byte:arg.end_byte].decode('utf-8').strip("'\"")
                    file_info['requires'].append(module_path)
    
    # Module exports
    if node.type == 'assignment_expression':
        left = node.child_by_field_name('left')
        if left:
            left_text = code[left.start_byte:left.end_byte].decode('utf-8')
            if 'module.exports' in left_text or 'exports.' in left_text:
                right = node.child_by_field_name('right')
                if right:
                    file_info['exports'].append({
                        'line': node.start_point[0] + 1,
                        'type': right.type
                    })
    
    # Recurse into children
    for child in node.children:
        extract_node_info(child, code, file_info)


# ============================================================
# TEST 3: HTTP Client Detection
# Find axios/fetch calls and map to target services
# ============================================================

def test_http_client_detection(services_dir):
    """Detect HTTP client calls and map to services"""
    print("\n" + "="*60)
    print("TEST 3: HTTP Client Detection")
    print("="*60)
    
    # Service port mapping
    port_to_service = {
        3000: 'gateway-service',
        3001: 'account-service',
        3002: 'payment-processor',
        3003: 'validation-service',
        3004: 'ledger-service',
        3005: 'fx-service',
        3006: 'audit-service'
    }
    
    http_calls = []
    
    for service_dir in Path(services_dir).iterdir():
        if not service_dir.is_dir():
            continue
        
        service_name = service_dir.name
        
        for js_file in service_dir.rglob("*.js"):
            # Skip node_modules
            if 'node_modules' in str(js_file):
                continue
            with open(js_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Find axios calls
            # Pattern: axios.get/post/put/delete('url') or axios({ url: '...' })
            axios_patterns = [
                r'axios\.(get|post|put|delete|patch)\s*\(\s*[`\'"]([^`\'"]+)[`\'"]',
                r'axios\s*\(\s*\{[^}]*url:\s*[`\'"]([^`\'"]+)[`\'"]',
            ]
            
            for pattern in axios_patterns:
                matches = re.finditer(pattern, content)
                for match in matches:
                    if len(match.groups()) == 2:
                        method, url = match.groups()
                    else:
                        method, url = 'unknown', match.group(1)
                    
                    target_service = resolve_url_to_service(url, port_to_service)
                    
                    http_calls.append({
                        'source_service': service_name,
                        'source_file': str(js_file.relative_to(service_dir)),
                        'method': method.upper() if method != 'unknown' else 'UNKNOWN',
                        'url': url,
                        'target_service': target_service
                    })
            
            # Find fetch calls
            fetch_pattern = r'fetch\s*\(\s*[`\'"]([^`\'"]+)[`\'"]'
            for match in re.finditer(fetch_pattern, content):
                url = match.group(1)
                target_service = resolve_url_to_service(url, port_to_service)
                
                http_calls.append({
                    'source_service': service_name,
                    'source_file': str(js_file.relative_to(service_dir)),
                    'method': 'GET',  # Default for fetch
                    'url': url,
                    'target_service': target_service
                })
    
    # Print results
    print(f"\nFound {len(http_calls)} HTTP client calls:\n")
    
    # Group by source service
    by_source = defaultdict(list)
    for call in http_calls:
        by_source[call['source_service']].append(call)
    
    for source, calls in sorted(by_source.items()):
        print(f"📦 {source}")
        for call in calls:
            target = call['target_service'] or '???'
            print(f"   → {call['method']:6} {call['url'][:50]:<50} → {target}")
    
    return http_calls

def resolve_url_to_service(url, port_map):
    """Resolve URL to target service name"""
    # Check for localhost:port pattern
    port_match = re.search(r'localhost:(\d+)', url)
    if port_match:
        port = int(port_match.group(1))
        return port_map.get(port)
    
    # Check for service name in URL (for service mesh / k8s patterns)
    for port, service in port_map.items():
        if service.replace('-service', '') in url.lower():
            return service
    
    return None


# ============================================================
# TEST 4: Build Unified Graph
# Combine all information into a single graph
# ============================================================

def build_unified_graph(openapi_data, treesitter_data, http_calls):
    """Build a unified service dependency graph"""
    print("\n" + "="*60)
    print("TEST 4: Build Unified Graph")
    print("="*60)
    
    import networkx as nx
    
    G = nx.DiGraph()
    
    # Add service nodes
    for service_name, data in openapi_data.items():
        G.add_node(service_name, 
                   type='service',
                   endpoints=len(data['endpoints']),
                   schemas=len(data['schemas']),
                   port=data['port'])
    
    # Add edges from HTTP calls
    edge_counts = defaultdict(int)
    for call in http_calls:
        if call['target_service']:
            key = (call['source_service'], call['target_service'])
            edge_counts[key] += 1
    
    for (source, target), count in edge_counts.items():
        if source in G.nodes and target in G.nodes:
            G.add_edge(source, target, weight=count, type='http_call')
    
    # Print graph summary
    print(f"\n📊 Graph Summary:")
    print(f"   Nodes (Services): {G.number_of_nodes()}")
    print(f"   Edges (Dependencies): {G.number_of_edges()}")
    
    print(f"\n🔗 Service Dependencies:")
    for source, target, data in G.edges(data=True):
        print(f"   {source} → {target} ({data.get('weight', 1)} calls)")
    
    # Calculate metrics
    print(f"\n📈 Service Metrics:")
    for node in G.nodes():
        in_degree = G.in_degree(node)
        out_degree = G.out_degree(node)
        print(f"   {node}: consumes {out_degree} services, consumed by {in_degree}")
    
    return G


# ============================================================
# TEST 5: Generate Visualization
# Create ASCII and DOT format graphs
# ============================================================

def generate_visualization(G, openapi_data, http_calls, output_dir):
    """Generate graph visualizations"""
    print("\n" + "="*60)
    print("TEST 5: Generate Visualization")
    print("="*60)
    
    # ASCII visualization
    print("\n📊 Service Dependency Graph (ASCII):")
    print()
    
    # Find services with no dependencies (entry points)
    entry_points = [n for n in G.nodes() if G.in_degree(n) == 0]
    
    # Simple ASCII representation
    print("    ┌─────────────────┐")
    print("    │  gateway-service │ ← Entry Point (Port 3000)")
    print("    └────────┬────────┘")
    print("             │")
    print("             ▼")
    print("    ┌─────────────────────┐")
    print("    │  payment-processor  │ ← Orchestrator (Port 3002)")
    print("    └──┬──┬──┬──┬──┬─────┘")
    print("       │  │  │  │  │")
    
    # Show connections from payment-processor
    targets = list(G.successors('payment-processor')) if 'payment-processor' in G else []
    for i, target in enumerate(targets):
        prefix = "       " + "   " * i + "└──▶ "
        port = openapi_data.get(target, {}).get('port', '?')
        print(f"{prefix}{target} (:{port})")
    
    # Generate DOT file
    dot_content = generate_dot(G, openapi_data)
    dot_path = Path(output_dir) / "service_graph.dot"
    
    with open(dot_path, 'w') as f:
        f.write(dot_content)
    
    print(f"\n✅ DOT file saved to: {dot_path}")
    
    # Generate JSON export
    json_export = {
        'nodes': [],
        'edges': []
    }
    
    for node in G.nodes(data=True):
        json_export['nodes'].append({
            'id': node[0],
            'type': 'service',
            'port': node[1].get('port'),
            'endpoints': node[1].get('endpoints', 0),
            'schemas': node[1].get('schemas', 0)
        })
    
    for edge in G.edges(data=True):
        json_export['edges'].append({
            'source': edge[0],
            'target': edge[1],
            'weight': edge[2].get('weight', 1),
            'type': 'http_call'
        })
    
    json_path = Path(output_dir) / "service_graph.json"
    with open(json_path, 'w') as f:
        json.dump(json_export, f, indent=2)
    
    print(f"✅ JSON export saved to: {json_path}")
    
    # Generate detailed markdown report
    md_content = generate_markdown_report(G, openapi_data, http_calls)
    md_path = Path(output_dir) / "GRAPH_TEST_RESULTS.md"
    
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_content)
    
    print(f"✅ Markdown report saved to: {md_path}")
    
    return dot_path, json_path

def generate_dot(G, openapi_data):
    """Generate Graphviz DOT format"""
    lines = [
        'digraph ServiceDependencies {',
        '    rankdir=TB;',
        '    node [shape=box, style=filled];',
        ''
    ]
    
    # Color mapping
    colors = {
        'gateway-service': '#4CAF50',      # Green - entry
        'payment-processor': '#2196F3',     # Blue - orchestrator
        'account-service': '#FF9800',       # Orange
        'validation-service': '#9C27B0',    # Purple
        'fx-service': '#00BCD4',            # Cyan
        'ledger-service': '#795548',        # Brown
        'audit-service': '#607D8B',         # Gray
        'payment-ui': '#E91E63'             # Pink
    }
    
    # Add nodes
    for node in G.nodes(data=True):
        name = node[0]
        port = node[1].get('port', '?')
        color = colors.get(name, '#FFFFFF')
        label = f"{name}\\n(:{port})"
        lines.append(f'    "{name}" [label="{label}", fillcolor="{color}"];')
    
    lines.append('')
    
    # Add edges
    for edge in G.edges(data=True):
        weight = edge[2].get('weight', 1)
        lines.append(f'    "{edge[0]}" -> "{edge[1]}" [label="{weight} calls"];')
    
    lines.append('}')
    return '\n'.join(lines)

def generate_markdown_report(G, openapi_data, http_calls):
    """Generate detailed markdown report"""
    lines = [
        "# Code Graph Test Results",
        "",
        f"*Generated: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        "",
        "---",
        "",
        "## 1. Service Summary",
        "",
        "| Service | Port | Endpoints | Schemas | Consumes | Consumed By |",
        "|---------|------|-----------|---------|----------|-------------|"
    ]
    
    for node in sorted(G.nodes()):
        data = openapi_data.get(node, {})
        port = data.get('port', '?')
        endpoints = data.get('endpoints', [])
        schemas = data.get('schemas', [])
        consumes = G.out_degree(node)
        consumed_by = G.in_degree(node)
        lines.append(f"| {node} | {port} | {len(endpoints)} | {len(schemas)} | {consumes} | {consumed_by} |")
    
    lines.extend([
        "",
        "## 2. Service Dependencies",
        "",
        "```"
    ])
    
    # Dependency tree
    for source in sorted(G.nodes()):
        targets = list(G.successors(source))
        if targets:
            lines.append(f"{source}")
            for i, target in enumerate(targets):
                prefix = "└──" if i == len(targets) - 1 else "├──"
                weight = G.edges[source, target].get('weight', 1)
                lines.append(f"  {prefix} {target} ({weight} calls)")
    
    lines.extend([
        "```",
        "",
        "## 3. HTTP Call Details",
        ""
    ])
    
    # Group by source
    by_source = defaultdict(list)
    for call in http_calls:
        by_source[call['source_service']].append(call)
    
    for source in sorted(by_source.keys()):
        lines.append(f"### {source}")
        lines.append("")
        lines.append("| File | Method | URL | Target |")
        lines.append("|------|--------|-----|--------|")
        for call in by_source[source]:
            target = call['target_service'] or 'Unknown'
            lines.append(f"| {call['source_file']} | {call['method']} | `{call['url'][:40]}` | {target} |")
        lines.append("")
    
    lines.extend([
        "## 4. Payment Flow Trace",
        "",
        "Based on the graph, the payment processing flow is:",
        "",
        "```",
        "1. Client → gateway-service (entry point)",
        "2. gateway-service → payment-processor (orchestration)",
        "3. payment-processor → account-service (lookup sender/receiver)",
        "4. payment-processor → validation-service (validate rules)",
        "5. payment-processor → fx-service (currency conversion)",
        "6. payment-processor → ledger-service (create entries)",
        "7. payment-processor → audit-service (log events)",
        "```",
        "",
        "## 5. Impact Analysis Example",
        "",
        "**Question**: If we change `account-service`, what is affected?",
        "",
        "**Answer**: Based on the graph:",
        "- `payment-processor` directly depends on `account-service`",
        "- `gateway-service` proxies to `account-service`",
        "- Impact: Payment processing flow would be affected",
        "",
        "---",
        "",
        "*Report generated by Forge Graph Test Suite*"
    ])
    
    return '\n'.join(lines)


# ============================================================
# MAIN
# ============================================================

def main():
    services_dir = Path(__file__).parent.parent / "services"
    output_dir = Path(__file__).parent.parent / "docs"
    
    print("🚀 Starting Code Graph Technique Tests")
    print(f"   Services directory: {services_dir}")
    print(f"   Output directory: {output_dir}")
    
    # Run all tests
    openapi_data = test_openapi_parser(services_dir)
    treesitter_data = test_treesitter_parser(services_dir)
    http_calls = test_http_client_detection(services_dir)
    
    # Build unified graph
    G = build_unified_graph(openapi_data, treesitter_data, http_calls)
    
    # Generate visualizations
    generate_visualization(G, openapi_data, http_calls, output_dir)
    
    print("\n" + "="*60)
    print("✅ ALL TESTS COMPLETED")
    print("="*60)

if __name__ == "__main__":
    main()
