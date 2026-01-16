"""
Base Resource Agent (RA) implementation
Handles P2P communication and resource matching
"""
#import
# unused imports removed

            
#import random

import os as _os
import shutil as _shutil
import json
import logging
import yaml
import time

from http.client import responses
from typing import Dict, Any, Optional, List
from pathlib import Path
from itertools import product

# Swarmchestrate library imports
from swchp2pcom import SwchPeer
from cluster_builder import Swarmchestrate
from sardou import Sardou

# TOSCA evaluation functions
from capability_evaluator import can_fulfill_requirement, get_matching_instances
from offer_evaluator import OfferEvaluator

# RA utility functions
from dotenv import load_dotenv
from utility import dict_to_yaml as write_yaml
from utility import extract_qos_priorities as get_qos_priorities
from utility import generate_tosca_configmap as write_tosca_configmap
from utility import generate_swarm_configmap as write_swarm_configmap   







class ResourceAgent:
    """Resource Agent for evaluating and responding to resource requests"""

    def __init__(self, config_file: str, capacity_file: Optional[str] = None):
        """Initialize Resource Agent with configuration files"""
        self.config_file = config_file
        self.capacity_file = capacity_file
        self.config = self._load_config(config_file)
        self.capacity = self._load_config(capacity_file) if capacity_file else {}
        
        self.job_tosca = {} # store the tosca of each job [job_id]
        self.job_states = {} # store the state of each job [job_id]{state: xxx}
        self.job_responses = {} # store the resource responses from RAs for each job [job_id][ra_id]
        self.job_clients = {} # store the client_id for each job [job_id]

        self.master_info = {} # store the master info for each job [job_id]{ip, port, k3s_token}
        self.job_offers = {} # job_offer stores the offer that fulfills a job request [job_id][]
        self.lead_resource = {} # store the lead resource RA for each job [job_id]=ra_id
        self.tosca = {} # store the Sardou tosca object for each job [job_id]
    
        # Extract configuration values
        self.ra_id = self.config.get('RA_id')
        self.universe_id = self.config.get('universe_id')
        self.api_port = self.config.get('api_port')
        self.p2p_port = self.config.get('p2p_port')
        self.domain = self.config.get('domain', '0.0.0.0')
        self.bootstrap_peers = self.config.get('bootstrap_peers', [])
        self.credentials = self.config.get('credentials', {})
        self.hub_ra_ip = self.config.get('hub_ra_ip', '')

        # Extract cluster-builder required values
        # Ze-TODO: these values may not be needed anymore, tosca.get_cluster() function should return these values, but it is not implemented yet
        # Ze-TODO: Maybe these should be defined in the capacity file instead of config file
        self.ssh_key_path = self.config.get('ssh_key_path', '')
        self.aws_ami = self.config.get('aws_ami', '')
        self.openstack_image_id = self.config.get('openstack_image_id', '')
        self.openstack_network_id = self.config.get('openstack_network_id', '')
        self.edge_device_ip = self.config.get('edge_device_ip', '')

        # Initialize P2P communication
        self.peer = None
        self.is_running = False

        # Setup logging
        self._setup_logging()
        load_dotenv()

    def _load_config(self, config_file: str) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        if not config_file:
            return {}
        try:
            with open(config_file, 'r') as f:
                return yaml.safe_load(f) or {}
        except (FileNotFoundError, yaml.YAMLError) as e:
            logging.error(f"Error loading config {config_file}: {e}")
            return {}

    def _setup_logging(self):
        """Setup logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(f"RA-{self.ra_id}")

    def initialize_peer(self):
        """Initialize P2P peer with configuration"""
        try:
            # Create metadata for this RA
            metadata = {
                "peer_type": "RA",
                "ra_id": self.ra_id,
                "universe_id": self.universe_id,
                "provider": self.credentials.get('provider', 'unknown'),
                "api_port": self.api_port
            }

            # Add capacity information if available
            if self.capacity:
                metadata.update({
                    "capacity_id": self.capacity.get('metadata', {}).get('capacity-id'),
                    "resource_provider": self.capacity.get('metadata', {}).get('resource-provider'),
                    "type": self.capacity.get('metadata', {}).get('type')
                })

            # Initialize SwchPeer
            self.peer = SwchPeer(
                peer_id=self.ra_id,
                listen_ip=self.domain,
                listen_port=self.p2p_port,
                public_ip=self.domain,
                public_port=self.p2p_port,
                metadata=metadata
            )

            # Register message handlers
            self._register_message_handlers()

            self.logger.info(f"RA {self.ra_id} initialized successfully")
            self.logger.info(f"Listening on {self.domain}:{self.p2p_port}")
            self.logger.info(f"API port: {self.api_port}")

        except Exception as e:
            self.logger.error(f"Failed to initialize peer: {e}")
            raise

    def _update_job_state(self, job_id, new_state):
        # create entry if missing
        if job_id not in self.job_states:
            self.job_states[job_id]["state"] = "Pending"
        # update state
        self.job_states[job_id]["state"] = new_state

    def _delete_job(self, job_id):
        if job_id in self.job_states:
            del self.job_states[job_id]

        if job_id in self.job_responses:
            del self.job_responses[job_id]

        if job_id in self.master_info:
            del self.master_info[job_id]

        if job_id in self.job_clients:
            del self.job_clients[job_id]

        if job_id in self.job_offers:
            del self.job_offers[job_id]

        if job_id in self.lead_resource:
            del self.lead_resource[job_id]

    def _register_message_handlers(self):
        """Register handlers for different message types"""
        self.peer.register_message_handler("MSG_SUBMIT", self._handle_submit)
        self.peer.register_message_handler("MSG_GETSTATE", self._handle_getstate)
        self.peer.register_message_handler("MSG_RESOURCE_QUERY", self._handle_resource_query)
        self.peer.register_message_handler("MSG_HEARTBEAT", self._handle_heartbeat)
        self.peer.register_message_handler("MSG_JOB_SUBMIT", self._handle_job_submit)
        self.peer.register_message_handler("MSG_JOB_DELETE", self._handle_job_delete)
        self.peer.register_message_handler("MSG_JOB_BROADCAST", self._handle_job_broadcast)
        self.peer.register_message_handler("MSG_RESOURCE_RESPONSE", self._handle_resource_response)
        self.peer.register_message_handler("MSG_CREATE_RESOURCE", self._handle_create_resource)
        self.peer.register_message_handler("MSG_CREATE_LEAD_RESOURCE", self._handle_create_lead_resource)
        self.peer.register_message_handler("MSG_MASTER_INFO", self._handle_master_info)

    # Ze-TODO： this function may not be needed anymore
    def _handle_submit(self, peer_id: str, message: Dict[str, Any]):
        """Handle job submission requests"""
        self.logger.info(f"Received submit request from {peer_id}")
        app_id = message.get('appid', 'unknown')
        response = {
            "appid": app_id,
            "status": "accepted",
            "ra_id": self.ra_id,
            "message": "Job submission received and queued"
        }
        self.peer.send(peer_id, "MSG_SUBMIT_ACK", response)
        self.logger.info(f"Job {app_id} accepted and queued")

    def _handle_getstate(self, peer_id: str, message: Dict[str, Any]):
        """Handle state query requests"""
        self.logger.info(f"Received state query from {peer_id}")
        job_id = message.get('job_id', 'unknown')
        response = {
            "job_id": job_id,
            "ra_id": self.ra_id,
            "state": self.job_states.get(job_id, {}).get("state", "unknown"),
            "resources_available": True,
            "queue_length": 0
        }
        self.peer.send(peer_id, "MSG_STATE", response)

    def _handle_resource_query(self, peer_id: str, message: Dict[str, Any]):
        """Handle resource availability queries"""
        self.logger.info(f"Received resource query from {peer_id}")
        response = {
            "ra_id": self.ra_id,
            "capacity": self.capacity.get('capacity', {}),
            "pricing": self.capacity.get('pricing', {}),
            "locality": self.capacity.get('locality', {}),
            "available": True
        }
        self.peer.send(peer_id, "MSG_RESOURCE_INFO", response)

    def _handle_heartbeat(self, peer_id: str, message: Dict[str, Any]):
        """Handle heartbeat messages"""
        response = {
            "ra_id": self.ra_id,
            "status": "alive",
            "timestamp": message.get('timestamp')
        }
        self.peer.send(peer_id, "MSG_HEARTBEAT_ACK", response)

    def _handle_job_submit(self, peer_id: str, message: Dict[str, Any]):
        """Handle job submission from client - Hub RA only"""
        self.logger.info(f"Received application submission from {peer_id}")
        job_id = message.get('job_id')
        self.job_states[job_id] = {}
        self._update_job_state(job_id, "Pending")
        self.job_clients[job_id] = message.get('client_id')
        ask_yaml = message.get('tosca')
        # initialise application tosca
        self.job_tosca[job_id] = ask_yaml

        write_yaml(ask_yaml, 'tosca.yaml')
	    # Ze-done: Using TOSCA library to validate and parse the tosca then extract resource requirements 
        try:
            # 1) (done) validate and parse
            self.tosca[job_id] = Sardou('tosca.yaml') #(to validate, may fail if invalid)
            print(f"✅ Successfully validated submitted application tosca for job {job_id}")
            
            # 2) (done) update state: if failed, 'failure';
            # 3) (done) if successful, extract resource requirements from tosca object
            ask_yaml = self.tosca[job_id].get_requirements()
            self._update_job_state(job_id, "Initialising")
            client_id = message.get('client_id')
            all_ras = self.peer.find_peers({"peer_type": "RA"})
            if not ask_yaml:
                self.logger.error("No ask_yaml data in application submission")
                return

            # Hub RA processes resource requirements and broadcasts to other RAs
            if not self.bootstrap_peers:
                self.logger.info(f"Broadcasting application {job_id} to all RAs")

                # Find all other RAs in network
                all_ras = self.peer.find_peers({"peer_type": "RA"})
                other_ras = [ra for ra in all_ras if ra != self.ra_id]

                broadcast_message = {
                    "job_id": job_id,
                    "client_id": client_id,
                    "ask_yaml": ask_yaml,
                    "timestamp": message.get('timestamp'),
                    "hub_ra": self.peer.peer_id
                    #"hub_ra": self.ra_id
                }

                # Broadcast to all other RAs
	            # Ze-TODO: modify this, to use broadcast method
                for ra_id in other_ras:
                    self.peer.send(ra_id, "MSG_JOB_BROADCAST", broadcast_message)
                    self.logger.info(f"Broadcasted application to {ra_id}")

                # Process locally as well
                self._process_job_requirements(job_id, client_id, ask_yaml, self.peer.peer_id)            
            else:
                self.logger.warning("Non-hub RA received direct job submission")
        except Exception as e:
            print(f"❌ Failed to process tosca.yaml: {e}")
            self._update_job_state(job_id, new_state="Invalid")
            return None
  

    def _handle_job_delete(self, peer_id: str, message: Dict[str, Any]):
        """Handle job deletion requests"""
        self.logger.info(f"Received submit job deletion request from {peer_id} to delete job {message.get('job_id')}")
        job_id = message.get('job_id')
        CLUSTER_NAME = job_id
        swarmchestrate = Swarmchestrate(template_dir="templates", output_dir="output")
        swarmchestrate.destroy(CLUSTER_NAME)
        self._delete_job(job_id)
        self.logger.info(f"Job {job_id} deleted successfully")


    def _handle_job_broadcast(self, peer_id: str, message: Dict[str, Any]):
        """Handle job broadcast from hub RA"""
        self.logger.info(f"Received application resource requirement broadcast from hub {peer_id}")

        job_id = message.get('job_id')
        client_id = message.get('client_id')
        ask_yaml = message.get('ask_yaml')
        hub_ra = message.get('hub_ra')
        all_ras = self.peer.find_peers({"peer_type": "RA"})

        # Process job requirements
        self._process_job_requirements(job_id, client_id, ask_yaml, hub_ra)

    def _process_job_requirements(self, job_id: str, client_id: str, ask_yaml: Dict, hub_ra: str):
        """ 
            Ze:
            Process job requirements against RA capacity
            Each RA receives a JOB_BROADCAST msg with job requirements from the Hub RA.
            Each RA evaluates the requirements and sends a RESOURCE_RESPONSE msg back to the Hub RA with their resource offers.
        """

        self.logger.info(f"RA: {self.ra_id} Evaluating application {job_id} requirements")

        if not self.capacity:
            self.logger.warning("No capacity data available for evaluation")
            return

        # Evaluate each resource request
        resource_responses = {}

        for resource_name, resource_requirements in ask_yaml.items():
            if not isinstance(resource_requirements, dict):
                continue

            self.logger.info(f"Evaluating application resource requirements for {resource_name}")

            # Extract requirements and metadata
            capabilities = resource_requirements.get('capabilities', {})
            count = resource_requirements.get('count', 1)
            metadata = resource_requirements.get('metadata', {})

            # Binary evaluation - can we fulfill this requirement?
            can_fulfill = self._evaluate_requirement(capabilities, count)

            if can_fulfill:
                self.logger.info(f"✅ {resource_name}: YES - Can fulfill requirement")
                resource_responses[resource_name] = {
                    "answer": "yes",
                    "ra_id": self.ra_id,
                    "provider": self.capacity.get('metadata', {}).get('resource-provider'),
                    # Ze—done：double check this redundant field
                    # Ze：in resource response handler， we only used provider field so the redundant field is removed
                    #"resource_provider": self.capacity.get('metadata', {}).get('resource-provider'),
                    "location": self._format_location(),
                    "bid": self._create_bid(resource_name, capabilities, count),
                    "resource_definition": self._create_resource_definition(resource_name, capabilities, count),
                    "available_instances": self._get_matching_instances(capabilities),
                    "estimated_setup_time": "2-5 minutes",
                    "metadata": metadata
                }
            else:
                self.logger.info(f"❌ {resource_name}: NO - Cannot fulfill requirement")
                resource_responses[resource_name] = {
                    "answer": "no",
                    "ra_id": self.ra_id,
                    "reason": "Insufficient capacity or incompatible requirements"
                }

        # # Ze: we need this condition because the hub RA does not received RESOURCE_RESPONSE sent from itself
        # # Ze：with the latest P2P lib changes, the hub RA also receives its own sent messages, so this block is commented out
        # if self.ra_id == hub_ra:
        #     self.logger.info(f"Hub RA {self.ra_id} does not send RESOURCE_RESPONSE to itself")
        #     if job_id not in self.job_responses:
        #         self.job_responses[job_id] = {}
        #     self.job_responses[job_id][self.ra_id] = {
        #         'provider': self.capacity.get('metadata', {}).get('resource-provider'),
        #         'responses': resource_responses
        #     }
        #     return
        
        # Send consolidated response to client
        response_message = {
            "job_id": job_id,
            "ra_id": self.ra_id,
            "provider": self.capacity.get('metadata', {}).get('resource-provider'),
            "timestamp": time.time(),
            "responses": resource_responses
        }

        all_ras = self.peer.find_peers({"peer_type": "RA"})
        #print(f"Sending resource response to hub RA {hub_ra} from RA {self.ra_id}, total RAs in network: {len(all_ras)}")
        self.peer.send(hub_ra, "MSG_RESOURCE_RESPONSE", response_message)

    def _evaluate_requirement(self, capabilities: Dict, count: int) -> bool:
        """Evaluate if we can fulfill the requirement using simple evaluator"""
        if not capabilities:
            return True
        
        # Use the simple evaluation function
        ask_requirements = {'capabilities': capabilities}
        can_fulfill = can_fulfill_requirement(ask_requirements, self.capacity)
        
        if not can_fulfill:
            self.logger.info("Requirements are not fulfilled")
            return False
          
        # Find matching instances
        suitable_instances = get_matching_instances(capabilities, self.capacity)
        if not suitable_instances:
            self.logger.info("Requirement fulfilled, but no suitable instances found")
            return False
        
        # Verify quota availability
        if not self._verify_quota(suitable_instances, count):
            self.logger.info("Quota check failed")
            return False
        
        self.logger.info(f"All checks passed! Suitable instances: {suitable_instances}")
        return True

    def _verify_quota(self, suitable_instances: List[str], count: int) -> bool:
        """Verify quota availability for instances"""
        our_quota = self.capacity.get('capacity', {}).get('instances_quota', {})
         # ADDED: Handle flat structure - if no quota defined, assume single instance
        if not our_quota and 'single-config' in suitable_instances:
            return count <= 1

        for instance_type in suitable_instances:
            available_quota = our_quota.get(instance_type, 0)
            if available_quota >= count:
                return True

        return False

    def _create_bid(self, resource_name: str, capabilities: Dict, count: int) -> Dict:
        """Create bid information for resource"""
        suitable_instances = get_matching_instances(capabilities, self.capacity)
        if not suitable_instances:
            return {}

        # Find most cost-effective instance
        # Ze-DONE: we should use the smallest instance that fulfills the requirements.
        our_pricing = self.capacity.get('pricing', {})
        
        # ADDED: Handle flat structure pricing
        if isinstance(our_pricing, (int, float)):
            best_cost = float(our_pricing)
            best_instance = 'single-config'
            our_capacity = self.capacity.get('capacity', {})
            energy = our_capacity.get('energy-consumption', 0)
            bandwidth = our_capacity.get('bandwidth', 0)
        elif isinstance(our_pricing, str):
            best_cost = float(our_pricing.replace('$', '').strip())
            best_instance = 'single-config'
            our_capacity = self.capacity.get('capacity', {})
            energy = our_capacity.get('energy-consumption', 0)
            bandwidth = our_capacity.get('bandwidth', 0)
        else:
            # Original instances logic
            best_instance = min(suitable_instances, key=lambda x: our_pricing.get(x, float('inf')))
            best_cost = our_pricing.get(best_instance, 0)
            # Check if it's still a flat structure selected
            if best_instance == 'single-config':
                our_capacity = self.capacity.get('capacity', {})
                energy = our_capacity.get('energy-consumption', 0)
                bandwidth = our_capacity.get('bandwidth', 0)
            else:
                energy = self.capacity['capacity']['instances'][best_instance]['energy-consumption']
                bandwidth = self.capacity['capacity']['instances'][best_instance]['bandwidth']
        
        return {
            "instance_type": best_instance,
            "cost_per_hour": best_cost,
            "total_cost_per_hour": best_cost * count,
            "currency": "credits",
            "count": count,
            "setup_fee": 0,
            "minimum_duration": "1 hour",
            "energy-consumption": energy,
            "bandwidth": bandwidth
            #"energy-consumption": self.capacity['capacity']['instances'][best_instance]['energy-consumption'],
            #"bandwidth": self.capacity['capacity']['instances'][best_instance]['bandwidth']
        }

    def _create_resource_definition(self, resource_name: str, capabilities: Dict, count: int) -> Dict:
        """Create resource definition for response"""
        suitable_instances = get_matching_instances(capabilities, self.capacity)
        if not suitable_instances:
            return {}

        best_instance = suitable_instances[0]
        our_instances = self.capacity.get('capacity', {}).get('instances', {})
        # ADDED: Handle flat structure
        if not our_instances and best_instance == 'single-config':
            matched_specs = self.capacity.get('capacity', {}).copy()
        else:
            matched_specs = our_instances.get(best_instance, {}).copy()
        matched_specs['instance_type'] = best_instance

        return {
            "name": resource_name,
            "type": "virtual_machine",
            "count": count,
            "specifications": matched_specs,
            "operating_system": self.capacity.get('system', {}).get('os', {}),
            "location": self.capacity.get('locality', {}),
            "provider_info": {
                "provider": self.credentials.get('provider'),
                "resource_provider": self.capacity.get('metadata', {}).get('resource-provider'),
                "capacity_provider": self.capacity.get('metadata', {}).get('capacity-provider')
            }
        }

    def _get_matching_instances(self, capabilities: Dict) -> Dict:
        """Get detailed information about matching instances"""
        suitable_instances = get_matching_instances(capabilities, self.capacity)
        our_instances = self.capacity.get('capacity', {}).get('instances', {})
        our_quota = self.capacity.get('capacity', {}).get('instances_quota', {})
        our_pricing = self.capacity.get('pricing', {})

        matching = {}
        # ADDED: Handle flat structure
        if 'single-config' in suitable_instances:
            capacity_section = self.capacity.get('capacity', {})
            price = our_pricing if isinstance(our_pricing, (int, float)) else 0
            if isinstance(our_pricing, str):
                price = float(our_pricing.replace('$', '').strip())
            
            matching['single-config'] = {
                "specifications": capacity_section,
                "available_quota": 1,
                "cost_per_hour": price,
                "energy-consumption": capacity_section.get('energy-consumption', 0),
                "bandwidth": capacity_section.get('bandwidth', 0)
            }
        else:
            # Original instances logic
            for instance_type in suitable_instances:
                matching[instance_type] = {
                    "specifications": our_instances.get(instance_type, {}),
                    "available_quota": our_quota.get(instance_type, 0),
                    "cost_per_hour": our_pricing.get(instance_type, 0)
                }


        return matching

    def _format_location(self) -> str:
        """Format location string from capacity data"""
        locality = self.capacity.get('locality', {})
        city = locality.get('city', 'Unknown')
        country = locality.get('country', 'Unknown')
        return f"{city}, {country}"
    
    def _handle_resource_response(self, peer_id, message):
        """
            Ze:
            Process resource response from RA
            The Hub RA receives RESOURCE_RESPONSE msgs from all RAs.
            It compiles the responses, finds valid combinations, ranks them using AI algorithm, and selects one.
            The lead resource (LR) is then created based on the selected offer.
            Only LR is created here because it will create the k3s cluster and returns the master info to the hub RA so that other RAs can connect to it.
        """

        self.logger.info(f"Received resource response from RA: {peer_id}")
        job_id = message.get('job_id')
        ra_id = message.get('ra_id')
        provider = message.get('provider')
        responses = message.get('responses', {})
        len_res = len(responses)
        #print(f"len of job responses for job {job_id} is {len_res}")
        
        if job_id not in self.job_responses:
            self.job_responses[job_id] = {}

        self.job_responses[job_id][ra_id] = {
            'provider': provider,
            'responses': responses
        }

        # Check if all RAs have responded
        all_ras = self.peer.find_peers({"peer_type": "RA"})
        #here we need len(all_ras) + 1 because all_ras does not include the main ra, the main ra cannot be detected with the function self.peer.find_peers({"peer_type": "RA"}).
        if len(self.job_responses.get(job_id, {})) >= len(all_ras)+1:
            print(f"All RAs have responded for job {job_id}. Compiling results...")
            self._compile_and_display_results(job_id)
        else:
            return
        # Amjad: appeared also if there are offers. temporary commenting
        #test
        # ADDED: Check if job_offers[job_id] is None (no valid combinations)
        if job_id not in self.job_offers:
            self.logger.exception(
                    "No valid resource combinations for application %s",
                    job_id,
                )
            client_id = self.job_clients.get(job_id)
            if client_id:
                print("Sending submit response failure message to client:", client_id)
                submit_response_message = {
                        "job_id": job_id,
                        "ra_id": self.ra_id,
                        "result": "failure",
                        "message": "Failed to compile resource offers"
                        }
                self.peer.send(client_id, "MSG_SUBMIT_RESPONSE", submit_response_message)                
                return None

        print("Valid resource combinations found. Selecting lead resource...") 
        # Ze-TODO: randomly select a resource's RA node as LR
        # Ze-DONE: for demo purpose, we hardcode the lead resource to be 'ra-aws-cloud-us'
        self.lead_resource[job_id] = next((k for k, v in self.job_offers[job_id].items() if v.get('ra_id') == 'ra-aws-cloud-us'), None)
        LR_id = self.job_offers[job_id][self.lead_resource[job_id]]["ra_id"]
        provider = self.job_offers[job_id][self.lead_resource[job_id]]["provider"]
        instance_type = self.job_offers[job_id][self.lead_resource[job_id]]["instance_type"]

        
        print("Press a key to continue:")
        key_to_continue = input()
        msg_lead_resource_request_ra = {
                "job_id": job_id,
                "hub_ra": self.peer.peer_id,
                "lead_resource": True,
                "leader_resource_name": self.lead_resource[job_id],
                "timestamp": message.get('timestamp'),
                "instance": {"instance_type": instance_type, "cloud": provider, "k3s_role": "master", "node-name": self.lead_resource[job_id]},
                "tosca": self.job_tosca[job_id],
                "offer_info": self.job_offers[job_id]
                #"instance": { "cloud": provider ,"instance_type": instance_type ,"ssh_key_name": "g","ssh_user": "ec2-user","k3s_role": "master","ssh_private_key_path": "","ami": "ami-0f7b02bb6a0e14062"}
        }
        
        self.peer.send(LR_id, "MSG_CREATE_LEAD_RESOURCE", msg_lead_resource_request_ra)
        self.logger.info(f"Sent resource request to RA: {LR_id}")
        print("lens of job offer is: ",len(self.job_offers[job_id])-1)



    def _compile_and_display_results(self, job_id):
        """Compile and display resource allocation results"""
        print("\nCompiling resource offers...")
        print("=" * 60)

        ra_responses = self.job_responses.get(job_id, {})

        # Extract all resource names from responses
        all_resource_names = set()
        for ra_id, ra_data in ra_responses.items():
            if ra_data['responses']:
                all_resource_names.update(ra_data['responses'].keys())

        if not all_resource_names:
            print("No resource requirements found")
            return

        # Display response matrix
        resource_names = sorted(all_resource_names)
        
        print("Response Summary:")
        print("-" * 60)
        
        # Create table header
        header = f"{'RA (Provider)':<30}"
        for resource_name in resource_names:
            header += f"{resource_name.title():<15}"
        print(header)
        print("-" * (20 + len(resource_names) * 15))

        # Create table rows
        for ra_id, ra_data in ra_responses.items():
            provider = ra_data['provider']
            responses = ra_data['responses']

            row = f"{ra_id} ({provider})"[:29].ljust(30)
            for resource_name in resource_names:
                answer = responses.get(resource_name, {}).get('answer', 'N/A')
                row += f"{answer}"[:14].ljust(15)
            print(row)

        print("\nFinding valid combinations...")
        print("=" * 60)

        # Find feasible resource combinations
        valid_combinations = self._find_valid_combinations(ra_responses, resource_names)

        if valid_combinations:
            print(f"Found {len(valid_combinations)} valid combination(s):")
            print("-" * 60)
            print("Possible offers:")
            
            for i, combination in enumerate(valid_combinations, 1):
                combo_str = f"{i}. "
                
                resource_items = []
                energy_consumption = 0
                total_bandwidth = 0
                total_price = 0
                for resource_name in sorted(combination.keys()):
                    allocation = combination[resource_name]
                    ra_id = allocation['ra_id']
                    energy_consumption += allocation['energy-consumption']
                    total_price += allocation['cost_per_hour']
                    total_bandwidth += allocation['bandwidth']
                    resource_items.append(f"{resource_name}: {ra_id}")
                
                combo_str += ", ".join(resource_items)
                print(combo_str)
                print(f", total energy consumption is: {energy_consumption:.2f}, total bandwidth is: {total_bandwidth}, total price is: {total_price}")
            print("-" * 60)
            
            # Randomly select one combination
            # Ze：we will use AI algorithm to select the best combination instead of random selection
            #selected_index = random.randint(0, len(valid_combinations) - 1)
            
            # Using AI algorithm to select the best combination
            selected_index = self._rank_resource_offers(valid_combinations, job_id)
            selected_combination = valid_combinations[selected_index]
            
            print(f"\nSELECTED OFFER (chosen by the ranking algorithm: #{selected_index + 1}):")
            print("=" * 60)
            
            resource_items = []
            energy_consumption = 0
            total_bandwidth = 0
            total_price = 0
            for resource_name in sorted(selected_combination.keys()):
                allocation = selected_combination[resource_name]
                count = allocation['count']
                ra_id = allocation['ra_id']
                energy_consumption += allocation['energy-consumption']
                total_bandwidth += allocation['bandwidth']
                total_price += allocation['cost_per_hour']
                resource_items.append(f"{resource_name}: {ra_id}")
            
            print(", ".join(resource_items))
            print(f", total energy consumption is: {energy_consumption:.2f}, total bandwidth is: {total_bandwidth}, total price is: {total_price}")
            print("=" * 60)
        else:
            print(f"No valid resource combinations found for job {job_id}!")
            selected_combination = None
            return
        # Save valid_combinations to a JSON file
        with open("valid_combinations.json", "w") as f:
            json.dump(valid_combinations, f, indent=2)
        # Complete job processing
        time.sleep(1)
        self.job_complete = True
        if job_id not in self.job_offers:
            self.job_offers[job_id] = {}

        self.job_offers[job_id] = selected_combination
        print(f"job_offer for job {job_id} is {self.job_offers[job_id]}")
        #self.peer.leave().addCallback(lambda _: self.peer.stop())

    def _rank_resource_offers(self,valid_combinations, job_id):
        """Rank resource offers based on QoS attributes using AI algorithm"""
        # Ze-done: Using the TOSCA library to fetch QoS priorities and populate them into the qos_priority template.
        # 1) create a qos_priority template
        # 2) get the qos_priority from the TOSCA 
        # 3) populate the qos_priority template

        qos_data = self.tosca[job_id].get_qos()
        qos_priority = get_qos_priorities(qos_data)
        print(f"qos_priority extracted from TOSCA is {qos_priority}")
        reliability_list = []
        latency_list = []
        energy_list = []
        bandwidth_list = []
        price_list = []
        for combination in valid_combinations:
            total_energy = 0
            total_bandwidth = 0
            total_price = 0
            for resource in combination.values():
                total_energy += resource.get('energy-consumption', 0)
                total_bandwidth += resource.get('bandwidth', 0)
                total_price += resource.get('cost_per_hour', 0)
            energy_list.append(total_energy)
            bandwidth_list.append(total_bandwidth)
            price_list.append(total_price)
            reliability_list.append(1) # Placeholder for reliability
            latency_list.append(1)     # Placeholder for latency 

        offer_data = {
            "qos_priority": qos_priority,
            "reliability": reliability_list,
            "energy": energy_list,
            "bandwidth": bandwidth_list,
            "latency": latency_list,
            "price": price_list
        }

        # Save offer data to a JSON file for debugging
        with open("rank-format.json", "w") as f:
            json.dump(offer_data, f, indent=2)

        # Call ranking function
        evaluator = OfferEvaluator(offer_data)
        optimal_index = evaluator.rank_offers_without_reliability()
        # Return first item if optimal_index is not empty
        return optimal_index[0]

    def _find_valid_combinations(self, ra_responses, resource_names):
        """Find all valid resource allocation combinations"""
        valid_combinations = []

        # Map resources to capable RAs
        resource_providers = {}
        for resource_name in resource_names:
            providers = []
            for ra_id, ra_data in ra_responses.items():
                response = ra_data['responses'].get(resource_name, {})
                if response.get('answer') == 'yes':
                    providers.append({
                        'ra_id': ra_id,
                        'provider': ra_data['provider'],
                        'response': response
                    })
            resource_providers[resource_name] = providers

        # Check if all resources can be fulfilled
        for resource_name, providers in resource_providers.items():
            if not providers:
                return []

        # Generate all possible combinations
        provider_lists = [resource_providers[name] for name in resource_names]

        for combination_tuple in product(*provider_lists):
            combination = {}
            for i, resource_name in enumerate(resource_names):
                provider_info = combination_tuple[i]
                response = provider_info['response']
		# Ze: a combination is an offer that fulfills all resources
                combination[resource_name] = {
                    'ra_id': provider_info['ra_id'],
                    'provider': provider_info['provider'],
                    'cost_per_hour': response.get('bid', {}).get('cost_per_hour', 0),
                    'count': response.get('bid', {}).get('count', 1),
                    'instance_type': response.get('bid', {}).get('instance_type', 'unknown'),
                    'energy-consumption': response.get('bid', {}).get('energy-consumption', 0),
                    'bandwidth': response.get('bid', {}).get('bandwidth', 0)
                }

            valid_combinations.append(combination)

        return valid_combinations


    def _handle_create_lead_resource(self, peer_id, message):
        """
            Ze:
            The RA which receives this msg will create the lead resource (LR) VM, k3s cluster, and return the master info to the hub RA.
        """
        self.logger.info(f"RA {self.ra_id} receives create lead resource request from {peer_id}")
        job_id = message.get('job_id')

        LR = message.get('lead_resource')
        lead_resource_name = message.get('leader_resource_name')
        instance = message.get('instance', {})
        instance_type = instance["instance_type"]
        k3s_role = instance["k3s_role"]
        node_name = instance["node-name"]
        tosca = message.get('tosca', {})
        cloud = instance["cloud"]
        #cloud = "openstack"
        #instance_type = "m2.small"
        print(f"instance is {instance}")
        offer_info = message.get('offer_info', {})
        print(f"offer_info received by LR is {offer_info}")

        # Ze-done: finish the RA which receives the msg and to create a VM
        if(LR):
	    # Ze: if it is the lead resource,
            # 1. creates the LR VM
            # 2. k3s cluster
            # Ze-done; make sure them can be correctly loaded on all clouds (sztaki, edge, aws_us)

            # For future automation, we need to make sure each RA has the required ssh key pair, security group, ami, etc for each provider.
            master_node_aws = (
                f'{{"cloud": "{cloud}",' # Ze: we can make it dynamic fetch from offer. Each RA could access multiple providers so this cannot be collected from config file
                f'"instance_type": "{instance_type}",'
                f'"ha": false,'
                f'"cluster_name": "{job_id}",'
                f'"ami": "{self.aws_ami}",' # Ze: we can make it dynamic later (from capacity/config info) does each provider has its own ami?
                f'"security_group_id": "",' # Ze: we can make it dynamic later from cluster-builder lib
                f'"resource_name":"{node_name}",' # Ze: to think about how to name
                f'"ssh_user": "ec2-user",' # Ze: we can make it dynamic later (from capacity/config info) does each provider has its own ssh user?
            #    f'"ssh_key_name": "",' # Ze: we can make it dynamic later (from capacity/config info) Does each provider has its own key pair?
                f'"ssh_key": "{self.ssh_key_path}",' # Ze: we can make it dynamic later (from capacity/config info) does each provider has its own private key?
                f'"k3s_role": "{k3s_role}"}}' # Ze: this should be default 
            )

            master_node_openstack = (
                f'{{"cloud": "{cloud}",'
                f'"openstack_flavor_id": "{instance_type}",'
                f'"ha": false,'
                f'"openstack_image_id": "{self.openstack_image_id}",'
                f'"security_group_id": "",'
                f'"volume_size": "10",'
                f'"floating_ip_pool": "ext-net",'
                f'"network_id": "{self.openstack_network_id}",'
                f'"cluster_name": "{job_id}",'
                f'"resource_name":"{node_name}",'    
                f'"ssh_user": "ubuntu",'
                f'"ssh_key_name": "",'
                f'"ssh_private_key_path": "{self.ssh_key_path}",'
                f'"use_block_device": true,'
                f'"k3s_role": "{k3s_role}"}}'
            )
            master_node_edge = (
                f'{{"cloud": "{cloud}",'
                f'"edge_device_ip": "{self.edge_device_ip}",'
                f'"ha": false,'
                f'"cluster_name": "{job_id}",'
                f'"resource_name":"{node_name}",'
                f'"ssh_user": "ec2-user",'
                f'"ssh_key": "{self.ssh_key_path}",'
                f'"ssh_auth_method": "key",'
                f'"k3s_role": "{k3s_role}"}}'
            )
            master_node = {
                "aws": master_node_aws,
                "openstack": master_node_openstack,
                "edge": master_node_edge
            }[cloud]
            master_node = json.loads(master_node)

            swarmchestrate = Swarmchestrate(template_dir="templates", output_dir="output")
            outputs = swarmchestrate.add_node(master_node)

            k3s_token = outputs.get("k3s_token")
            cluster_name = outputs.get("cluster_name")
            master_ip = outputs.get("master_ip")


            print(f"[DEBUG] master ip is {master_ip}")
            # After creating the lead resource;
            # substract the count of the resource requirement for lead resource by one because it will be created

            
            # Ze-done: Prepare configmap of tosca file for SA
            # Ze: we have three folders to create here: KB/, k3s/, k3s-{job_id}/
            #     1) KB/ acts as knowledge base and stores the tosca file
            #     2) k3s/ stores default manifests for deploying SA and other, i.e., namespace, daemonset, rbac, k3s-dashboard
            #     3) k3s-{job_id}/ stores all manifests for deploying SA for this job, it copies from k3s/ and adds two configmaps: tosca configmap and SA configmap  
            #        a) tosca configmap: contains the tosca file for this job
            #        b) SA configmap: contains the SA configuration info

            folder_path = f"KB"
            #import os
            #import shutil

            _os.makedirs(folder_path, exist_ok=True)  # ✅ Creates folder if it doesn't exist
            write_yaml(tosca, f"KB/{job_id}_tosca.yaml")
            folder_path = f"k3s-{job_id}"
            _os.makedirs(folder_path, exist_ok=True)  # ✅ Creates folder if it doesn't exist
            src_folder = "k3s"

            # ✅ Copy all files from k3s/ into k3s-{job_id}/
            if _os.path.exists(src_folder):
                for item in _os.listdir(src_folder):
                    src_path = _os.path.join(src_folder, item)
                    dest_path = _os.path.join(folder_path, item)
                    if _os.path.isdir(src_path):
                        _shutil.copytree(src_path, dest_path, dirs_exist_ok=True)
                    else:
                        _shutil.copy2(src_path, dest_path)
            else:
                print(f"⚠️ Warning: Source folder '{src_folder}' does not exist.")
            
            # prepare configmap of tosca file for SA
            configMap_tosca_path = f"k3s-{job_id}/03-configmap-swarm-agent-tosca.yaml"
            write_tosca_configmap(f"KB/{job_id}_tosca.yaml", output_file=configMap_tosca_path)
            
            # Ze-done: Prepare configmap of SA configuration
            # input: job_id, resource names
            # Ze-done: input should include hub RA's ip. without it, SA cannot join in p2p network.
            resource_input = {
                "LEADER": lead_resource_name,
                "Worker": [res for res in offer_info if res != lead_resource_name]                                
            }
            configMap_config_path = f"k3s-{job_id}/04-configmap-swarm-agent-config.yaml"
            # The ra_ip should be the ip of one of the RAs, don't be confused with master_ip which is the LR ip.
            # Ze-TODO: we need to make sure the hub RA ip is reachable by all RAs.
            write_swarm_configmap(resource_input, application_id=job_id, output_file=configMap_config_path,ra_ip=""+self.hub_ra_ip+"")
            
            # Ze-done: Create registry secret on the LR using cluster-builder library
            registry_config = {
                "master_ip": master_ip,
                "ssh_user": "ec2-user", #Ze-TODO: ubuntu for openstack
                "ssh_private_key_path": self.ssh_key_path,
                "secret_names": ["regcred"] #optional
                #"namespace":"test" , #optional
            }
 
            # Run the registry secret creation
            swarmchestrate = Swarmchestrate(template_dir="templates", output_dir="output")
            swarmchestrate.create_registry_secrets(registry_config)

            # copy the manifests from k3s-{job_id}/ to the LR
            manifest_cfg = (
                f'{{"manifest_folder": "/home/ubuntu/e2e-demo/ra/k3s-{job_id}",'
#                f'{{"manifest_folder": "/home/ubuntu/e2e-demo/k3s-{job_id}",'

                f'"master_ip": "{master_ip}",'
                f'"ssh_key_path": "{self.ssh_key_path}",'
                f'"ssh_user": "ec2-user"}}'
            )
            cfg = json.loads(manifest_cfg)
            manifest_folder = Path(cfg["manifest_folder"])
            manifest_folder.exists() or exit(f"❌ Manifest folder does not exist: {manifest_folder}")
            # Run cluster-builder copy-manifest
            Swarmchestrate(template_dir="templates", output_dir="output").deploy_manifests(
            manifest_folder=str(manifest_folder),
            master_ip=cfg["master_ip"],
            ssh_key_path=cfg["ssh_key_path"],
            ssh_user=cfg["ssh_user"]
            ) 

            # Ze: send k3s master info back to the hub RA, so that other RAs can create worker nodes and join the cluster
            msg_master_info = {
                "job_id": job_id,
                "hub_ra": self.peer.peer_id,
                "timestamp": message.get('timestamp'),
                "master_info": { "k3s_token": k3s_token ,"cluster_name": cluster_name, "master_ip": master_ip}
            }
            self.peer.send(message.get('hub_ra'), "MSG_MASTER_INFO", msg_master_info)
            self.logger.info(f"RA {self.ra_id} instantiates the lead resource")

    def _handle_master_info(self, peer_id, message):
        """Process master info from lead resource"""
        self.logger.info(f"RA {self.ra_id} receives master info from {peer_id}")
        job_id = message.get('job_id')
        master_info = message.get('master_info', {})
        k3s_token = master_info["k3s_token"]
        cluster_name = master_info["cluster_name"]
        master_ip = master_info["master_ip"]
        self.job_offers[job_id][self.lead_resource[job_id]]["count"] -= 1
        offer_info = self.job_offers[job_id]
        #print(f"Master info received by main RA is: {master_info}")
        for res in offer_info:
            if offer_info[res]["count"] <=0:
                continue
            ra_id = offer_info[res]["ra_id"]
            print(f"ra_id in offer_info is {ra_id}")
            msg_create_resource = {
                    "job_id": job_id,
                    "hub_ra": self.peer.peer_id, 
                    "lead_resource": False, 
                    "timestamp": message.get('timestamp'),
                    "instance": { "resource": offer_info[res], "k3s_role": "worker", "node-name": list(offer_info.keys())[list(offer_info.values()).index(offer_info[res])]},
                    "master_info": { "k3s_token": k3s_token ,"cluster_name": cluster_name, "master_ip": master_ip}
                }
            self.peer.send(ra_id, "MSG_CREATE_RESOURCE", msg_create_resource)
        self.job_offers[job_id][self.lead_resource[job_id]]["count"] += 1

    def _handle_create_resource(self, peer_id, message):
        """Process create resource request from LRA"""
        self.logger.info(f"RA {self.ra_id} receives create resource request from {peer_id}")
        job_id = message.get('job_id')
        instance = message.get('instance', {})
        instance_type = instance["resource"]["instance_type"]
        k3s_role = instance["k3s_role"]
        resource_name = instance["node-name"]
        self.master_info = message.get('master_info') # Ze-TODO: master info should be job_id specific
        cluster_name = self.master_info["cluster_name"]
        master_ip = self.master_info["master_ip"]
        k3s_token = self.master_info["k3s_token"]
        for i in range(instance["resource"]["count"]):
            cloud = instance["resource"]["provider"]
            if instance["resource"]["count"] >1:
                node_name = f"{resource_name}-{i+1}"
            else:
                node_name = resource_name
            worker_node_aws = (
                    f'{{"cloud": "{cloud}",' # Ze: we can make it dynamic fetch from offer. Each RA could access multiple providers so this cannot be collected from config file
                    f'"instance_type": "{instance_type}",'
                    f'"ha": false,'
                    f'"ami": "{self.aws_ami}",' # Ze: we can make it dynamic later (from capacity/config info) does each provider has its own ami?
                    f'"security_group_id": "",' # Ze: we can make it dynamic later from cluster-builder lib
                    f'"resource_name":"{node_name}",' # Ze: to think about how to name
                    f'"ssh_user": "ec2-user",' # Ze: we can make it dynamic later (from capacity/config info) does each provider has its own ssh user?
                 #   f'"ssh_key_name": "",' # Ze: we can make it dynamic later (from capacity/config info) Does each provider has its own key pair?
                    f'"ssh_key": "{self.ssh_key_path}",' # Ze: we can make it dynamic later (from capacity/config info) does each provider has its own private key?
                    f'"k3s_role": "{k3s_role}",' # Ze: this should be default 
                    f'"k3s_token": "{k3s_token}",'
                    f'"master_ip": "{master_ip}",'
                    f'"cluster_name": "{cluster_name}"}}'
                )

            worker_node_openstack = (
                    f'{{"cloud": "{cloud}",'
                    f'"openstack_flavor_id": "{instance_type}",'
                    f'"ha": false,'
                    f'"openstack_image_id": "{self.openstack_image_id}",'
                    #f'"security_group_id": "",'
                    f'"volume_size": "10",'
                    #f'"floating_ip_pool": "ext-net",'
                    f'"network_id": "{self.openstack_network_id}",'
                    f'"resource_name":"{node_name}",'    
                    f'"ssh_user": "ubuntu",'
                    #f'"ssh_key_name": "",'
                    f'"ssh_key": "{self.ssh_key_path}",'
                    f'"use_block_device": true,'
                    f'"k3s_role": "worker",'
                    f'"k3s_token": "{k3s_token}",'
                    f'"master_ip": "{master_ip}",'
                    f'"cluster_name": "{cluster_name}"}}' 
                )

            worker_node_edge = (
                    f'{{"cloud": "{cloud}",'
                    f'"edge_device_ip": "{self.edge_device_ip}",'
                    f'"ha": false,'
                    f'"resource_name":"{node_name}",'
                    f'"ssh_user": "ec2-user",'
                    f'"ssh_key": "{self.ssh_key_path}",'
                    f'"ssh_auth_method": "key",'
                    f'"k3s_role": "worker",'
                    f'"k3s_token": "{k3s_token}",'
                    f'"master_ip": "{master_ip}",'
                    f'"cluster_name": "{cluster_name}"}}'   
                )
            worker_node = {
                    "aws": worker_node_aws,
                    "openstack": worker_node_openstack,
                    "edge": worker_node_edge
                }[cloud]
            worker_node = json.loads(worker_node)
            swarmchestrate = Swarmchestrate(template_dir="templates", output_dir="output")
            swarmchestrate.add_node(worker_node)
        

	# Ze-done: finish the RA which receives the msg and to create a VM
        self.logger.info(f"RA {self.ra_id} instantiates resource {resource_name} for job {job_id}")

    def connect_to_network(self):
        """Connect to P2P network using bootstrap peers"""
        if not self.bootstrap_peers:
            self.logger.info("No bootstrap peers configured - running as hub")
            return

        # Connect to configured bootstrap peers
        for peer_address in self.bootstrap_peers:
            try:
                host, port = peer_address.split(':')
                port = int(port)
                self.logger.info(f"Connecting to bootstrap peer: {host}:{port}")
                self.peer.enter(host, port)
            except (ValueError, Exception) as e:
                self.logger.error(f"Failed to connect to {peer_address}: {e}")

    def start(self):
        """Start the Resource Agent"""
        try:
            self.logger.info(f"Starting Resource Agent: {self.ra_id}")
            self.initialize_peer()
            self.connect_to_network()
            self.is_running = True
            self.logger.info(f"RA {self.ra_id} is now running and ready to accept connections...")
            self.peer.start()
        except KeyboardInterrupt:
            self.logger.info("Shutdown requested by user")
            self.stop()
        except Exception as e:
            self.logger.error(f"Failed to start RA: {e}")
            self.is_running = False
            raise

    def stop(self):
        """Stop the Resource Agent"""
        self.logger.info(f"Stopping Resource Agent: {self.ra_id}")
        self.is_running = False
        if self.peer:
            self.peer.stop()

    def get_status(self) -> Dict[str, Any]:
        """Get current status of the Resource Agent"""
        return {
            "ra_id": self.ra_id,
            "universe_id": self.universe_id,
            "is_running": self.is_running,
            "p2p_port": self.p2p_port,
            "api_port": self.api_port,
            "bootstrap_peers": self.bootstrap_peers,
            "provider": self.credentials.get('provider'),
            "capacity_loaded": bool(self.capacity)
        }



