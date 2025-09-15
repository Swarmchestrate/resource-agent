"""
Base Resource Agent (RA) implementation
Handles P2P communication and resource matching
"""
import logging
import yaml
import time
from typing import Dict, Any, Optional, List
from pathlib import Path

import random
from itertools import product

from swchp2pcom import SwchPeer
from capability_evaluator import can_fulfill_requirement, get_matching_instances


class ResourceAgent:
    """Resource Agent for evaluating and responding to resource requests"""

    def __init__(self, config_file: str, capacity_file: Optional[str] = None):
        """Initialize Resource Agent with configuration files"""
        self.config_file = config_file
        self.capacity_file = capacity_file
        self.config = self._load_config(config_file)
        self.capacity = self._load_config(capacity_file) if capacity_file else {}
        self.job_responses = {}

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
        # Ze-TODO: we should use the smallest instance that fulfills the requirements.
        # We should add total energy consumption and bandwidth avaliablility into the responses.
        our_pricing = self.capacity.get('pricing', {})
        best_instance = min(suitable_instances, key=lambda x: our_pricing.get(x, float('inf')))
        best_cost = our_pricing.get(best_instance, 0)
        #print(f"\n\n\nbest instance is: {self.capacity['capacity']['instances'][best_instance]['energy-consumption']}")
        #print(f"\n\n\nbest instance is: {self.capacity['capacity']['instances'][best_instance]['bandwidth']}")

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
        print(f"the length of all_ras is {all_ras}, the number of received reponses is {len(self.job_responses.get(job_id, {}))}")
        if len(self.job_responses.get(job_id, {})) >= len(all_ras)+1:
            # Ze-TODO: at here, compute the resource response of the LRA, compile all possible offers.
            # 
            self._compile_and_display_results(job_id)

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
            
            energy_consumption = 0
            total_bandwidth = 0
            for i, combination in enumerate(valid_combinations, 1):
                combo_str = f"{i}. "
                
                resource_items = []
                for resource_name in sorted(combination.keys()):
                    allocation = combination[resource_name]
                    ra_id = allocation['ra_id']
                    energy_consumption += allocation['energy-consumption']
                    total_bandwidth += allocation['bandwidth']
                    resource_items.append(f"{resource_name}: {ra_id}")
                
                combo_str += ", ".join(resource_items)
                print(combo_str)
                print(f", total energy consumption is: {energy_consumption:.2f}, total bandwidth is: {total_bandwidth}")
            print("-" * 60)
            
            # Randomly select one combination
            selected_index = random.randint(0, len(valid_combinations) - 1)
            selected_combination = valid_combinations[selected_index]
            
            print(f"\nSELECTED OFFER (Randomly chosen: #{selected_index + 1}):")
            print("=" * 60)
            
            resource_items = []
            energy_consumption = 0
            total_bandwidth = 0
            for resource_name in sorted(selected_combination.keys()):
                allocation = selected_combination[resource_name]
                ra_id = allocation['ra_id']
                energy_consumption += allocation['energy-consumption']
                total_bandwidth += allocation['bandwidth']
                resource_items.append(f"{resource_name}: {ra_id}")
            
            print(", ".join(resource_items))
            print(f", total energy consumption is: {energy_consumption:.2f}, total bandwidth is: {total_bandwidth}")
            print("=" * 60)
        else:
            print("No valid combinations found!")
            print("   No combination can fulfill all resource requirements.")

        # Complete job processing
        time.sleep(1)
        self.job_complete = True
        #self.peer.leave().addCallback(lambda _: self.peer.stop())

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
