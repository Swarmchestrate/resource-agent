"""
Base Resource Agent (RA) implementation
Handles P2P communication and resource matching
"""
#import
# unused imports removed

            
#import random

import asyncio
from email.mime import message
from fileinput import filename
import os as _os
from random import random
import shutil as _shutil
import json
import logging
import sys
import threading
import yaml
import time
from datetime import datetime

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

#cap-lib-Done:
from swch_capreg import SwChCapacityRegistry
# capreg.initialize_capacity_from_file("sztaki-capacity-raw.yaml")
#




class ResourceAgent:
    """Resource Agent for evaluating and responding to resource requests"""

    def __init__(self, config_file: str, capacity_file: Optional[str] = None):
        """Initialize Resource Agent with configuration files"""
        self.resource_lock = threading.Lock() # lock for synchronizing access to shared resource data structures
        self.config_file = config_file
        self.capacity_file = capacity_file
        self.config = self._load_config(config_file)
        # cap-lib-Done: replace capacity registeration
        print(f"[DEBUG] Initializing capacity registry for RA {self.config.get('RA_id')}")  
        self.capreg = SwChCapacityRegistry(self.config.get('RA_id'))
        with open(self.capacity_file) as stream:
            try:
                capacity_content = stream.read()
            except yaml.YAMLError as exc:
                print(exc)
        self.capreg.initialize_capacity_by_content(capacity_content)
        
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
        self.ssh_user = self.config.get('ssh_user', '')
        self.aws_ami = self.config.get('aws_ami', '')
        self.openstack_image_id = self.config.get('openstack_image_id', '')
        self.openstack_network_id = self.config.get('openstack_network_id', '')
        self.edge_device_ip = self.config.get('edge_device_ip', '')

        # print(f"[DEBUG]SSH user is {self.ssh_user}")
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

    def _register_message_handlers(self):
        """Register handlers for different message types"""
        self.peer.register_message_handler("MSG_JOB_STATUS_QUERY", self._handle_job_status_query)
    #    self.peer.register_message_handler("MSG_GETSTATE", self._handle_getstate)
        self.peer.register_message_handler("MSG_RESOURCE_QUERY", self._handle_resource_query)
        self.peer.register_message_handler("MSG_HEARTBEAT", self._handle_heartbeat)
        self.peer.register_message_handler("MSG_JOB_SUBMIT", self._handle_job_submit)
        self.peer.register_message_handler("MSG_JOB_DELETE", self._handle_job_delete)
        self.peer.register_message_handler("MSG_JOB_BROADCAST", self._handle_job_broadcast)
        self.peer.register_message_handler("MSG_RESOURCE_RESPONSE", self._handle_resource_response)
        self.peer.register_message_handler("MSG_SELECTED_OFFER", self._handle_selected_offer)
        self.peer.register_message_handler("MSG_CREATE_RESOURCE", self._handle_create_resource)
        self.peer.register_message_handler("MSG_CREATE_LEAD_RESOURCE", self._handle_create_lead_resource)
        self.peer.register_message_handler("MSG_DELETE_JOB_BROADCAST", self._handle_delete_job_broadcast)
        #self.peer.register_message_handler("MSG_MASTER_INFO", self._handle_master_info)
        self.peer.register_message_handler("MSG_MASTER_INFO", self._handle_master_info_cb)


    def _handle_delete_job_broadcast(self, peer_id: str, message: Dict[str, Any]):
        """Handle job deletion broadcast from hub RA"""
        job_id = message.get('job_id')
        offers_all = self.capreg.resource_offer_query_all(job_id)
        self.capreg.resources_and_offers_destroy_all(job_id)
        self.capreg.dump_capacity_registry_info()
    
    
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


    def _handle_job_status_query(self, peer_id: str, message: Dict[str, Any]):
        """Handle job status query requests"""
        self.logger.info(f"Received job status query from {peer_id}")
        job_id = message.get('job_id', 'unknown')
        response = {
            "job_id": job_id,
            "ra_id": self.ra_id,
            "state": self.job_states.get(job_id, {}).get("state", "unknown"),
            "resources_available": True,
            "queue_length": 0
        }
        self.peer.send(peer_id, "MSG_STATE_INFO", response)
        self.logger.info(f"Sent job status for {job_id} to {peer_id}")

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

        # TODO: as soon as job is received, job id should be created
        client_id = message.get('client_id')
        job_id = (datetime.now().strftime("%Y%m%d_%H%M%S.%f")[:-3] + "_"+ client_id)
        self.job_states[job_id] = {}
        self._update_job_state(job_id, "Pending")
        self.job_clients[job_id] = message.get('client_id')


        if client_id:
            print("Sending SWARM ID response to client:", self.job_clients[job_id])
            submit_response_message = {
                    "swarm_id": job_id,
                    "ra_id": self.ra_id,
                    "result": "SWARM_ID_ASSIGNED",
                    "message": "SWARM ID assigned successfully, now processing the application submission"
                    }
            self.peer.send(client_id, "MSG_SWARM_ID_RESPONSE", submit_response_message)        
        
        ask_yaml = message.get('tosca')
        # initialise application tosca
        self.job_tosca[job_id] = ask_yaml

        write_yaml(ask_yaml, 'tosca.yaml')
	    # Ze-done: Using TOSCA library to validate and parse the tosca then extract resource requirements 
        try:
            # 1) (done) validate and parse
            self.tosca[job_id] = Sardou('tosca.yaml') #(to validate, may fail if invalid)
            print(f"✅ Successfully validated submitted application tosca for job {job_id}")
            
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
                    # cap-lib-TODO: replace requirements with tosca
                    "ask_yaml" : self.job_tosca[job_id], #"tosca.yaml", #/ rm ask_yaml = self.tosca[job_id].get_requirements()
                    #"ask_yaml": ask_yaml,
                    "timestamp": message.get('timestamp'),
                    "hub_ra": self.peer.peer_id
                    #"hub_ra": self.ra_id
                }

                # Broadcast to all other RAs
	            # Ze-TODO: modify this, to use broadcast method
                for ra_id in other_ras:
                    self.peer.send(ra_id, "MSG_JOB_BROADCAST", broadcast_message)
                    self.logger.info(f"Broadcasted application to {ra_id}")
                        # TODO: at here create a folder to store TOSCA

                save_path = f"./KB/tosca_{job_id}.yaml"
                with open(save_path, 'w') as f:
                    yaml.dump(self.job_tosca[job_id], f)
                print(f"✅ Successfully saved TOSCA file for job {job_id} at {save_path}")

                # Process locally as well
                self._process_job_requirements(job_id, client_id, save_path, self.peer.peer_id)            
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
        if job_id not in self.job_offers:
            self.logger.exception(
                    f"Job {job_id} not found for deletion"
                )
            client_id = self.job_clients.get(job_id)
            if client_id:
                print("Sending delete response failure message to client:", client_id)
                delete_response_message = {
                        "job_id": job_id,
                        "ra_id": self.ra_id,
                        "result": "failure",
                        "message": "Failed to delete job, job not found"
                        }
                self.peer.send(client_id, "MSG_DELETE_RESPONSE", delete_response_message)                
                return None


        msg_delete_job = {
                    "job_id": job_id,
                    "timestamp": message.get('timestamp'),
                    "hub_ra": self.peer.peer_id
        }
        all_ras = self.peer.find_peers({"peer_type": "RA"})
        all_ras += [self.ra_id] # add the main RA to the list of RAs to be informed, because the main RA also needs to update its capacity status based on the job deletion
        for ra_id in all_ras:
            self.peer.send(ra_id, "MSG_DELETE_JOB_BROADCAST", msg_delete_job)
            self.logger.info(f"Broadcasted job deletion request to {ra_id}")
        #self._delete_job(job_id)
        CLUSTER_NAME = job_id
        swarmchestrate = Swarmchestrate(template_dir="templates", output_dir="output")
        swarmchestrate.destroy(CLUSTER_NAME)
        
        self.logger.info(f"Job {job_id} deleted successfully")


    def _handle_job_broadcast(self, peer_id: str, message: Dict[str, Any]):
        """Handle job broadcast from hub RA"""
        self.logger.info(f"Received application resource requirement broadcast from hub {peer_id}")

        job_id = message.get('job_id')
        client_id = message.get('client_id')
        ask_yaml = message.get('ask_yaml')
        save_path = f"./KB/tosca_{job_id}.yaml"
        with open(save_path, 'w') as f:
            yaml.dump(ask_yaml, f)
        print(f"✅ Successfully saved TOSCA file for job {job_id} at {save_path}")
        hub_ra = message.get('hub_ra')
        all_ras = self.peer.find_peers({"peer_type": "RA"})

        # Process job requirements
        self._process_job_requirements(job_id, client_id, save_path, hub_ra)

    # cap-lib-DONE: replace this _process_job_requirements func to support cap-lib
    def _process_job_requirements(self, job_id: str, client_id: str, ask_yaml: str, hub_ra: str):
        self.logger.info(f"RA: {self.ra_id} Evaluating application {job_id} requirements")

        if not self.capacity:
            self.logger.warning("No capacity data available for evaluation")
            return

        self.capreg.dump_capacity_registry_info()
        offers = self.capreg.resource_offer_generate_from_SAT_file(job_id, ask_yaml)
        print(yaml.dump(offers))
    # Ze-comment: by far each RA returns its offer
    # offers should be sent to the main RA now!
       # Send consolidated response to client
        response_message = {
           "job_id": job_id,
           "ra_id": self.ra_id,
           "provider": self.capacity.get('metadata', {}).get('resource-provider'),
           "timestamp": time.time(),
           # cap-lib-TODO: replace resource_responses with offers, to achieve this, one need to output and compare them
           "responses": offers
        }

        all_ras = self.peer.find_peers({"peer_type": "RA"})
        self.peer.send(hub_ra, "MSG_RESOURCE_RESPONSE", response_message)
    


    
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
            # cap-lib-Done: this function compiles all combinations based on individual response
            # a successful outcome of this function is the selected job offer, self.job_offers[job_id]
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
        #self.lead_resource[job_id] = next((k for k, v in self.job_offers[job_id].items() if v.get('ra_id') == 'ra-aws-cloud-us'), None)
        
        import random
        # 1. Look inside the nested offer to see if it has an ra_id
        valid = []
        for ms_id, offers in self.job_offers[job_id].items():
            # Get the first offer_id in this service
            for offer_id, data in offers.items():
                if data.get("ids", {}).get("ra_id"):
                    valid.append(ms_id)
                    break # Move to next microservice

        # 2. Pick a Lead Resource
        self.lead_resource[job_id] = random.choice(valid) if valid else None
        # 1. Look inside the nested offers to find the specific RA ID
        # This correctly handles: job_offers[job_id][ms_id][offer_id]['ids']['ra_id']
        self.lead_resource[job_id] = next(
            (ms_id for ms_id, offers in self.job_offers[job_id].items() 
            if any(data.get('ids', {}).get('ra_id') == 'ra-aws-cloud-us' for data in offers.values())), 
            #if any(data.get('ids', {}).get('ra_id') == 'ra-sztaki-cloud-hu' for data in offers.values())), 
            None
        )
        print(f"[DEBUG] lead_resource for job {job_id} is {self.lead_resource[job_id]}")
        # 3. Safely extract the details from the chosen Lead Resource
        selected_ms = self.lead_resource[job_id]
        if selected_ms:
            # Get the keys and ensure there is at least one offer
            offer_keys = list(self.job_offers[job_id][selected_ms].keys())
            if not offer_keys:
                print(f"[ERROR] Microservice {selected_ms} has no offers!")
                return
                
            offer_id = offer_keys[0]
            offer_data = self.job_offers[job_id][selected_ms][offer_id]
            
            # Using .get() for production safety
            ids = offer_data.get("ids", {})
            LR_id = ids.get("ra_id")
            provider = ids.get("provider_id")
            instance_type = ids.get("res_id") 
            
            print(f"[DEBUG] Lead Resource selected: {selected_ms} (RA: {LR_id})")
        else:
            print("[ERROR] No valid lead resource found!")
            return

        # cap-lib-DONE: Now, we should have selected an offer, it would be good to let individual RA know so that they can update capacity status
        # how to let them know? either sending a complete offer back with msg: update_capacity_status/the_selected_offer or send individual RA specific resource
        msg_selected_offer = {
                "job_id": job_id,
                "hub_ra": self.peer.peer_id,
                "timestamp": message.get('timestamp'),
                "offer_info": self.job_offers[job_id]
        }
            
        all_ras = self.peer.find_peers({"peer_type": "RA"})
        all_ras += [self.ra_id] # add the main RA to the list of RAs to be informed, because the main RA also needs to update its capacity status based on the selected offer
        print("all_ras in the network are: ", all_ras)
        for ra_id in all_ras:
            #print(f"Sending selected offer to RA {ra_id} from RA {self.ra_id}")
            self.peer.send(ra_id, "MSG_SELECTED_OFFER", msg_selected_offer)
            #print(f"Sent selected offer to RA {ra_id} from RA {self.ra_id}")
              


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

    
    # cap-lib-DONE: this function should be modified to create all combination
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
        resource_names = self._get_independent_microservices(f"./KB/tosca_{job_id}.yaml") # override resource_names with the independent microservices extracted from TOSCA
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
            
            # TODO: may need to put provider back 
            # row = f"{ra_id} ({provider})"[:29].ljust(30)
            row = f"{ra_id} "[:29].ljust(30)
            # implement logic that answer is yes if resource is in the response and has 'ids' and 'characteristics' keys, otherwise is no

            for resource_name in resource_names:
                answer = "No"
                if resource_name in responses:
                    resource_data = responses[resource_name]

                    # ignore colocated-only entries
                    if not ("colocated" in resource_data and len(resource_data) == 1):
                        if any(
                            isinstance(v, dict) and "ids" in v and "characteristics" in v
                            for v in resource_data.values()
                        ):
                            answer = "Yes"

                row += f"{answer}"[:14].ljust(15)
            print(row)

        print("\nFinding valid combinations...")
        print("=" * 60)
        #print(f"[DEBUG] resource_names: {resource_names}")
        # Find feasible resource combinations
        ra_responses = self._transform_ra_responses(ra_responses) # transform the ra_responses to make it easier to find combinations
        
        with open("ra_responses.json", "w") as f:
            json.dump(ra_responses, f, indent=2)

        valid_combinations = self._find_valid_combinations(ra_responses, resource_names)

        with open("valid_combinations__.json", "w") as f:
            json.dump(valid_combinations, f, indent=2)
        
        #filename = "valid_combinations.json"
        #with open(filename, "r") as f:
        #    valid_combinations = json.load(f)

        # print(f"[DEBUG] Testing valid combinations loaded from file: {filename}")
        
        if valid_combinations:
            print(f"Found {len(valid_combinations)} valid combination(s):")
            print("-" * 60)
            print("Possible offers:")
            
            # Use .values() to get the dictionary data, not just the "combination_1" string
            for i, combination in enumerate(valid_combinations.values(), 1):
                resource_items = []
                energy_consumption = 0
                total_bandwidth = 0
                total_price = 0

                # combination.keys() are now "details_v1", "ratings_v1", etc.
                for ms_id in sorted(combination.keys()):
                    # This is the inner dict (e.g., the "ra-fuelics..." key)
                    offers = combination[ms_id]
                    
                    for offer_id, data in offers.items():
                        ids = data['ids']
                        chars = data['characteristics']
                        
                        # Update totals using the 'characteristics' keys from your JSON
                        energy_consumption += chars.get('energy.consumption', 0)
                        total_price += chars.get('pricing.cost', 0)
                        
                        # Bandwidth is a string in some JSONs, ensure it's an int
                        total_bandwidth += int(chars.get('host.bandwidth', 0))
                        
                        ra_id = ids.get('ra_id', 'unknown')
                        resource_items.append(f"{ms_id}: {ra_id}")

                combo_str = f"{i}. " + ", ".join(resource_items)
                print(combo_str)
                print(f"   >> Total energy: {energy_consumption:.2f} | Bandwidth: {total_bandwidth} | Price: {total_price:.2f}")
            print("-" * 60)
            
            # Randomly select one combination
            # Ze：we will use AI algorithm to select the best combination instead of random selection
            #selected_index = random.randint(0, len(valid_combinations) - 1)
            
            # Using AI algorithm to select the best combination
            selected_index = self._rank_resource_offers(valid_combinations, job_id)
            # Convert the NumPy index to a standard Python list of keys
            combination_keys = list(valid_combinations.keys())

            # Ensure the index is a standard Python int, then get the key name
            selected_key = combination_keys[int(selected_index)]
            selected_combination = valid_combinations[selected_key]
            #selected_combination = valid_combinations[selected_index]
            
            print(f"\nSELECTED OFFER (chosen by the ranking algorithm: #{selected_index + 1}):")
            print("=" * 60)
            
            resource_items = []
            energy_consumption = 0
            total_bandwidth = 0
            total_price = 0
            for ms_id in sorted(selected_combination.keys()):
                offers = selected_combination[ms_id]
            
                # The JSON has an offer_id key (like 'ra-fuelics...') before the data
                for offer_id, data in offers.items():
                    ids = data.get('ids', {})
                    chars = data.get('characteristics', {})
                    
                    # Check for 'count' safely; use 1 as default if missing
                    count = data.get('count', 1) 
                    
                    ra_id = ids.get('ra_id', 'unknown')
                    
                    # Use the dot-notation keys from your actual JSON characteristics
                    energy_consumption += chars.get('energy.consumption', 0)
                    total_price += chars.get('pricing.cost', 0)
                    total_bandwidth += int(chars.get('host.bandwidth', 0))
                    
                    resource_items.append(f"{ms_id}: {ra_id}")

            
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


    def _transform_ra_responses(self,input_data):
        transformed = {}

        for original_ra_key, content in input_data.items():
            responses = content.get('responses', {})
            
            # Determine the target RA key from the actual data if possible
            # We look for the first microservice that has real offers
            target_ra_id = None
            for ms_id, offers in responses.items():
                if "colocated" not in offers:
                    first_offer = next(iter(offers.values()))
                    target_ra_id = first_offer.get('ids', {}).get('ra_id')
                    break
            
            # Fallback to the original key if no offers are found
            final_key = target_ra_id if target_ra_id else original_ra_key
            
            # Assign the stripped-down response directly
            transformed[final_key] = responses

        return transformed

    def _get_independent_microservices(self,file_path):
        """
            Ze: 
                This helper function identifies independent microservices as resources
        """
        import ruamel.yaml
        yaml = ruamel.yaml.YAML(typ='safe')
        with open(file_path, 'r') as f:
            data = yaml.load(f)

        # 1. Get all nodes that are of type swch:Microservice
        node_templates = data.get('service_template', {}).get('node_templates', {})
        all_ms = [
            name for name, node in node_templates.items()
            if node.get('type') == 'swch:Microservice'
        ]

        # 2. Identify services that are colocated (the "followers")
        policies = data.get('service_template', {}).get('policies', [])
        colocated_followers = set()

        for policy in policies:
            for policy_name, policy_details in policy.items():
                # Look for Colocation policies
                if policy_details.get('type') == 'swch:Scheduling.Colocation':
                    targets = policy_details.get('targets', [])
                    # If targets are [A, B], B is colocated with A.
                    # We only need a separate resource for A.
                    if len(targets) > 1:
                        colocated_followers.update(targets[1:])

        # 3. Filter out the followers from the main list
        independent_ms = [ms for ms in all_ms if ms not in colocated_followers]

        return sorted(independent_ms)

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
                # Change 'for combination in valid_combinations:' to:
        for combination_data in valid_combinations.values():
            total_energy = 0
            total_bandwidth = 0
            total_price = 0
            
            # Since your JSON is nested: ms_id -> offer_id -> data
            for ms_id, offers in combination_data.items():
                for offer_id, resource_data in offers.items():
                    # Access the 'characteristics' dictionary from your JSON
                    chars = resource_data.get('characteristics', {})
                    
                    # Match the key names exactly as they appear in your JSON (with dots)
                    total_energy += chars.get('energy.consumption', 0)
                    total_bandwidth += int(chars.get('host.bandwidth', 0))
                    total_price += chars.get('pricing.cost', 0)
            
            energy_list.append(total_energy)
            bandwidth_list.append(total_bandwidth)
            price_list.append(total_price)
            reliability_list.append(1) 
            latency_list.append(1)


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

    def _find_valid_combinations(self, offers_dict, resources_list):

        """Find all valid resource allocation combinations"""
            # 1. For each required resource, collect all concrete offers across all RAs
        import itertools
        #print(f"[DEBUG] offers_dict: {offers_dict}")
        offers_per_resource = {}
        for resource in resources_list:
            offers_per_resource[resource] = []
            for ra_id, ra_offers in offers_dict.items():
                if resource not in ra_offers:
                    continue
                resource_offers = ra_offers[resource]
                # Skip colocated entries (they have a single "colocated" key, not real offers)
                if "colocated" in resource_offers:
                    continue
                # Each remaining key is an offer_id mapping to offer details
                for offer_id, offer_data in resource_offers.items():
                    offers_per_resource[resource].append({offer_id: offer_data})

        # 2. Cartesian product across per-resource offer lists
        resource_keys = list(offers_per_resource.keys())
        offer_lists = [offers_per_resource[r] for r in resource_keys]
        combinations = list(itertools.product(*offer_lists))

        # 3. Format as numbered combinations dict
        result = {}
        for i, combo in enumerate(combinations, 1):
            combination = {}
            for resource, offer in zip(resource_keys, combo):
                combination[resource] = offer
            result[f"combination_{i}"] = combination

        return result


    # cap-lib-TODO:
    def _handle_selected_offer(self, peer_id, message):
        """
            Ze:
                This function takes the selected offer sent from the main RA, decide: 
                offer generated -> offer accept (reserved -> assigned)
                offer generated -> offer reject (reserve -> free)
                
                Note that when the application is deployed, 
                
                offer accept -> set deploy (assigned -> deployed)
                offer delete / reconfigured -> set undeploy (assigned -> undeploy)
        """
        self.logger.info(f"RA {self.ra_id} received the selected offer, now it will update the capacity registry accordingly")
        job_id = message.get('job_id')
        the_selected_offer = message.get('offer_info', {})
