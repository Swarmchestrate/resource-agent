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
    """Log startup configuration using the same stream as stage messages."""
    status = ra.get_status()
    ra.logger.info(
        "\n%s\nThe RA { %s } Starting...\n%s\n"
        "RA ID: %s\nUniverse ID: %s\nProvider: %s\n"
        "P2P Port: %s\nAPI Port: %s\nBootstrap Peers: %s\n"
        "Capacity Loaded: %s\n%s",
        "=" * 60, ra.ra_id, "=" * 60,
        status['ra_id'], status['universe_id'], status['provider'],
        status['p2p_port'], status['api_port'], status['bootstrap_peers'],
        status['capacity_loaded'], "-" * 60,
    )

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
        print(f"Error starting ResourceAgent with config_file={config_file} and capacity_file={capacity_file}: {e}")
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
