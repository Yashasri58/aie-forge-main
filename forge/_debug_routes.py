import re
from pathlib import Path

route_pattern = re.compile(
    r"(?:app|router)\.(get|post|put|patch|delete)\s*\(\s*['\"]([^'\"]+)['\"]",
    re.IGNORECASE
)

services = [
    ('audit-service', r'C:\Users\raghavsk\OneDrive - Capgemini\Documents\hsbc_rfp\services\audit-service'),
    ('fx-service', r'C:\Users\raghavsk\OneDrive - Capgemini\Documents\hsbc_rfp\services\fx-service'),
    ('ledger-service', r'C:\Users\raghavsk\OneDrive - Capgemini\Documents\hsbc_rfp\services\ledger-service'),
    ('payment-ui', r'C:\Users\raghavsk\OneDrive - Capgemini\Documents\hsbc_rfp\services\payment-ui'),
]

for name, root in services:
    print(f'\n=== {name} ===')
    root_path = Path(root)
    routes_found = []
    
    for js_file in root_path.rglob("*.js"):
        if "node_modules" in js_file.parts:
            continue
        try:
            source = js_file.read_text(encoding="utf-8", errors="ignore")
        except IOError:
            continue
        
        for match in route_pattern.finditer(source):
            method = match.group(1).upper()
            path = match.group(2)
            rel = js_file.relative_to(root_path)
            routes_found.append((method, path, str(rel)))
    
    if routes_found:
        for method, path, file in routes_found[:10]:  # First 10
            print(f'  {method:6} {path:40} ({file})')
        if len(routes_found) > 10:
            print(f'  ... and {len(routes_found) - 10} more')
    else:
        print('  No routes found!')
