"""
Base Resource Agent (RA) implementation
Handles P2P communication and resource matching
"""
import json
import logging
import yaml
import time
from typing import Dict, Any, Optional, List
from pathlib import Path
from offer_evaluator import OfferEvaluator


import random
from itertools import product

from swchp2pcom import SwchPeer
from capability_evaluator import can_fulfill_requirement, get_matching_instances

from cluster_builder import Swarmchestrate


class ResourceAgent:
    """Resource Agent for evaluating and responding to resource requests"""

    def __init__(self, config_file: str, capacity_file: Optional[str] = None):
        """Initialize Resource Agent with configuration files"""
        self.config_file = config_file
        self.capacity_file = capacity_file
        self.config = self._load_config(config_file)
        self.capacity = self._load_config(capacity_file) if capacity_file else {}
        # job_responses collect RAs' responses to a job request [job_id][responses]
        self.job_responses = {}
        # job_offer stores the offer that fulfills a job request [job_id][]
        self.job_offers = {}
        self.master_info = {}
        # Extract configuration values
        self.ra_id = self.config.get('RA_id')
        self.universe_id = self.config.get('universe_id')
        self.api_port = self.config.get('api_port')
        self.p2p_port = self.config.get('p2p_port')
        self.domain = self.config.get('domain', '0.0.0.0')
        self.bootstrap_peers = self.config.get('bootstrap_peers', [])
        self.credentials = self.config.get('credentials', {})

        # Initialize P2P communication
        self.peer = None
        self.is_running = False

        # Setup logging
        self._setup_logging()

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

    def _register_message_handlers(self):
        """Register handlers for different message types"""
        self.peer.register_message_handler("MSG_SUBMIT", self._handle_submit)
        self.peer.register_message_handler("MSG_GETSTATE", self._handle_getstate)
        self.peer.register_message_handler("MSG_RESOURCE_QUERY", self._handle_resource_query)
        self.peer.register_message_handler("MSG_HEARTBEAT", self._handle_heartbeat)
        self.peer.register_message_handler("MSG_JOB_SUBMIT", self._handle_job_submit)
        self.peer.register_message_handler("MSG_JOB_BROADCAST", self._handle_job_broadcast)
        self.peer.register_message_handler("MSG_RESOURCE_RESPONSE", self._handle_resource_response)
        self.peer.register_message_handler("MSG_CREATE_RESOURCE", self._handle_create_resource)
        self.peer.register_message_handler("MSG_MASTER_INFO", self._handle_master_info)

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
        app_id = message.get('appid', 'unknown')
        response = {
            "appid": app_id,
            "ra_id": self.ra_id,
            "state": "running",
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
        self.logger.info(f"Received job submission from {peer_id}")

        job_id = message.get('job_id')
        ask_yaml = message.get('ask_yaml')
        client_id = message.get('client_id')
        all_ras = self.peer.find_peers({"peer_type": "RA"})
        if not ask_yaml:
            self.logger.error("No ask_yaml data in job submission")
            return

        # Hub RA processes and broadcasts job
        if not self.bootstrap_peers:
            self.logger.info(f"Broadcasting job {job_id} to all RAs")

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
            for ra_id in other_ras:
                self.peer.send(ra_id, "MSG_JOB_BROADCAST", broadcast_message)
                self.logger.info(f"Broadcasted job to {ra_id}")

            # Process locally as well
            self._process_job_requirements(job_id, client_id, ask_yaml, self.ra_id)
        else:
            self.logger.warning("Non-hub RA received direct job submission")

    def _handle_job_broadcast(self, peer_id: str, message: Dict[str, Any]):
        """Handle job broadcast from hub RA"""
        self.logger.info(f"Received job broadcast from hub {peer_id}")

        job_id = message.get('job_id')
        client_id = message.get('client_id')
        ask_yaml = message.get('ask_yaml')
        hub_ra = message.get('hub_ra')
        all_ras = self.peer.find_peers({"peer_type": "RA"})

        # Process job requirements
        self._process_job_requirements(job_id, client_id, ask_yaml, hub_ra)

    def _process_job_requirements(self, job_id: str, client_id: str, ask_yaml: Dict, hub_ra: str):
        """Process job requirements against RA capacity"""
        self.logger.info(f"RA: {self.ra_id} Evaluating job {job_id} requirements")

        if not self.capacity:
            self.logger.warning("No capacity data available for evaluation")
            return

        # Evaluate each resource request
        resource_responses = {}

        for resource_name, resource_requirements in ask_yaml.items():
            if not isinstance(resource_requirements, dict):
                continue

            self.logger.info(f"Evaluating requirements for {resource_name}")

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
                    "provider": self.credentials.get('provider'),
                    "resource_provider": self.capacity.get('metadata', {}).get('resource-provider'),
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

        # Send consolidated response to client
        response_message = {
            "job_id": job_id,
            "ra_id": self.ra_id,
            "provider": self.credentials.get('provider'),
            "timestamp": time.time(),
            "responses": resource_responses
        }

        all_ras = self.peer.find_peers({"peer_type": "RA"})

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

        for instance_type in suitable_instances:
            available_quota = our_quota.get(instance_type, 0)
            if available_quota >= count:
                return True

        return False

    def _create_bid(self, resource_name: str, capabilities: Dict, count: int) -> Dict:
        """Create bid information for resource"""
        suitable_instances = get_matching_instances(capabilities, self.capacity)
        #print(f"capabilities are: {capabilities}")
        #print(f"\n\n\ncapacity is: {self.capacity}")
        if not suitable_instances:
            return {}

        # Find most cost-effective instance
        # Ze-DONE: we should use the smallest instance that fulfills the requirements.
        our_pricing = self.capacity.get('pricing', {})
        best_instance = min(suitable_instances, key=lambda x: our_pricing.get(x, float('inf')))
        best_cost = our_pricing.get(best_instance, 0)

        return {
            "instance_type": best_instance,
            "cost_per_hour": best_cost,
            "total_cost_per_hour": best_cost * count,
            "currency": "credits",
            "count": count,
            "setup_fee": 0,
            "minimum_duration": "1 hour",
            "energy-consumption": self.capacity['capacity']['instances'][best_instance]['energy-consumption'],
            "bandwidth": self.capacity['capacity']['instances'][best_instance]['bandwidth']
        }

    def _create_resource_definition(self, resource_name: str, capabilities: Dict, count: int) -> Dict:
        """Create resource definition for response"""
        suitable_instances = get_matching_instances(capabilities, self.capacity)
        if not suitable_instances:
            return {}

        best_instance = suitable_instances[0]
        our_instances = self.capacity.get('capacity', {}).get('instances', {})
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
        """Process resource response from RA"""
        job_id = message.get('job_id')
        ra_id = message.get('ra_id')
        provider = message.get('provider')
        responses = message.get('responses', {})

        if job_id not in self.job_responses:
            self.job_responses[job_id] = {}

        self.job_responses[job_id][ra_id] = {
            'provider': provider,
            'responses': responses
        }

        # Check if all RAs have responded
        all_ras = self.peer.find_peers({"peer_type": "RA"})
        if len(self.job_responses.get(job_id, {})) >= len(all_ras)+1:
            # Ze: at here, LRA compiles all possible offers based on responses.
            self._compile_and_display_results(job_id)
        if job_id not in self.job_offers:
            logging.error("No resources are available for job %s", job_id)
            return None

        # Ze: randomly select a resource's RA node as LR
        LR_index = random.randint(0, len(self.job_offers[job_id]) - 1)+1
        selected_resource = f"resource{LR_index}"
        LR_id = self.job_offers[job_id][selected_resource]["ra_id"]
        provider = self.job_offers[job_id][selected_resource]["provider"]
        instance_type = self.job_offers[job_id][selected_resource]["instance_type"]

        print(f"LR_index is {LR_index}, LR_id is {LR_id}, selected_resource is {self.job_offers[job_id][selected_resource]}")
	# Ze-TODO: define msg send to the RA which hosts the LR.
        msg_resource_request_ra = {
                "job_id": job_id,
                "hub_ra": self.peer.peer_id,
                "lead_resource": True, 
                "timestamp": message.get('timestamp'),
                "instance": { "instance_type": instance_type ,"k3s_role": "master","node-name": "lsa"}
                #"instance": { "cloud": provider ,"instance_type": instance_type ,"ssh_key_name": "g","ssh_user": "ec2-user","k3s_role": "master","ssh_private_key_path": "/home/ubuntu/test/g.pem","ami": "ami-00ca32bbc84273381"}
        }
        
        self.peer.send(LR_id, "MSG_CREATE_RESOURCE", msg_resource_request_ra)
        self.logger.info(f"Sent resource request to RA: {LR_id}")



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
        header = f"{'RA (Provider)':<20}"
        for resource_name in resource_names:
            header += f"{resource_name.title():<15}"
        print(header)
        print("-" * (20 + len(resource_names) * 15))

        # Create table rows
        for ra_id, ra_data in ra_responses.items():
            provider = ra_data['provider']
            responses = ra_data['responses']

            row = f"{ra_id} ({provider})"[:19].ljust(20)
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
            selected_index = self._rank_resource_offers(valid_combinations)
            #selected_index = random.randint(0, len(valid_combinations) - 1)
            selected_combination = valid_combinations[selected_index]
            
            print(f"\nSELECTED OFFER (Randomly chosen: #{selected_index + 1}):")
            print("=" * 60)
            
            resource_items = []
            energy_consumption = 0
            total_bandwidth = 0
            total_price = 0
            for resource_name in sorted(selected_combination.keys()):
                allocation = selected_combination[resource_name]
                ra_id = allocation['ra_id']
                energy_consumption += allocation['energy-consumption']
                total_bandwidth += allocation['bandwidth']
                total_price += allocation['cost_per_hour']
                resource_items.append(f"{resource_name}: {ra_id}")
            
            print(", ".join(resource_items))
            print(f", total energy consumption is: {energy_consumption:.2f}, total bandwidth is: {total_bandwidth}, total price is: {total_price}")
            print("=" * 60)
        else:
            print("No valid combinations found!")
            print("   No combination can fulfill all resource requirements.")

# Save valid_combinations to a JSON file
        with open("valid_combinations.json", "w") as f:
            json.dump(valid_combinations, f, indent=2)
        # Complete job processing
        time.sleep(1)
        self.job_complete = True
        if job_id not in self.job_offers:
            self.job_offers[job_id] = {}

        self.job_offers[job_id] = selected_combination
        print(f"job_offer for job {job_id} is {self.job_offers[job_id]}, size is {len(self.job_offers[job_id])}")
        #self.peer.leave().addCallback(lambda _: self.peer.stop())

    def _rank_resource_offers(self,valid_combinations):
        """Rank resource offers based on QoS attributes"""
        qos_priority = {
            "energy": 0.5,
            "bandwidth": 0.5,
            "latency": 0.5,
            "price": 0.5
        }
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
		# Ze: a combination is the resource fulfillment
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


    def _handle_create_resource(self, peer_id, message):
        """Process create resource request from LRA"""
        self.logger.info(f"RA {self.ra_id} receives create resource request from {peer_id}")
        job_id = message.get('job_id')

        LR = message.get('lead_resource')
        instance = message.get('instance', {})
        instance_type = instance["instance_type"]
        #node_name = instance["node_name"]

        print(f"instance is {instance}")
	# Ze-TODO: finish the RA which receives the msg and to create a VM
	# !!! What info is required is important
        if(LR):
	    # Ze: if it is the lead resource, it creates the LR VM, k3s cluster, deploy LSA, broadcast the cluster info.
            # Ze-TODO; make sure them can be corrected loaded on all clouds (sztaki, edge, aws_us)


            master_node = (
                f'{{"cloud": "aws","instance_type": "{instance_type}","ssh_key_name": "g", "resource_name":"lsa",'
                f'"ssh_user": "ec2-user","k3s_role": "master","ssh_private_key_path": "/home/ubuntu/.ssh/Ze_mac.pem",'
                #f'"ssh_user": "ec2-user","k3s_role": "master","ssh_private_key_path": "/home/ubuntu/test/g.pem",'
                f'"ami": "ami-00ca32bbc84273381"}}'
            )
            master_node = json.loads(master_node)

            swarmchestrate = Swarmchestrate(template_dir="templates", output_dir="output")
            outputs = swarmchestrate.add_node(master_node)

            k3s_token = outputs.get("k3s_token")
            cluster_name = outputs.get("cluster_name")
            master_ip = outputs.get("master_ip")
            node_name = outputs.get("node_name")
            # Ze-TODO 1) : deploy LSA, based on master_node, LSA should be able to load config files.
            # Ze-TODO 1a): prepare manifests:
	    # 1. ip address of the hub_ra
            # 2. node name of each resource
            # 3. image of application 
	    # application's tosca into SA's expected toscas and store them in config-map.
            manifest_cfg = (
                f'{{"manifest_folder": "/home/ubuntu/repo/swarm-agent/k3s",'
                f'"master_ip": "{master_ip}",'
                f'"ssh_key_path": "/home/ubuntu/.ssh/Ze_mac.pem",'
                f'"ssh_user": "ec2-user"}}'
            )
            # Load configuration
            cfg = json.loads(manifest_cfg)

            manifest_folder = Path(cfg["manifest_folder"])
            manifest_folder.exists() or exit(f"❌ Manifest folder does not exist: {manifest_folder}")

            # Run copy-manifest
            Swarmchestrate(template_dir="templates", output_dir="output").deploy_manifests(
            manifest_folder=str(manifest_folder),
            master_ip=cfg["master_ip"],
            ssh_key_path=cfg["ssh_key_path"],
            ssh_user=cfg["ssh_user"]
            )
            # Ze-(DONE) 2) ) : prepare master_output and send back to ra_hub.
            msg_master_info = {
                "job_id": job_id,
                "hub_ra": self.peer.peer_id,
                "lead_resource": True, 
                "timestamp": message.get('timestamp'),
                "master_info": { "k3s_token": k3s_token ,"cluster_name": cluster_name, "master_ip": master_ip, "node-name": node_name}
            }
        
            self.peer.send(peer_id, "MSG_MASTER_INFO", msg_master_info)

            print(f"Output from master node is: {outputs}")
            self.logger.info(f"RA {self.ra_id} instantiates the lead resource")
        else:
            self.logger.info(f"RA {self.ra_id} instantiates normal resource")
	    # Ze: it is not lead resource, create a VM, join the cluster
            master_node = f'{ "cloud": {provider}","instance_type": {instance['instance_type']},"ssh_key_name": "g","ssh_user": {ssh_user},"k3s_role": "master","ssh_private_key_path": {ssh_private_key_path},"ami": {ami}}'


    def _handle_resource_request(self, peer_id, message):
        """Process resource request from SA"""
        self.logger.info(f"RA {self.ra_id} receives resource request from {peer_id}")

	# Ze-TODO 3) : SA should just send resource 1/2/3.... 
	# LRA should identify the provider, the instance, and so on so forth
        resource_index = message.get('resource_index')
        sa_requested_resource = f"resource{resource_index}"

        ra_id = self.job_offers[job_id][sa_requested_resource]["ra_id"]
        provider = self.job_offers[job_id][sa_requested_resource]["provider"]
        instance_type = self.job_offers[job_id][sa_requested_resource]["instance_type"]

	# Ze-TODO: define msg send to a RA such that it can use it to create a VM.
        msg_resource_request_ra = {
                "job_id": job_id,
                "hub_ra": self.peer.peer_id,
                "lead_resource": True, 
                "timestamp": message.get('timestamp'),
                "instance": { "cloud": provider ,"instance_type": instance_type ,"k3s_role": "worker"}
        }
 
        self.peer.send(ra_id, "MSG_CREATE_RESOURCE", msg_resource_request_ra)
        self.logger.info(f"Sent resource request to RA: {LR_id}")


    def _handle_master_info(self, peer_id, message):
        """Process master info output from LR"""

        self.logger.info(f"RA {self.ra_id} receives master info output from LR: {peer_id}")
        self.master_info = message.get('master_info')

        cluster_name = self.master_info["cluster_name"]
        master_ip = self.master_info["master_ip"]
        k3s_token = self.master_info["k3s_token"]

        #Ze-TODO: this is just a try out to add the edge node as a worker
        worker_node_aws = (
                f'{{"cloud": "edge","edge_device_ip": "18.130.228.103", "resource_name":"sa-1",'
                f'"ssh_user": "ubuntu","k3s_role": "worker","ssh_private_key": "/home/ubuntu/.ssh/Ze_mac.pem",'
                f'"ssh_auth_method": "key",'
                f'"k3s_token": "{k3s_token}", "master_ip": "{master_ip}", "cluster_name": "{cluster_name}"}}'
        )

        worker_node_sztaki = (
                f'{{"cloud": "openstack","openstack_image_id": "b2be6f4e-ebd8-42af-a526-63691a4d90ea",'
                f'"openstack_flavor_id": "m2.small",'
                f'"ssh_key_name": "Ze_mac",'
                f'"volume_size": "10",'
                f'"k3s_role": "worker",'
                f'"ha": false,'
                f'"ssh_user": "ubuntu",'
                f'"ssh_private_key_path": "/home/ubuntu/.ssh/Ze_mac.pem",'
                f'"floating_ip_pool": "ext-net",'
                f'"network_id": "bbe042e4-91a1-4601-962f-14a31e5e2787",'
                f'"use_block_device": true, "resource_name":"sa-1",'
                f'"k3s_token": "{k3s_token}", "master_ip": "{master_ip}", "cluster_name": "{cluster_name}"}}'
        )
        worker_node = json.loads(worker_node_sztaki)
        swarmchestrate = Swarmchestrate(template_dir="templates", output_dir="output")
        outputs = swarmchestrate.add_node(worker_node)

        print(f"worker_node {worker_node}")


    def connect_to_network(self):
        """Connect to P2P network using bootstrap peers"""
        if not self.bootstrap_peers:
            self.logger.info("No bootstrap peers configured - running as hub")
            #self.peer.enter("172.31.40.7", 5000)
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
"""
        msg_resource_request_ra = {
                "job_id": job_id,
                "hub_ra": self.peer.peer_id,
                "lead_resource": True, 
                "timestamp": message.get('timestamp'),
		"instance": [{
  "nodes": [
    {
        "cloud": "aws",
        "instance_type": "t2.small",
        "ssh_key_name": "g",
        "ssh_user": "ec2-user",
        "k3s_role": "master",
        "ssh_private_key_path": "/home/ubuntu/test/g.pem",
        "ami": "ami-00ca32bbc84273381"
    }
]}]
                }
"""
"""
        aws_cloud_us = {
  "nodes": [
    {
        "cloud": "aws",
        "instance_type": "t2.small",
        "ssh_key_name": "g",
        "ssh_user": "ec2-user",
        "k3s_role": "worker",
        "ssh_private_key_path": "/home/ubuntu/test/g.pem",
        "ami": "ami-00ca32bbc84273381"
    }
]}
"""
# Ze-Reference
        #"instance": '{ "cloud": "edge","edge_device_ip": "18.130.228.103", "ssh_user": "ubuntu", "ssh_auth_method": "key", "ssh_private_key": "/home/ubuntu/test/g.pem","k3s_role": "master"}'
#        master_node = '{ "cloud": "aws","instance_type": "t2.micro","ssh_key_name": "g","ssh_user": "ec2-user","k3s_role": "master","ssh_private_key_path": "/home/ubuntu/test/g.pem","ami": "ami-00ca32bbc84273381"}'

"""
# Ze-TODO 1a): prepare manifests: application's tosca into SA's expected toscas and store them in config-map.
            manifest_cfg = (
                f'{{"manifest_folder": "/home/ubuntu/swarm-agent/k3s",'
                f'"master_ip": "{master_ip}",'
                f'"ssh_key_path": "/home/ubuntu/test/g.pem",'
                f'"ssh_user": "ec2-user"}}'
            )
            # Load configuration
            cfg = json.loads(manifest_cfg)

            manifest_folder = Path(cfg["manifest_folder"])
            manifest_folder.exists() or exit(f"❌ Manifest folder does not exist: {manifest_folder}")

            # Run copy-manifest
            Swarmchestrate(template_dir="templates", output_dir="output").deploy_manifests(
            manifest_folder=str(manifest_folder),
            master_ip=cfg["master_ip"],
            ssh_key_path=cfg["ssh_key_path"],
            ssh_user=cfg["ssh_user"]
            )
# sztaki openstack
        worker_node = (
                f'{{"cloud": "openstack","openstack_image_id": "b2be6f4e-ebd8-42af-a526-63691a4d90ea",'
                f'"openstack_flavor_id": "m2.small",'
                f'"ssh_key_name": "test",'
                f'"volume_size": "10",'
                f'"k3s_role": "worker",'
                f'"ha": false,'
                f'"ssh_user": "ubuntu",'
                f'"ssh_private_key_path": "/home/ubuntu/test/g.pem",'
                f'"floating_ip_pool": "ext-net",'
                f'"network_id": "bbe042e4-91a1-4601-962f-14a31e5e2787",'
                f'"use_block_device": true,'
                f'"security_group_id": "f05b97f0-140a-4d24-bfc6-3a197e842739",'
                f'"k3s_token": "{k3s_token}", "master_ip": "{master_ip}", "cluster_name": "{cluster_name}"}}'
        )
"""
