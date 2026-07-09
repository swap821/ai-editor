import re
import os
from collections import defaultdict

frontend_dir = 'frontend/src'
backend_api_dir = 'aios/api'

backend_routes = set()
for root, _, files in os.walk(backend_api_dir):
    for file in files:
        if file.endswith('.py'):
            with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                content = f.read()
                matches = re.findall(r'@(?:app|router)\.(?:get|post|put|delete|patch|websocket)\([\'"]([^\'"]+)[\'"]\)', content)
                for match in matches:
                    backend_routes.add(match)

frontend_calls = set()
for root, _, files in os.walk(frontend_dir):
    for file in files:
        if file.endswith(('.js', '.jsx', '.ts', '.tsx')):
            with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                content = f.read()
                matches = re.findall(r'(/api/[^\'"`\?\s]+|/health|/metrics)', content)
                for match in matches:
                    clean_match = re.sub(r'\$\{[^\}]+\}', '{var}', match)
                    frontend_calls.add(clean_match)

matched_routes = set()
for be_route in backend_routes:
    be_regex = re.sub(r'\{[^\}]+\}', '{var}', be_route)
    for fe_call in frontend_calls:
        if be_regex in fe_call or fe_call in be_regex:
            matched_routes.add(be_route)

missing = sorted(list(backend_routes - matched_routes))
groups = defaultdict(list)
for m in missing:
    if m.startswith('/api/v1/'):
        group_name = m.split('/')[3]
        groups[group_name].append(m)
    else:
        groups['root'].append(m)

for g, routes in sorted(groups.items()):
    print(f'\n### {g.capitalize()}')
    for r in routes:
        print(f'- `{r}`')
