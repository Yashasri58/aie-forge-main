"""
Generate deep code graph visualization showing:
- Services (L1)
- Files (L2)
- Functions (L3)
- HTTP Calls with actual URLs (L4)
"""
import json
import re
from pathlib import Path
import tree_sitter_javascript as tsjs
from tree_sitter import Language, Parser

def parse_js_deep(file_path: str) -> dict:
    """Extract detailed info from JS file using Tree-sitter."""
    JS_LANGUAGE = Language(tsjs.language())
    parser = Parser(JS_LANGUAGE)
    
    with open(file_path, 'rb') as f:
        content = f.read()
    
    tree = parser.parse(content)
    text = content.decode('utf-8')
    
    result = {
        'functions': [],
        'classes': [],
        'requires': [],
        'exports': [],
        'http_calls': []
    }
    
    def extract_text(node):
        return text[node.start_byte:node.end_byte]
    
    def walk(node, depth=0):
        # Function declarations
        if node.type == 'function_declaration':
            name_node = node.child_by_field_name('name')
            params_node = node.child_by_field_name('parameters')
            if name_node:
                result['functions'].append({
                    'name': extract_text(name_node),
                    'params': extract_text(params_node) if params_node else '()',
                    'line': node.start_point[0] + 1,
                    'type': 'function'
                })
        
        # Arrow functions assigned to const
        if node.type == 'lexical_declaration':
            for child in node.children:
                if child.type == 'variable_declarator':
                    name_node = child.child_by_field_name('name')
                    value_node = child.child_by_field_name('value')
                    if name_node and value_node:
                        if value_node.type == 'arrow_function':
                            params = value_node.child_by_field_name('parameters')
                            result['functions'].append({
                                'name': extract_text(name_node),
                                'params': extract_text(params) if params else '()',
                                'line': node.start_point[0] + 1,
                                'type': 'arrow'
                            })
        
        # Class declarations
        if node.type == 'class_declaration':
            name_node = node.child_by_field_name('name')
            if name_node:
                methods = []
                body = node.child_by_field_name('body')
                if body:
                    for method in body.children:
                        if method.type == 'method_definition':
                            method_name = method.child_by_field_name('name')
                            if method_name:
                                methods.append(extract_text(method_name))
                result['classes'].append({
                    'name': extract_text(name_node),
                    'methods': methods,
                    'line': node.start_point[0] + 1
                })
        
        # Require calls
        if node.type == 'call_expression':
            func = node.child_by_field_name('function')
            args = node.child_by_field_name('arguments')
            if func and extract_text(func) == 'require' and args:
                for arg in args.children:
                    if arg.type == 'string':
                        module = extract_text(arg).strip("'\"")
                        result['requires'].append({
                            'module': module,
                            'line': node.start_point[0] + 1
                        })
        
        # HTTP calls (axios.get, axios.post, etc.)
        if node.type == 'call_expression':
            func = node.child_by_field_name('function')
            if func and func.type == 'member_expression':
                obj = func.child_by_field_name('object')
                prop = func.child_by_field_name('property')
                if obj and prop:
                    obj_text = extract_text(obj)
                    prop_text = extract_text(prop)
                    if 'axios' in obj_text.lower() and prop_text in ['get', 'post', 'put', 'delete', 'patch']:
                        args = node.child_by_field_name('arguments')
                        url = ''
                        if args and len(args.children) > 0:
                            url = extract_text(args.children[1]) if len(args.children) > 1 else extract_text(args.children[0])
                        result['http_calls'].append({
                            'method': prop_text.upper(),
                            'url': url[:100],
                            'line': node.start_point[0] + 1
                        })
        
        for child in node.children:
            walk(child, depth + 1)
    
    walk(tree.root_node)
    return result

