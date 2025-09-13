#!/usr/bin/env python3
"""
Job Submission Client
Submits resource requests to RA network and compiles responses
"""
import yaml
import time
import logging
import sys
import random
from pathlib import Path
from itertools import product
from swchp2pcom import SwchPeer
 
 
class JobSubmissionClient:
    """Client for submitting jobs and collecting resource offers"""

    def __init__(self, client_id="job-client"):
        self.client_id = client_id
        self.peer = None
        self.job_responses = {}
        self.job_complete = False
 

        # Setup minimal logging
        logging.basicConfig(level=logging.WARNING)
        self.logger = logging.getLogger(f"JobClient-{client_id}")
 
    def load_ask_yaml(self, file_path):
        """Load ask.yaml file with path resolution"""
        try:
            path = Path(file_path)
           
            # Resolve relative paths when running from src directory
            if Path.cwd().name == 'src' and not path.is_absolute() and not str(file_path).startswith('../'):
                path = Path("../") / file_path
           
            if not path.exists():
                print(f"File not found: {path.resolve()}")
                return None
           
            with open(path, 'r') as f:
                yaml_data = yaml.safe_load(f)
               
            if yaml_data:
                print(f"Loaded {len(yaml_data)} resource requests from ask.yaml")
                # Generate resource summary
                resource_details = []
                for name, data in yaml_data.items():
                    count = data.get('count', 1) if isinstance(data, dict) else 1
                    capabilities = data.get('capabilities', {}) if isinstance(data, dict) else {}
                    category_count = len(capabilities)
                    resource_details.append(f"{name}(×{count}, {category_count} requirements)")
                print(f"📋 Resources: {', '.join(resource_details)}")
            else:
                print("YAML data is None or empty")
            
            return yaml_data
                
            
        except Exception as e:
            print(f"Failed to load ask.yaml: {e}")
            return None
 
    def submit_job(self, ask_yaml_path, hub_host="", hub_port=5000):
        """Submit job to RA network via hub"""
        ask_data = self.load_ask_yaml(ask_yaml_path)
        if not ask_data:
            return False
 
        print("Swarmchestrate Job Submission Client")
        print("=" * 60)
 

        # Initialize P2P client
        self.peer = SwchPeer(
            peer_id=self.client_id,
            enable_rejoin=False,
            metadata={"peer_type": "JOB_CLIENT", "client_id": self.client_id}
        )
 
        # Register response handler
#        self.peer.register_message_handler("MSG_RESOURCE_RESPONSE", self._handle_resource_response)
 
        def on_entered():
            print(f"Connected to hub {hub_host}:{hub_port}")

            # Find Gateway RA
            hub_ras = self.peer.find_peers({"peer_type": "RA", "ra_id": "Aws-UK-RA"})
            if not hub_ras:
                print("Hub RA (Aws-UK-RA) not found!")
                return
 
            hub_ra_id = hub_ras[0]
            print(f"Connected to hub: {hub_ra_id}")

            # Create job submission message
            job_message = {
                "job_id": f"job_{int(time.time())}",
                "client_id": self.client_id,
                "ask_yaml": ask_data,
                "timestamp": time.time(),
                "action": "broadcast_job"
            }
 
            print("Sending job to the selected RA...")
            self.peer.send(hub_ra_id, "MSG_JOB_SUBMIT", job_message)
            print("Job submitted.")
 
        try:
            self.peer.enter(hub_host, hub_port).addCallback(lambda _: on_entered())
            self.peer.start()
 
        except Exception as e:
            self.logger.error(f"Failed to connect: {e}")
            return False
 
def main():
    if len(sys.argv) < 4:
        sys.exit("Error: Three parameters are required: {Path of ask.yaml file, IP of Gateway RA, port}")
 
    ask_yaml_path = sys.argv[1]
    hub_host = sys.argv[2]          # IP of RA to which job is submitted
    hub_port = int(sys.argv[3])     # Port of RA to which job is submitted
 
    client = JobSubmissionClient()
    client.submit_job(ask_yaml_path, hub_host, hub_port)
 
 
if __name__ == "__main__":
    main()
