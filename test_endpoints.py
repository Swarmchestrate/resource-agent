#!/usr/bin/env python3
"""
Simple test to check available endpoints on the RA.
"""

import requests

def test_available_endpoints():
    """Test what endpoints are available on the RA."""
    
    print("🔍 Testing Available Endpoints on RA")
    print("=" * 50)
    
    base_url = "http://localhost:8000"
    
    # Test root endpoint
    try:
        response = requests.get(f"{base_url}/")
        print(f"✅ Root endpoint: {response.status_code}")
        if response.status_code == 200:
            print(f"   Response: {response.json()}")
    except Exception as e:
        print(f"❌ Root endpoint error: {e}")
    
    # Test status endpoint
    try:
        response = requests.get(f"{base_url}/status")
        print(f"✅ Status endpoint: {response.status_code}")
        if response.status_code == 200:
            print(f"   Response: {response.json()}")
    except Exception as e:
        print(f"❌ Status endpoint error: {e}")
    
    # Test health endpoint
    try:
        response = requests.get(f"{base_url}/health")
        print(f"✅ Health endpoint: {response.status_code}")
        if response.status_code == 200:
            print(f"   Response: {response.json()}")
    except Exception as e:
        print(f"❌ Health endpoint error: {e}")
    
    # Test broadcast-ask endpoint
    try:
        response = requests.post(f"{base_url}/broadcast-ask")
        print(f"✅ Broadcast-ask endpoint: {response.status_code}")
        if response.status_code == 200:
            print(f"   Response: {response.json()}")
        elif response.status_code == 404:
            print("   ❌ Endpoint not found - needs RA restart")
        else:
            print(f"   Response: {response.text}")
    except Exception as e:
        print(f"❌ Broadcast-ask endpoint error: {e}")
    
    # Test submit endpoint
    try:
        response = requests.post(f"{base_url}/submit")
        print(f"✅ Submit endpoint: {response.status_code}")
        if response.status_code == 422:  # Expected for missing file
            print("   ✅ Endpoint exists (422 is expected for missing file)")
        else:
            print(f"   Response: {response.text}")
    except Exception as e:
        print(f"❌ Submit endpoint error: {e}")

if __name__ == "__main__":
    test_available_endpoints()
