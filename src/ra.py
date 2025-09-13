#!/usr/bin/env python3
"""
Resource Agent (RA)
Instantiate an RA based on the provided configuration (ra-config.yaml and capacity-config.yaml)
"""
import sys
import signal
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.ra_base import ResourceAgent


def signal_handler(signum, frame):
    global ra
    """Handle shutdown signals gracefully"""
    print(f"\nReceived signal {signum}. Shutting down {ra.ra_id} ...")
    if 'ra' in globals():
        ra.stop()
    sys.exit(0)

def display_ra(ra):
     # Display configuration
    print("=" * 60)
    print("The RA {", ra.ra_id,"} Starting...")
    print("=" * 60)
    status = ra.get_status()
    print(f"RA ID: {status['ra_id']}")
    print(f"Universe ID: {status['universe_id']}")
    print(f"Provider: {status['provider']}")
    print(f"P2P Port: {status['p2p_port']}")
    print(f"API Port: {status['api_port']}")
    print(f"Bootstrap Peers: {status['bootstrap_peers']}")
    print(f"Capacity Loaded: {status['capacity_loaded']}")
    print("-" * 60)

def main(config_file, capacity_file):
    global ra
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Initialize Resource Agent
        ra = ResourceAgent(config_file, capacity_file)
        display_ra(ra)
        ra.start()
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
        if 'ra' in locals():
            ra.stop()
    except Exception as e:
        print(f"Error starting {ra.ra_id}: {e}")
        sys.exit(1)

if __name__ == "__main__":
    script_dir = Path(__file__).parent

    # Use command-line arguments if provided, otherwise use default files
    config_file = sys.argv[1] if len(sys.argv) > 1 else script_dir.parent / "config" / "ra-config.yaml"
    capacity_file = sys.argv[2] if len(sys.argv) > 2 else script_dir.parent / "config" / "capacity-config.yaml"

    # Check if default files exist when not provided as arguments
    if len(sys.argv) <= 1 and not config_file.exists():
        print(f"Error: Default RA config file not found at {config_file}")
        sys.exit(1)
    if len(sys.argv) <= 2 and not capacity_file.exists():
        print(f"Error: Default capacity config file not found at {capacity_file}")
        sys.exit(1)
    
    main(config_file, capacity_file)