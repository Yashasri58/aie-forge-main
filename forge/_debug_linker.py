import re
from pathlib import Path

# Current pattern from linker.py
pattern_current = re.compile(r"fetch\s*\(\s*['\"`]([^'\"`]+)['\"`]", re.IGNORECASE)

def extract_path_from_url(url):
    """Copy of _extract_path_from_url from linker.py"""
    if not url:
        return None

    # Handle template literals: ${BASE_URL}/api/...
    url = re.sub(r"\$\{[^}]+\}", "", url)

    # Handle variable interpolation: + baseUrl + '/api/...'
    # Just extract the literal path portion
    if "/api/" in url:
        idx = url.find("/api/")
        return url[idx:]

    # If it starts with /, treat it as a path
    if url.startswith("/"):
        return url

    # Try to extract path from full URL
    path_match = re.search(r"https?://[^/]+(/[^'\"` ]+)", url)
    if path_match:
        return path_match.group(1)

    return None

# Test URLs found in client files
test_urls = [
    '${AUDIT_SERVICE_URL}/events',
    '${AUDIT_SERVICE_URL}/events/payment/${paymentId}/trail',
    '${FX_SERVICE_URL}/rates/${fromCurrency}/${toCurrency}',
    '${FX_SERVICE_URL}/convert',
    '${FX_SERVICE_URL}/rates',
    '${LEDGER_SERVICE_URL}/entries',
    '${LEDGER_SERVICE_URL}/entries/payment/${paymentId}',
    '${LEDGER_SERVICE_URL}/entries/payment/${paymentId}/summary',
]

print('URL extraction results:')
for url in test_urls:
    path = extract_path_from_url(url)
    print(f'  {url[:50]:50} -> {path}')