def generate_deep_graph(services_dir: str, output_dir: str):
    """Generate multi-level graph."""
    
    graph = {
        'levels': {
            'L1_services': [],
            'L2_files': [],
            'L3_functions': [],
            'L4_http_calls': []
        },
        'edges': {
            'service_to_file': [],
            'file_to_function': [],
            'function_to_http': [],
            'service_to_service': []
        },
        'stats': {}
    }
    
    port_to_service = {
        3000: 'gateway-service',
        3001: 'account-service',
        3002: 'payment-processor',
        3003: 'validation-service',
        3004: 'ledger-service',
        3005: 'fx-service',
        3006: 'audit-service'
    }
    
    service_urls = {
        'ACCOUNT_SERVICE': 'account-service',
        'AUDIT_SERVICE': 'audit-service',
        'FX_SERVICE': 'fx-service',
        'PAYMENT_SERVICE': 'payment-processor',
        'LEDGER_SERVICE': 'ledger-service',
        'VALIDATION_SERVICE': 'validation-service'
    }
    
    total_functions = 0
    total_http = 0
    total_files = 0
    
    for service_path in Path(services_dir).iterdir():
        if not service_path.is_dir() or service_path.name.startswith('.'):
            continue
        if service_path.name in ['payment-ui', 'node_modules']:
            continue
        
        service_name = service_path.name
        src_path = service_path / 'src'
        
        if not src_path.exists():
            continue
        
        # L1: Service
        graph['levels']['L1_services'].append({
            'id': service_name,
            'port': port_to_service.get(service_name, 'unknown')
        })
        
        service_functions = []
        service_http = []
        
        for js_file in src_path.rglob('*.js'):
            if 'node_modules' in str(js_file):
                continue
            
            rel_path = js_file.relative_to(service_path)
            file_id = f"{service_name}/{rel_path}"
            total_files += 1
            
            try:
                parsed = parse_js_deep(str(js_file))
                
                # L2: File
                graph['levels']['L2_files'].append({
                    'id': file_id,
                    'service': service_name,
                    'path': str(rel_path),
                    'function_count': len(parsed['functions']),
                    'http_count': len(parsed['http_calls'])
                })
                
                graph['edges']['service_to_file'].append({
                    'from': service_name,
                    'to': file_id
                })
                
                # L3: Functions
                for func in parsed['functions']:
                    func_id = f"{file_id}:{func['name']}"
                    total_functions += 1
                    graph['levels']['L3_functions'].append({
                        'id': func_id,
                        'name': func['name'],
                        'params': func['params'],
                        'line': func['line'],
                        'file': file_id
                    })
                    graph['edges']['file_to_function'].append({
                        'from': file_id,
                        'to': func_id
                    })
                    service_functions.append(func['name'])
                
                # L4: HTTP Calls
                for http in parsed['http_calls']:
                    http_id = f"{file_id}:HTTP:{http['line']}"
                    total_http += 1
                    
                    # Detect target service
                    target = '???'
                    for key, svc in service_urls.items():
                        if key in http['url']:
                            target = svc
                            break
                    
                    graph['levels']['L4_http_calls'].append({
                        'id': http_id,
                        'method': http['method'],
                        'url': http['url'],
                        'line': http['line'],
                        'target_service': target,
                        'source_file': file_id
                    })
                    
                    graph['edges']['function_to_http'].append({
                        'from': file_id,
                        'to': http_id
                    })
                    
                    if target != '???':
                        # Service to service edge
                        edge_exists = any(
                            e['from'] == service_name and e['to'] == target 
                            for e in graph['edges']['service_to_service']
                        )
                        if not edge_exists:
                            graph['edges']['service_to_service'].append({
                                'from': service_name,
                                'to': target,
                                'calls': []
                            })
                        
                        for e in graph['edges']['service_to_service']:
                            if e['from'] == service_name and e['to'] == target:
                                e['calls'].append({
                                    'method': http['method'],
                                    'url': http['url'][:60]
                                })
                    
                    service_http.append(http)
                    
            except Exception as e:
                print(f"Error: {js_file}: {e}")
    
    graph['stats'] = {
        'services': len(graph['levels']['L1_services']),
        'files': total_files,
        'functions': total_functions,
        'http_calls': total_http,
        'service_edges': len(graph['edges']['service_to_service'])
    }
    
    # Save JSON
    with open(Path(output_dir) / 'deep_graph.json', 'w', encoding='utf-8') as f:
        json.dump(graph, f, indent=2)
    
    # Generate detailed DOT
    generate_detailed_dot(graph, output_dir)
    
    # Print summary
    print_graph_summary(graph)
    
    return graph

