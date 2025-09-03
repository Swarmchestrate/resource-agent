#!/usr/bin/env python3
"""
SZTAKI Resource Agent
Uses configuration from Config_ras/Sztaki_RA_config.yaml and SZTAKI_RA_capacity.yaml
Represents SZTAKI cloud infrastructure
"""
import sys
import signal
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.ra_base import ResourceAgent


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    print(f"\nReceived signal {signum}. Shutting down SZTAKI RA...")
    if 'ra' in globals():
        ra.stop()
    sys.exit(0)


if __name__ == "__main__":
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Initialize SZTAKI Resource Agent
        config_file = "Config_ras/Sztaki_RA_config.yaml"
        capacity_file = "Config_ras/SZTAKI_RA_capacity.yaml"
        
        print("=" * 60)
        print("🇭🇺 SZTAKI Resource Agent Starting...")
        print("=" * 60)
        
        ra = ResourceAgent(config_file, capacity_file)
        
        # Display configuration
        status = ra.get_status()
        print(f"RA ID: {status['ra_id']}")
        print(f"Universe ID: {status['universe_id']}")
        print(f"Provider: {status['provider']}")
        print(f"P2P Port: {status['p2p_port']}")
        print(f"API Port: {status['api_port']}")
        print(f"Bootstrap Peers: {status['bootstrap_peers']}")
        print(f"Capacity Loaded: {status['capacity_loaded']}")
        print("-" * 60)
        
        # Start the Resource Agent
        ra.start()
        
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
        if 'ra' in locals():
            ra.stop()
    except Exception as e:
        print(f"Error starting SZTAKI RA: {e}")
        sys.exit(1)
