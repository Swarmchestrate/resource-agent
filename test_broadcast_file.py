#!/usr/bin/env python3
"""
Test script to directly broadcast ask.yaml requirements to the RA system.
This script uses the new /broadcast-ask endpoint that bypasses TOSCA validation.
"""

import requests
import json
import os
import sys

def test_direct_ask_broadcast():
    """Test direct broadcasting of ask.yaml requirements using the new endpoint."""
    
    print("🧪 Testing Direct ask.yaml Broadcasting (No TOSCA Validation)")
    print("=" * 80)
    
    # Check if RA is running
    try:
        response = requests.get("http://localhost:8000/status")
        if response.status_code == 200:
            ra_status = response.json()
            print("✅ RA Status:", response.status_code)
            print("📊 Response:", ra_status)
        else:
            print("❌ RA not responding properly:", response.status_code)
            return
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to RA. Make sure it's running on localhost:8000")
        return
    
    print(f"\n📡 Using new /broadcast-ask endpoint (bypasses TOSCA validation)")
    
    try:
        # Use the new direct broadcast endpoint
        response = requests.post("http://localhost:8000/broadcast-ask")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ ask.yaml requirements broadcasted successfully!")
            print(f"📋 RA ID: {result.get('ra_id', 'N/A')}")
            print(f"📡 Status: {result.get('status', 'N/A')}")
            print(f"📄 Message: {result.get('message', 'N/A')}")
            
            # Check broadcast info
            if 'broadcast_info' in result:
                broadcast_info = result['broadcast_info']
                print(f"🌐 Broadcast Status: {broadcast_info.get('status', 'N/A')}")
                print(f"📡 Broadcast Message: {broadcast_info.get('message', 'N/A')}")
                print(f"🆔 Reservation ID: {broadcast_info.get('reservation_id', 'N/A')}")
            
            # Check resource requirements
            if 'resource_requirements' in result:
                req_info = result['resource_requirements']
                print(f"📊 Total VMs: {req_info.get('total_vms', 'N/A')}")
                print(f"📋 Source: {req_info.get('source', 'N/A')}")
                
                # Show VM details
                vm_requirements = req_info.get('vm_requirements', [])
                if vm_requirements:
                    print(f"\n📋 VM Requirements from ask.yaml:")
                    for vm in vm_requirements:
                        vm_name = vm.get('vm_name', 'Unknown')
                        count = vm.get('count', 0)
                        requirements = vm.get('requirements', {})
                        
                        print(f"  • {vm_name}: {count} VMs")
                        
                        # Show host requirements
                        host_req = requirements.get('host', {}).get('properties', {})
                        if host_req:
                            cpu = host_req.get('num-cpus', 'N/A')
                            mem = host_req.get('mem-size', 'N/A')
                            disk = host_req.get('disk-size', 'N/A')
                            print(f"    - Host: CPU={cpu}, Memory={mem}, Disk={disk}")
                        
                        # Show OS requirements
                        os_req = requirements.get('os', {}).get('properties', {})
                        if os_req:
                            os_type = os_req.get('type', 'N/A')
                            distro = os_req.get('distribution', 'N/A')
                            version = os_req.get('version', 'N/A')
                            print(f"    - OS: {os_type} {distro} {version}")
            
            print("\n🔍 Checking broadcast details...")
            print("💡 The RA should now be broadcasting resource requirements from ask.yaml to the P2P network")
            print("💡 Check the RA logs to see the broadcasting process in action")
            
        else:
            print(f"❌ Failed to broadcast ask.yaml: {response.status_code}")
            print(f"📄 Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Error broadcasting ask.yaml: {e}")
        return
    
    print("\n🎯 Direct ask.yaml broadcasting test completed!")
    print("💡 If successful, your RA should have broadcasted the exact requirements from ask.yaml to Aws-RA2")

if __name__ == "__main__":
    test_direct_ask_broadcast()


