"""Test the graph explorer endpoints."""

import requests
import json

BASE = "http://localhost:8000"

def test_endpoint(method, path, data=None):
    """Test an endpoint and print result."""
    url = f"{BASE}{path}"
    try:
        if method == "GET":
            resp = requests.get(url, timeout=5)
        else:
            resp = requests.post(url, json=data, timeout=5)
        
        print(f"\n{method} {path}")
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            result = resp.json()
            print(json.dumps(result, indent=2)[:500])
            if len(json.dumps(result)) > 500:
                print("... (truncated)")
        else:
            print(f"Error: {resp.text[:200]}")
    except requests.exceptions.ConnectionError:
        print(f"\n{method} {path}")
        print("ERROR: Server not running. Start with: uvicorn main:app --port 8000")

if __name__ == "__main__":
    print("=" * 60)
    print("GRAPH EXPLORER API TEST")
    print("=" * 60)
    
    # Health check
    test_endpoint("GET", "/health")
    
    # Graph stats
    test_endpoint("GET", "/graph/stats")
    
    # Graph overview (services + HTTP deps)
    test_endpoint("GET", "/graph/overview")
    
    # Expand a service
    test_endpoint("GET", "/graph/service/payment-processor")
    
    # Expand a symbol
    test_endpoint("GET", "/graph/symbol/validatePayment")