#        print(f"offer_info received by LR is {the_selected_offer}")

        all_offers = self.capreg.resource_offer_query_all(job_id)
        
#        print(f"[DEBUG]all_offers in capacity registry for job {job_id} is {all_offers}")

        self.capreg.dump_capacity_registry_info()
        # for all resources
        for ms_id in all_offers.keys():
            # for all offers in the resource
            for offer_id in all_offers[ms_id].keys():
                # compare whether it should be accepted or rejected
                for selected_ms, offers in the_selected_offer.items():
                    if selected_ms != ms_id:
                        continue
                    for selected_offer_id, data in offers.items():
                        offer = all_offers[ms_id][offer_id]
                        if selected_offer_id == offer_id:
                            self.capreg.resource_offer_accept(offer_id, offer)
                        else:
                            self.capreg.resource_offer_reject(offer_id, offer)


        self.capreg.dump_capacity_registry_info()


    def _handle_create_lead_resource(self, peer_id, message):
        """
            Ze:
            The RA which receives this msg will create the lead resource (LR) VM, k3s cluster, and return the master info to the hub RA.
        """
        self.logger.info(f"RA {self.ra_id} receives create lead resource request from {peer_id}")
        job_id = message.get('job_id')

        LR = message.get('lead_resource')
        lead_resource_name = message.get('leader_resource_name')
        #print(f"[DEBUG]lead_resource_name is {lead_resource_name}")
        instance = message.get('instance', {})
        instance_type = instance["instance_type"]
        #print(f"[DEBUG]instance_type is {instance_type}")
        k3s_role = instance["k3s_role"]
        node_name = instance["node-name"]
        #print(f"[DEBUG]node_name is {node_name}")
        tosca = message.get('tosca', {})
        cloud = instance["cloud"]
        #print(f"[DEBUG]cloud is {cloud}")
        #cloud = "openstack"
        #instance_type = "m2.small"
        #print(f"instance is {instance}")
        offer_info = message.get('offer_info', {})
        #print(f"offer_info received by LR is {offer_info}")

        print("Press a key to continue:")


        key_to_continue = input()

        # Ze-done: finish the RA which receives the msg and to create a VM
        if(LR):
	    # Ze: if it is the lead resource,
            # 1. creates the LR VM
            # 2. k3s cluster
            # Ze-done; make sure them can be correctly loaded on all clouds (sztaki, edge, aws_us)

            ports = json.dumps([
                {
                    "from": 0,
                    "to": 65535,
                    "protocol": "tcp",
                    "source": "0.0.0.0/0"
                },
                {
                    "from": 0,
                    "to": 65535,
                    "protocol": "udp",
                    "source": "10.0.0.0/16"
                }
            ])
            # For future automation, we need to make sure each RA has the required ssh key pair, security group, ami, etc for each provider.
            master_node_aws = (
                f'{{"cloud": "{cloud}",' # Ze: we can make it dynamic fetch from offer. Each RA could access multiple providers so this cannot be collected from config file
                f'"instance_type": "{instance_type}",'
                f'"ha": false,'
                f'"cluster_name": "{job_id}",'
                f'"ami": "{self.aws_ami}",' # Ze: we can make it dynamic later (from capacity/config info) does each provider has its own ami?
                f'"security_group_id": "",' # Ze: we can make it dynamic later from cluster-builder lib
                f'"resource_name":"{node_name}",' # Ze: to think about how to name
                f'"ssh_user": "{self.ssh_user}",' # Ze: we can make it dynamic later (from capacity/config info) does each provider has its own ssh user?
            #    f'"ssh_key_name": "",' # Ze: we can make it dynamic later (from capacity/config info) Does each provider has its own key pair?
                f'"ssh_key": "{self.ssh_key_path}",' # Ze: we can make it dynamic later (from capacity/config info) does each provider has its own private key?
                f'"k3s_role": "{k3s_role}",' # Ze: this should be default 
                f'"custom_ingress_ports": {ports}}}'
                )   

            master_node_openstack = (
                f'{{"cloud": "{cloud}",'
                f'"openstack_flavor_id": "{instance_type}",'
                f'"ha": false,'
                f'"openstack_image_id": "{self.openstack_image_id}",'
                f'"security_group_id": "",'
                f'"volume_size": "10",'
                #f'"floating_ip_pool": "ext-net",'
                f'"network_id": "{self.openstack_network_id}",'
                f'"cluster_name": "{job_id}",'
                f'"resource_name":"{node_name}",'    
                f'"ssh_user": "{self.ssh_user}",'
                #f'"ssh_key_name": "",'
                f'"ssh_key": "{self.ssh_key_path}",'
                f'"use_block_device": true,'
                f'"k3s_role": "{k3s_role}"}}'
            )
            master_node_edge = (
                f'{{"cloud": "{cloud}",'
                f'"edge_device_ip": "{self.edge_device_ip}",'
                f'"ha": false,'
                f'"cluster_name": "{job_id}",'
                f'"resource_name":"{node_name}",'
                f'"ssh_user": "{self.ssh_user}",'
                f'"ssh_key": "{self.ssh_key_path}",'
                f'"ssh_auth_method": "key",'
                f'"k3s_role": "{k3s_role}"}}'
            )
            master_node = {
                "aws": master_node_aws,
                "openstack": master_node_openstack,
                "sztaki": master_node_openstack,  # Add sztaki here
                "edge": master_node_edge
            }[cloud]
            master_node = json.loads(master_node)

            swarmchestrate = Swarmchestrate(template_dir="templates", output_dir="output")
            outputs = swarmchestrate.add_node(master_node)

            # Add logic to update resource status in the registry based on the result of node creation
            # cap-lib-DONE: assigned -> allocated          
            
            offers_all = self.capreg.resource_offer_query_all(job_id)
            for msid in offers_all.keys():
                if msid == node_name:
                    offerid=list(offers_all[msid].keys())[0]
                    res_set = self.capreg.resource_set_get_from_offer(offerid, offers_all[msid][offerid])
                    if res_set is not None:
                        self.capreg.resource_set_deployed(job_id, msid, res_set["restype"], res_set["resid"], res_set["count"])
            self.capreg.dump_capacity_registry_info()

            k3s_token = outputs.get("k3s_token")
            cluster_name = outputs.get("cluster_name")
            master_ip = outputs.get("master_ip")

            print(f"[DEBUG] master ip is {master_ip}")

            
            # Ze-done: Prepare configmap of tosca file for SA
            # Ze: we have three folders to create here: KB/, k3s/, k3s-{job_id}/
            #     1) KB/ acts as knowledge base and stores the tosca file
            #     2) k3s/ stores default manifests for deploying SA and other, i.e., namespace, daemonset, rbac, k3s-dashboard
            #     3) k3s-{job_id}/ stores all manifests for deploying SA for this job, it copies from k3s/ and adds two configmaps: tosca configmap and SA configmap  
            #        a) tosca configmap: contains the tosca file for this job
            #        b) SA configmap: contains the SA configuration info

            folder_path = f"KB"
            import os
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
            
            # Ze:TODO: translate tosca -> k3s manifest, this should be done in SA, but it requires puccini installation
            self.logger.info("Converting Tosca into k3s manifests.")
            #tpl = parse_tosca(self.tosca_path)

            from ruamel.yaml import YAML
            from sardou.manifestGenerator import get_kubernetes_manifest
            
            yaml_parser = YAML()
            yaml_parser.default_flow_style = False

            TOSCA_FILE = f"KB/{job_id}_tosca.yaml"
            OUTPUT_FILE = f"k3s-{job_id}/application-manifest.yaml"
            IMAGE_PULL_SECRET = "regcred"

            path = Path(TOSCA_FILE)
            if not path.exists():
                sys.exit(f"Error: TOSCA file '{TOSCA_FILE}' not found.")

            try:
                manifests = get_kubernetes_manifest(TOSCA_FILE, image_pull_secret=IMAGE_PULL_SECRET)

                if not manifests:
                    sys.exit("Warning: No Kubernetes manifests generated.")
                with open(OUTPUT_FILE, "w") as f:
                    yaml_parser.dump_all(manifests, f)
            except Exception as e:
                sys.exit(f"Error: {e}")

            print(f"✅ Kubernetes manifests written to '{OUTPUT_FILE}' ({len(manifests)} items)")


            # Ze-done: Create registry secret on the LR using cluster-builder library
            registry_config = {
                "master_ip": master_ip,
                "ssh_user": self.ssh_user, #Ze-TODO: ubuntu for openstack
                "ssh_private_key_path": self.ssh_key_path,
                "secret_names": ["regcred"] #optional
                #"namespace":"test" , #optional
            }
 
            # Run the registry secret creation
            swarmchestrate = Swarmchestrate(template_dir="templates", output_dir="output")
            swarmchestrate.create_registry_secrets(registry_config)

            # Use absolute path to ensure OpenTofu can find it from any directory
            absolute_path = os.path.abspath(f"k3s-{job_id}")

            # copy the manifests from k3s-{job_id}/ to the LR
            manifest_cfg = (
                f'{{"manifest_folder": "{absolute_path}",'
#                f'{{"manifest_folder": "/home/ubuntu/e2e-demo/k3s-{job_id}",'

                f'"master_ip": "{master_ip}",'
                f'"ssh_key_path": "{self.ssh_key_path}",'
                f'"ssh_user": "{self.ssh_user}"}}'
                #f'"ssh_user": "ec2-user"}}'
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
 
    async def _handle_master_info(self, peer_id, message):
        """Process master info from lead resource"""
        self.logger.info(f"RA {self.ra_id} receives master info from {peer_id}")
        import asyncio
        job_id = message.get("job_id")
        master_info = message.get("master_info", {})

        k3s_token = master_info["k3s_token"]
        cluster_name = master_info["cluster_name"]
        master_ip = master_info["master_ip"]

        # decrement lead resource offer count while we fan out worker creates
        # [Ze-DEBUG]
        # self.job_offers[job_id][self.lead_resource[job_id]]["count"] -= 1
        offer_info = self.job_offers[job_id]

        tasks = []
        for res, res_info in offer_info.items():
            # [Ze-DEBUG
            # if res_info["count"] <= 0:
            #    continue

            # [Ze-DEBUG]
                # 1. Get the dictionary containing the actual data (ids/characteristics)
            # This skips over the long "ra-aws-edge-uk_job_..." key
            offer_data = next(iter(res_info.values()))
            
            # 2. Reach into the "ids" block to get the ra_id
            ra_id = offer_data["ids"]["ra_id"]
            print(f"Service: {res} | RA ID: {ra_id}")
            #resource = offer_data["ids"]["res_id"]

            if res == self.lead_resource[job_id]:
                print(f"Skipping lead resource {res} with RA ID {ra_id}")
                continue

            # ra_id = res_info["ra_id"]
            # print(f"ra_id in offer_info is {ra_id}")

            msg_create_resource = {
                "job_id": job_id,
                "hub_ra": self.peer.peer_id,
                "lead_resource": False,
                "timestamp": message.get("timestamp"),
                "instance": {
                    "resource": res_info,
                    "k3s_role": "worker",
                    "node-name": res,  # res is already the key / node name
                },
                "master_info": {
                    "k3s_token": k3s_token,
                    "cluster_name": cluster_name,
                    "master_ip": master_ip,
                },
            }
            print(f"[DEBUG] Sending create resource for {res} to RA {ra_id} with message: {msg_create_resource}")
            # Approach 2: peer.send is blocking -> run it in a thread, schedule concurrently
            tasks.append(
                asyncio.create_task(
                    asyncio.to_thread(self.peer.send, ra_id, "MSG_CREATE_RESOURCE", msg_create_resource)
                )
            )

        # If you want "non-blocking" as in "don't wait at all", comment this out.
        # Keeping it ensures sends are dispatched before we update state.
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        # restore lead count & update state
        # Ze-DEBUG 
        #self.job_offers[job_id][self.lead_resource[job_id]]["count"] += 1
        self._update_job_state(job_id, "Running")

    # sync wrapper for the library
    def _handle_master_info_cb(self, peer_id, message):
        import asyncio
        # If we're already in an event loop (typical), schedule it
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # If no loop is running (rare), run it to completion
            asyncio.run(self._handle_master_info(peer_id, message))
            return

        task = loop.create_task(self._handle_master_info(peer_id, message))

        # optional: log exceptions instead of "Task exception was never retrieved"
        def _log_task_result(t: asyncio.Task):
            exc = t.exception()
            if exc:
                self.logger.exception("Error in _handle_master_info", exc_info=exc)

        task.add_done_callback(_log_task_result)
        
    def _handle_create_resource(self, peer_id, message):
        # import threading
        # thread = threading.Thread(
        #     target=self._handle_create_resource_blocking,
        #     args=(peer_id, message),
        #     daemon=True,
        # )
        # thread.start()

        import threading

        def locked_execution(p_id, msg):
            # This ensures only one thread runs the blocking logic at a time
            with self.resource_lock:
                self._handle_create_resource_blocking(p_id, msg)

        thread = threading.Thread(
            target=locked_execution,
            args=(peer_id, message),
            daemon=True,
        )
        thread.start()

    def _handle_create_resource_blocking(self, peer_id, message):
        """Process create resource request from LRA"""
        self.logger.info(f"RA {self.ra_id} receives create resource request from {peer_id}")
        job_id = message.get('job_id')
        instance = message.get('instance', {})
        offer_data = next(iter(instance["resource"].values()))
    
        # 2. Reach into the "ids" block to get the ra_id
        instance_type = offer_data["ids"]["res_id"]
        #instance_type = instance["resource"]["instance_type"]
        k3s_role = instance["k3s_role"]
       #resource_name = instance["node-name"]
        resource_name = offer_data["ids"]["ms_id"]
        self.master_info = message.get('master_info') # Ze-TODO: master info should be job_id specific
        cluster_name = self.master_info["cluster_name"]
        master_ip = self.master_info["master_ip"]
        k3s_token = self.master_info["k3s_token"]
        print(f"[DEBUG] instance_type is {instance_type}, k3s_role is {k3s_role}, resource_name is {resource_name}, cluster_name is {cluster_name}, master_ip is {master_ip}, k3s_token is {k3s_token}")
        for i in range(1):
        
        #for i in range(instance["resource"]["count"]):
        #    cloud = instance["resource"]["provider"]
            cloud = offer_data["ids"]["provider_id"]
        #    if instance["resource"]["count"] >1:
        #        node_name = f"{resource_name}-{i+1}"
        #    else:
            node_name = resource_name
            worker_node_aws = (
                    f'{{"cloud": "{cloud}",' # Ze: we can make it dynamic fetch from offer. Each RA could access multiple providers so this cannot be collected from config file
                    f'"instance_type": "{instance_type}",'
                    f'"ha": false,'
                    f'"ami": "{self.aws_ami}",' # Ze: we can make it dynamic later (from capacity/config info) does each provider has its own ami?
                    f'"security_group_id": "",' # Ze: we can make it dynamic later from cluster-builder lib
                    f'"resource_name":"{node_name}",' # Ze: to think about how to name
                    f'"ssh_user": "{self.ssh_user}",' # Ze: we can make it dynamic later (from capacity/config info) does each provider has its own ssh user?
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
                    f'"ssh_user": "{self.ssh_user}",'
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
                    f'"ssh_user": "{self.ssh_user}",'
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
            print(f"ssh_user is {self.ssh_user}")
            
            
            worker_node = json.loads(worker_node)
            swarmchestrate = Swarmchestrate(template_dir="templates", output_dir="output")
            swarmchestrate.add_node(worker_node)

            offers_all = self.capreg.resource_offer_query_all(job_id)
            for msid in offers_all.keys():
                if msid == node_name:
                    offerid=list(offers_all[msid].keys())[0]
                    res_set = self.capreg.resource_set_get_from_offer(offerid, offers_all[msid][offerid])
                    if res_set is not None:
                        self.capreg.resource_set_deployed(job_id, msid, res_set["restype"], res_set["resid"], res_set["count"])
            self.capreg.dump_capacity_registry_info()
        

	# # Ze-done: finish the RA which receives the msg and to create a VM
    #     self.logger.info(f"RA {self.ra_id} instantiates resource {resource_name} for job {job_id}")

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


