"""
Simple API Response Time Benchmarking
======================================
Measures API endpoint response times
"""

import requests
import time
import statistics
import json
from datetime import datetime

BASE_URL = "http://localhost:5000"

def measure_api_response():
    """Measure API response times"""
    print("\n" + "="*80)
    print("API RESPONSE TIME BENCHMARKING")
    print("="*80 + "\n")

    results = {
        "phase": "after",
        "timestamp": datetime.now().isoformat(),
        "api_endpoints": {}
    }

    # Test endpoints (public endpoints that don't need auth)
    endpoints = [
        {"name": "login_page", "method": "GET", "url": "/login", "category": "public"},
        {"name": "homepage", "method": "GET", "url": "/", "category": "public"},
    ]

    for endpoint in endpoints:
        print(f"Testing {endpoint['name']} ({endpoint['method']} {endpoint['url']})...")
        times = []
        
        for i in range(20):  # 20 iterations per endpoint
            try:
                start = time.perf_counter()
                response = requests.get(
                    f"{BASE_URL}{endpoint['url']}", 
                    timeout=10
                )
                end = time.perf_counter()
                response_time = (end - start) * 1000  # Convert to ms
                times.append(response_time)
            except Exception as e:
                print(f"  Error: {e}")
                break

        if times:
            result = {
                "name": endpoint['name'],
                "url": endpoint['url'],
                "method": endpoint['method'],
                "mean": statistics.mean(times),
                "median": statistics.median(times),
                "min": min(times),
                "max": max(times),
                "stdev": statistics.stdev(times) if len(times) > 1 else 0,
                "iterations": len(times)
            }
            
            category = endpoint.get('category', 'other')
            if category not in results["api_endpoints"]:
                results["api_endpoints"][category] = {}
            
            results["api_endpoints"][category][endpoint['name']] = result
            
            print(f"  Mean: {result['mean']:.4f}ms | Median: {result['median']:.4f}ms")

    # Save results
    with open('benchmark_results_api_after.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n[OK] Results saved to benchmark_results_api_after.json")
    return results

if __name__ == "__main__":
    try:
        measure_api_response()
    except Exception as e:
        print(f"Error: {e}")