def generate_detailed_dot(graph: dict, output_dir: str):
    """Generate detailed Graphviz DOT file."""
    
    dot = ['digraph DeepCodeGraph {']
    dot.append('    rankdir=TB;')
    dot.append('    compound=true;')
    dot.append('    node [fontname="Arial"];')
    dot.append('    edge [fontname="Arial", fontsize=10];')
    dot.append('')
    
    colors = {
        'gateway-service': '#4CAF50',
        'payment-processor': '#2196F3',
        'account-service': '#FF9800',
        'validation-service': '#9C27B0',
        'ledger-service': '#795548',
        'fx-service': '#00BCD4',
        'audit-service': '#607D8B'
    }
    
    # Create subgraph for each service
    for svc in graph['levels']['L1_services']:
        svc_id = svc['id']
        color = colors.get(svc_id, '#999999')
        
        dot.append(f'    subgraph cluster_{svc_id.replace("-", "_")} {{')
        dot.append(f'        label="{svc_id}";')
        dot.append(f'        style=filled;')
        dot.append(f'        fillcolor="{color}20";')
        dot.append(f'        color="{color}";')
        
        # Add files as nodes
        for file in graph['levels']['L2_files']:
            if file['service'] == svc_id:
                file_label = file['path'].replace('src/', '').replace('\\', '/')
                func_count = file['function_count']
                http_count = file['http_count']
                
                # Only show important files
                if func_count > 0 or http_count > 0:
                    dot.append(f'        "{file["id"]}" [label="{file_label}\\n({func_count}f, {http_count}h)", shape=note, fillcolor="white", style=filled];')
        
        dot.append('    }')
        dot.append('')
    
    # Add service-to-service edges with call details
    for edge in graph['edges']['service_to_service']:
        call_count = len(edge['calls'])
        methods = set(c['method'] for c in edge['calls'])
        method_str = '/'.join(methods)
        dot.append(f'    "{edge["from"]}" -> "{edge["to"]}" [label="{call_count} calls\\n({method_str})", penwidth=2];')
    
    # Add invisible service nodes for cross-cluster edges
    for svc in graph['levels']['L1_services']:
        dot.append(f'    "{svc["id"]}" [style=invis, width=0, height=0];')
    
    dot.append('}')
    
    dot_path = Path(output_dir) / 'deep_graph.dot'
    with open(dot_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(dot))
    
    print(f"\n[OK] DOT file: {dot_path}")

def print_graph_summary(graph: dict):
    """Print ASCII visualization of the graph."""
    
    print("\n" + "=" * 70)
    print("DEEP CODE GRAPH - 4 LEVELS")
    print("=" * 70)
    
    stats = graph['stats']
    print(f"\nL1 Services:    {stats['services']}")
    print(f"L2 Files:       {stats['files']}")
    print(f"L3 Functions:   {stats['functions']}")
    print(f"L4 HTTP Calls:  {stats['http_calls']}")
    print(f"Service Edges:  {stats['service_edges']}")
    
    print("\n" + "-" * 70)
    print("SERVICE DEPENDENCY GRAPH (with HTTP call details)")
    print("-" * 70)
    
    for edge in graph['edges']['service_to_service']:
        print(f"\n{edge['from']} --> {edge['to']}")
        for call in edge['calls'][:5]:  # Show first 5
            print(f"    {call['method']:6} {call['url']}")
        if len(edge['calls']) > 5:
            print(f"    ... and {len(edge['calls']) - 5} more")
    
    print("\n" + "-" * 70)
    print("FILE DETAILS (Top files by function count)")
    print("-" * 70)
    
    files_sorted = sorted(graph['levels']['L2_files'], 
                         key=lambda x: x['function_count'], reverse=True)
    
    for file in files_sorted[:15]:
        if file['function_count'] > 0:
            print(f"  {file['id'][:50]:50} | {file['function_count']:2}f | {file['http_count']:2}h")
    
    print("\n" + "-" * 70)
    print("FUNCTION SAMPLES (orchestrator.js)")
    print("-" * 70)
    
    for func in graph['levels']['L3_functions']:
        if 'orchestrator' in func['file']:
            print(f"  L{func['line']:3}: {func['name']}{func['params']}")

if __name__ == '__main__':
    base = Path(__file__).parent.parent
    graph = generate_deep_graph(str(base / 'services'), str(base / 'docs'))
    print("\n[OK] Deep graph saved to docs/deep_graph.json")
