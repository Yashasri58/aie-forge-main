from pathlib import Path
from code_graph.graph.store import KuzuGraphStore

db = Path(r'C:\Users\raghavsk\OneDrive - Capgemini\Documents\hsbc_rfp\data\code_graph.kuzu')
store = KuzuGraphStore(db)

# Check edges involving payment-ui
print('Edges FROM payment-ui:')
edges_from = store.query('MATCH (s:Service {service_id: "payment-ui"})-[h:HTTP_CALLS]->(r:Route) RETURN r.service_id AS to_svc, h.via', {})
print(f'  {edges_from}')

print()
print('Edges TO payment-ui:')
edges_to = store.query('MATCH (s:Service)-[h:HTTP_CALLS]->(r:Route {service_id: "payment-ui"}) RETURN s.service_id AS from_svc, h.via', {})
print(f'  {edges_to}')

print()
print('All unique service pairs:')
pairs = store.query('MATCH (s:Service)-[h:HTTP_CALLS]->(r:Route) RETURN DISTINCT s.service_id AS from_svc, r.service_id AS to_svc', {})
for p in pairs:
    print(f'  {p["from_svc"]} -> {p["to_svc"]}')

store.close()
