import json

with open('docs/deep_graph.json', 'r') as f:
    g = json.load(f)

print('=' * 70)
print('GRAPH DEPTH ANALYSIS')
print('=' * 70)

print('\n## LEVEL 1: SERVICES (7 nodes)')
print('-' * 50)
for s in g['levels']['L1_services']:
    print(f"  {s['id']}")

print('\n## LEVEL 2: FILES (65 nodes) - Sample')
print('-' * 50)
for f in g['levels']['L2_files'][:10]:
    print(f"  {f['path']:40} ({f['function_count']}f)")

print('\n## LEVEL 3: FUNCTIONS (124 nodes) - Sample')
print('-' * 50)
for func in g['levels']['L3_functions'][:15]:
    print(f"  {func['name']:30} @ {func['file'].split('/')[0]}")

print('\n## LEVEL 4: HTTP CALLS (15 detected)')
print('-' * 50)
for h in g['levels']['L4_http_calls']:
    print(f"  {h['method']:6} {h['url'][:50]}")
    print(f"         -> {h['target_service']}")

print('\n## EDGES SUMMARY')
print('-' * 50)
print(f"  Service -> File:     {len(g['edges']['service_to_file']):3} edges")
print(f"  File -> Function:    {len(g['edges']['file_to_function']):3} edges")
print(f"  Function -> HTTP:    {len(g['edges']['function_to_http']):3} edges")
print(f"  Service -> Service:  {len(g['edges']['service_to_service']):3} edges")
print(f"  TOTAL EDGES:         {sum(len(g['edges'][k]) for k in g['edges']):3}")
