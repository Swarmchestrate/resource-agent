#!/usr/bin/env python3
"""
Swarmchestrate Client
Submits resource requests to RA network and compiles responses
"""
from email import message
from typing import Any
import yaml
import time
import logging
import sys
import random
from pathlib import Path
from itertools import product
from swchp2pcom import SwchPeer
 
 


class SwarmchestrateClient:
    """Client for submitting requests to RA network via hub"""

    def __init__(self, client_id="job-client"):
        self.client_id = client_id
        self.peer = None
        self.job_responses = {}
        self.job_complete = False

        # Setup minimal logging
        logging.basicConfig(level=logging.WARNING)
        self.logger = logging.getLogger(f"JobClient-{client_id}")
 
    def load_tosca(self, file_path):
        """Load tosca.yaml file with path resolution"""
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
 #   def _register_message_handlers(self):
 #       """Register handlers for different message types"""


    def handle_client_request(self, request_path):
        try:
            with open(request_path, 'r') as f:
                request_data = yaml.safe_load(f)
            
            request_type = request_data.get('request_type', '')
            job_id = request_data.get('job_id', '')
            tosca_path = request_data.get('tosca_path', '')
            hub_host = request_data.get('hub_host', '')
            hub_port = request_data.get('hub_port', 5000)
            gw_RA_id = request_data.get('gw_RA_id', '')
            
            if request_type == 'submit':
                return self.submit_job(tosca_path, hub_host, hub_port, gw_RA_id)
            elif request_type == 'delete':
                return self.delete_job(job_id, hub_host, hub_port, gw_RA_id)
            elif request_type == 'query':
                return self.get_job_status(job_id, hub_host, hub_port, gw_RA_id)
            else:
                print(f"Unknown request type: {request_type}")
                return False
            
        except Exception as e:
            print(f"Failed to handle client request: {e}")
            return False

    def get_job_status(self, job_id, hub_host="", hub_port=5000, gw_RA_id=""):
        """Query job status from RA network via hub"""
        print("Swarmchestrate Job Status Query Client")
        print("=" * 60)
 
        # Initialize P2P client
        self.peer = SwchPeer(
            peer_id=self.client_id,
            enable_rejoin=False,
            metadata={"peer_type": "JOB_CLIENT", "client_id": self.client_id}
        )

        self.peer.register_message_handler("MSG_STATE_INFO", self._handle_query_response)

        
        # Process the message as needed
        # For example, update job status in internal records
        def on_entered():
            print(f"Connected to hub {hub_host}:{hub_port}")

            # Find Gateway RA
            hub_ras = self.peer.find_peers({"peer_type": "RA", "ra_id": gw_RA_id})
            if not hub_ras:
                print("Gateway RA {}", {gw_RA_id}, "} not found!")
                return
 
            hub_ra_id = hub_ras[0]
            print(f"Connected to hub: {hub_ra_id}")

            # Create job status query message
            query_message = {
                "job_id": job_id,
                "client_id": self.client_id,
                "timestamp": time.time(),
                "action": "query_job_status"
            }
 
            print("Sending job status query to the selected RA...")
            self.peer.send(hub_ra_id, "MSG_JOB_STATUS_QUERY", query_message)
            print("Job status query submitted.")
 
        try:
            self.peer.enter(hub_host, hub_port).addCallback(lambda _: on_entered())
            self.peer.start()
 
        except Exception as e:
            self.logger.error(f"Failed to connect: {e}")
            return False
        
    def delete_job(self, job_id, hub_host="", hub_port=5000, gw_RA_id=""):
        """Delete job from RA network via hub"""
        print("Swarmchestrate Job Deletion Client")
        print("=" * 60)
 
        # Initialize P2P client
        self.peer = SwchPeer(
            peer_id=self.client_id,
            enable_rejoin=False,
            metadata={"peer_type": "JOB_CLIENT", "client_id": self.client_id}
        )

        self.peer.register_message_handler("MSG_DELETE_RESPONSE", self._handle_delete_response)
        def on_entered():
            print(f"Connected to hub {hub_host}:{hub_port}")

            # Find Gateway RA
            hub_ras = self.peer.find_peers({"peer_type": "RA", "ra_id": gw_RA_id})
            if not hub_ras:
                print("Gateway RA {}", {gw_RA_id}, "} not found!")
                return
 
            hub_ra_id = hub_ras[0]
            print(f"Connected to hub: {hub_ra_id}")

            # Create job deletion message
            delete_message = {
                "job_id": job_id,
                "client_id": self.client_id,
                "timestamp": time.time(),
                "action": "delete_job"
            }
 
            print("Sending job deletion request to the selected RA...")
            self.peer.send(hub_ra_id, "MSG_JOB_DELETE", delete_message)
            print("Job deletion request submitted.")
 
        try:
            self.peer.enter(hub_host, hub_port).addCallback(lambda _: on_entered())
            self.peer.start()
 
        except Exception as e:
            self.logger.error(f"Failed to connect: {e}")
            return False
        
    def submit_job(self, tosca_path, hub_host="", hub_port=5000, gw_RA_id=""):
        """Submit job to RA network via hub"""
        ask_data = self.load_tosca(tosca_path)

        if not ask_data:
            return False

        print(ask_data)
        print("Swarmchestrate Job Submission Client")
        print("=" * 60)
 

        # Initialize P2P client
        self.peer = SwchPeer(
            peer_id=self.client_id,
            enable_rejoin=False,
            metadata={"peer_type": "JOB_CLIENT", "client_id": self.client_id}
        )
 
        # Register response handler
        self.peer.register_message_handler("MSG_SUBMIT_RESPONSE", self._handle_submit_response)
        #self.peer.register_message_handler("MSG_SWARM_ID_RESPONSE", self._handle_swarm_id_response)

        def debug_swarm_id_handler(*args, **kwargs):
            print("[DEBUG] MSG_SWARM_ID_RESPONSE HANDLER CALLED")
            print("[DEBUG] args:", args)
            print("[DEBUG] kwargs:", kwargs)

        self.peer.register_message_handler("MSG_SWARM_ID_RESPONSE", debug_swarm_id_handler)

        def on_entered():
            print(f"Connected to hub {hub_host}:{hub_port}")

            # Find Gateway RA
            hub_ras = self.peer.find_peers({"peer_type": "RA", "ra_id": gw_RA_id})
            if not hub_ras:
                print("Gateway RA {}", {gw_RA_id}, "} not found!")
                return
 
            hub_ra_id = hub_ras[0]
            print(f"Connected to hub: {hub_ra_id}")

            # Create job submission message
            job_message = {
                "job_id": f"job_{int(time.time())}",
                "client_id": self.client_id,
                "tosca": ask_data,
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
        
    def _handle_submit_response(self, peer_id: str, message: dict[str, Any]):
        """Handle responses from RA"""
        self.logger.info(f"Received job submit response from {peer_id}")
        job_id = message.get('job_id')
        result = message.get('result')
        if result == "failure":
            self.logger.error(f"Job {job_id} submission failed"
            )
            self.peer.leave()
            return
        else:
            self.logger.info(f"Job {job_id} submission succeeded")
    
    def _handle_swarm_id_response(self, peer_id: str, message: dict[str, Any]):
        """Handle SWARM ID responses from RA"""
        self.logger.info(f"Received SWARM ID response from {peer_id}")
        swarm_id = message.get('swarm_id')
        if not swarm_id:
            self.logger.error(f"Job {swarm_id} failed to receive SWARM ID")
            self.peer.leave()
            return
        else:
            self.logger.info(f"Job {swarm_id} received SWARM ID: {swarm_id}")

    def _handle_submit_response(self, peer_id: str, message: dict[str, Any]):
        """Handle responses from RA"""
        self.logger.info(f"Received job submit response from {peer_id}")
        job_id = message.get('job_id')
        result = message.get('result')
        if result == "failure":
            self.logger.error(f"Job {job_id} submission failed"
            )
            self.peer.leave()
            return
        else:
            self.logger.info(f"Job {job_id} submission succeeded")


    def _handle_delete_response(self, peer_id: str, message: dict[str, Any]):
        """Handle responses from RA"""
        self.logger.info(f"Received job delete response from {peer_id}")
        job_id = message.get('job_id')
        result = message.get('result')
        if result == "failure":
            self.logger.error(f"Job {job_id} deletion failed, not found or already deleted"
            )
            self.peer.leave()
            return
        else:
            self.logger.info(f"Job {job_id} deletion succeeded")
    
        # Process the message as needed
        # For example, store job status or resource allocation details

    def _handle_query_response(self, peer_id: str, message: dict[str, Any]):
        """Handle job status query responses from RA"""
        print(f"Received job status response from {peer_id}")
        job_id = message.get('job_id')
        status = message.get('state')
        if status == "unknown":
            print(f"Job {job_id} not found")
        else:
            print(f"Job {job_id} status: {status}")

def main():
    if len(sys.argv) < 2:
        sys.exit("Error: One parameter is required: {Path of client_request.yaml file}")
 
    request_yaml_path = sys.argv[1]
    client = SwarmchestrateClient()
    # Ze: How to implement this? submit a file, which defines the action and contains required information?
    client.handle_client_request(request_yaml_path)
 
if __name__ == "__main__":
    main()


#Reference
"""

request_type:
"
 this will be used to define the request action
 1. submit(tosca_path): submit a job's tosca
 2. delete(job_id): delete a job's deployment
 3. query(job_id): query the state of a job: deploying, deployed, failed, terminated, none
"

job_id:
"
 the job id, this will be used for deleting a job
 or querying the state of a job
"

tosca_path:
"
 the path where the submitted tosca locates
 this will only be used for job submition
"
"""
