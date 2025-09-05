"""
Base Resource Agent (RA) implementation using Swarmchestrate P2P communication library
"""
import logging
import yaml
import asyncio
import time
from typing import Dict, Any, Optional
from pathlib import Path

from swchp2pcom import SwchPeer


class ResourceAgent:
    """
    Base Resource Agent class that handles P2P communication and resource management
    """
    
    def __init__(self, config_file: str, capacity_file: Optional[str] = None):
        """
        Initialize Resource Agent with configuration files
        
        Args:
            config_file: Path to RA configuration YAML file
            capacity_file: Path to RA capacity YAML file (optional)
        """
        self.config_file = config_file
        self.capacity_file = capacity_file
        self.config = self._load_config(config_file)
        self.capacity = self._load_config(capacity_file) if capacity_file else {}
        
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
        except FileNotFoundError:
            logging.error(f"Configuration file not found: {config_file}")
            return {}
        except yaml.YAMLError as e:
            logging.error(f"Error parsing YAML file {config_file}: {e}")
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
    
    def _handle_submit(self, peer_id: str, message: Dict[str, Any]):
        """Handle job submission requests"""
        self.logger.info(f"Received submit request from {peer_id}: {message}")
        
        # Process submission based on capacity and availability
        app_id = message.get('appid', 'unknown')
        
        # Send acknowledgment
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
        self.logger.info(f"Received state query from {peer_id}: {message}")
        
        app_id = message.get('appid', 'unknown')
        
        # Return current state
        response = {
            "appid": app_id,
            "ra_id": self.ra_id,
            "state": "running",
            "resources_available": True,
            "queue_length": 0
        }
        
        self.peer.send(peer_id, "MSG_STATE", response)
        self.logger.info(f"State information sent for {app_id}")
    
    def _handle_resource_query(self, peer_id: str, message: Dict[str, Any]):
        """Handle resource availability queries"""
        self.logger.info(f"Received resource query from {peer_id}: {message}")
        
        # Return capacity information
        response = {
            "ra_id": self.ra_id,
            "capacity": self.capacity.get('capacity', {}),
            "pricing": self.capacity.get('pricing', {}),
            "locality": self.capacity.get('locality', {}),
            "available": True
        }
        
        self.peer.send(peer_id, "MSG_RESOURCE_INFO", response)
        self.logger.info("Resource information sent")
    
    def _handle_heartbeat(self, peer_id: str, message: Dict[str, Any]):
        """Handle heartbeat messages"""
        self.logger.debug(f"Heartbeat from {peer_id}")
        
        # Send heartbeat response
        response = {
            "ra_id": self.ra_id,
            "status": "alive",
            "timestamp": message.get('timestamp')
        }
        
        self.peer.send(peer_id, "MSG_HEARTBEAT_ACK", response)
    
    def _handle_job_submit(self, peer_id: str, message: Dict[str, Any]):
        """Handle job submission from client (Hub RA only)"""
        self.logger.info(f"Received job submission from {peer_id}")
        
        job_id = message.get('job_id')
        ask_yaml = message.get('ask_yaml')
        client_id = message.get('client_id')
        
        if not ask_yaml:
            self.logger.error("No ask_yaml data in job submission")
            return
        
        # If this is the hub RA, broadcast to all other RAs
        if not self.bootstrap_peers:  # Hub RA has no bootstrap peers
            self.logger.info(f"Broadcasting job {job_id} to all RAs")
            
            # Find all RAs except self
            all_ras = self.peer.find_peers({"peer_type": "RA"})
            other_ras = [ra for ra in all_ras if ra != self.ra_id]
            
            broadcast_message = {
                "job_id": job_id,
                "client_id": client_id,
                "ask_yaml": ask_yaml,
                "timestamp": message.get('timestamp'),
                "hub_ra": self.ra_id
            }
            
            # Broadcast to all other RAs
            for ra_id in other_ras:
                self.peer.send(ra_id, "MSG_JOB_BROADCAST", broadcast_message)
                self.logger.info(f"Broadcasted job to {ra_id}")
            
            # Also evaluate locally
            self._evaluate_job_requirements(job_id, client_id, ask_yaml, peer_id)
        else:
            # Non-hub RA shouldn't receive direct job submissions
            self.logger.warning("Non-hub RA received direct job submission")
    
    def _handle_job_broadcast(self, peer_id: str, message: Dict[str, Any]):
        """Handle job broadcast from hub RA"""
        self.logger.info(f"Received job broadcast from hub {peer_id}")
        
        job_id = message.get('job_id')
        client_id = message.get('client_id')
        ask_yaml = message.get('ask_yaml')
        hub_ra = message.get('hub_ra')
        
        # Evaluate job requirements
        self._evaluate_job_requirements(job_id, client_id, ask_yaml, hub_ra)
    
    def _evaluate_job_requirements(self, job_id: str, client_id: str, ask_yaml: Dict, hub_ra: str):
        """Evaluate job requirements against RA capacity - YES/NO based"""
        self.logger.info(f"Evaluating job {job_id} requirements")
        
        if not self.capacity:
            self.logger.warning("No capacity data available for evaluation")
            return
        
        # Create response for each resource requirement
        resource_responses = {}
        
        # Evaluate each resource request in ask.yaml
        for resource_name, resource_requirements in ask_yaml.items():
            if not isinstance(resource_requirements, dict):
                continue
                
            self.logger.info(f"Evaluating requirements for {resource_name}")
            
            # Extract requirements
            capabilities = resource_requirements.get('capabilities', {})
            count = resource_requirements.get('count', 1)
            metadata = resource_requirements.get('metadata', {})
            
            # YES/NO evaluation - can we fulfill this requirement?
            can_fulfill = self._can_fulfill_requirement(capabilities, count)
            
            if can_fulfill:
                self.logger.info(f"✅ {resource_name}: YES - Can fulfill requirement")
                
                # Create detailed response with bid and resource definition
                resource_responses[resource_name] = {
                    "answer": "yes",
                    "ra_id": self.ra_id,
                    "provider": self.credentials.get('provider'),
                    "resource_provider": self.capacity.get('metadata', {}).get('resource-provider'),
                    "location": f"{self.capacity.get('locality', {}).get('city')}, {self.capacity.get('locality', {}).get('country')}",
                    "bid": self._create_bid_for_resource(resource_name, capabilities, count),
                    "resource_definition": self._create_resource_definition(resource_name, capabilities, count),
                    "available_instances": self._get_available_instances(capabilities),
                    "estimated_setup_time": "2-5 minutes",
                    "metadata": metadata
                }
            else:
                self.logger.info(f"❌ {resource_name}: NO - Cannot fulfill requirement")
                
                # Simple NO response - no bid or definition needed
                resource_responses[resource_name] = {
                    "answer": "no",
                    "ra_id": self.ra_id,
                    "reason": "Insufficient capacity or incompatible requirements"
                }
        
        # Create YAML response format
        yaml_response = {
            "job_id": job_id,
            "ra_id": self.ra_id,
            "provider": self.credentials.get('provider'),
            "timestamp": time.time(),
            "responses": resource_responses
        }
        
        # Send response to client
        clients = self.peer.find_peers({"peer_type": "JOB_CLIENT", "client_id": client_id})
        if clients:
            client_peer_id = clients[0]
            self.peer.send(client_peer_id, "MSG_RESOURCE_RESPONSE", yaml_response)
            self.logger.info(f"Sent YES/NO responses for {len(resource_responses)} resources to client")
        else:
            self.logger.warning(f"Client {client_id} not found in network")
    
    def _calculate_match_score(self, capabilities: Dict) -> float:
        """Calculate how well our capacity matches the requirements"""
        if not self.capacity.get('capacity'):
            return 0.0
        
        score = 0.0
        max_score = 0.0
        
        # Get our capacity data
        our_instances = self.capacity.get('capacity', {}).get('instances', {})
        our_pricing = self.capacity.get('pricing', {})
        our_locality = self.capacity.get('locality', {})
        our_system = self.capacity.get('system', {})
        our_energy = self.capacity.get('energy', {})
        
        # Evaluate host requirements
        host_reqs = capabilities.get('host', {}).get('properties', {})
        if host_reqs and our_instances:
            # Check if we have suitable instance types
            for instance_type, instance_specs in our_instances.items():
                cpu_match = self._check_cpu_requirement(host_reqs.get('num-cpus'), instance_specs.get('num-cpus'))
                mem_match = self._check_memory_requirement(host_reqs.get('mem-size'), instance_specs.get('mem-size'))
                disk_match = self._check_disk_requirement(host_reqs.get('disk-size'), instance_specs.get('disk-size'))
                
                self.logger.debug(f"Instance {instance_type}: CPU={cpu_match}, MEM={mem_match}, DISK={disk_match}")
                
                if cpu_match and mem_match and disk_match:
                    score += 25.0  # Host compatibility
                    self.logger.info(f"Host requirements matched for instance type: {instance_type}")
                    break
            max_score += 25.0
        
        # Evaluate pricing requirements
        pricing_reqs = capabilities.get('pricing', {}).get('properties', {})
        if pricing_reqs and our_pricing:
            cost_req = pricing_reqs.get('cost')
            if cost_req and self._check_cost_requirement(cost_req, our_pricing):
                score += 20.0
            max_score += 20.0
        
        # Evaluate locality requirements
        locality_reqs = capabilities.get('locality', {}).get('properties', {})
        if locality_reqs and our_locality:
            if self._check_locality_requirement(locality_reqs, our_locality):
                score += 15.0
            max_score += 15.0
        
        # Evaluate resource provider requirements
        resource_reqs = capabilities.get('resource', {}).get('properties', {})
        if resource_reqs:
            provider_match = self._check_provider_requirement(resource_reqs.get('provider'), 
                                                            self.capacity.get('metadata', {}).get('resource-provider'))
            if provider_match:
                score += 25.0
            max_score += 25.0
        
        # Evaluate energy requirements
        energy_reqs = capabilities.get('energy', {}).get('properties', {})
        if energy_reqs and our_energy:
            if self._check_energy_requirement(energy_reqs, our_energy):
                score += 15.0
            max_score += 15.0
        
        return score / max_score if max_score > 0 else 0.0
    
    def _check_cpu_requirement(self, requirement, available):
        """Check CPU requirement"""
        if not requirement or not available:
            return True
        
        if isinstance(requirement, dict):
            if '$in_range' in requirement:
                min_cpu, max_cpu = requirement['$in_range']
                return min_cpu <= available <= max_cpu
        else:
            return available >= requirement
        return True
    
    def _check_memory_requirement(self, requirement, available):
        """Check memory requirement"""
        if not requirement or not available:
            return True
        
        # Parse memory strings like "16 GB"
        available_gb = self._parse_memory_string(available)
        
        if isinstance(requirement, dict):
            if '$greater_or_equal' in requirement:
                req_gb = self._parse_memory_string(requirement['$greater_or_equal'])
                return available_gb >= req_gb
        else:
            req_gb = self._parse_memory_string(requirement)
            return available_gb >= req_gb
        return True
    
    def _check_disk_requirement(self, requirement, available):
        """Check disk requirement"""
        if not requirement or not available:
            return True
        
        # Parse disk strings like "200 GB"
        available_gb = self._parse_memory_string(available)
        req_gb = self._parse_memory_string(requirement)
        
        return available_gb >= req_gb
    
    def _parse_memory_string(self, mem_str):
        """Parse memory string like '16 GB' to numeric GB"""
        if isinstance(mem_str, (int, float)):
            return mem_str
        
        if isinstance(mem_str, str):
            mem_str = mem_str.upper().replace(' ', '')
            if 'GB' in mem_str:
                return float(mem_str.replace('GB', ''))
            elif 'MB' in mem_str:
                return float(mem_str.replace('MB', '')) / 1024
        return 0
    
    def _check_cost_requirement(self, requirement, our_pricing):
        """Check cost requirement"""
        if not requirement or not our_pricing:
            return True
        
        if isinstance(requirement, dict) and '$less_or_equal' in requirement:
            max_cost_str = requirement['$less_or_equal']
            # Handle both "1" and "1 credit / hr" formats
            if isinstance(max_cost_str, str):
                max_cost = float(max_cost_str.split()[0])  # Extract number from "1 credit / hr"
            else:
                max_cost = float(max_cost_str)
            
            self.logger.debug(f"Cost requirement: <= {max_cost}, Our pricing: {our_pricing}")
            
            # Check if any of our instance types meet the cost requirement
            for instance_type, cost in our_pricing.items():
                if cost <= max_cost:
                    self.logger.info(f"Cost requirement met: {instance_type} costs {cost} <= {max_cost}")
                    return True
            self.logger.info(f"No instance meets cost requirement <= {max_cost}")
        return False
    
    def _check_locality_requirement(self, requirements, our_locality):
        """Check locality requirements"""
        continent_req = requirements.get('continent')
        country_req = requirements.get('country') 
        city_req = requirements.get('city')
        
        our_continent = our_locality.get('continent')
        our_country = our_locality.get('country')
        our_city = our_locality.get('city')
        
        # Check continent
        if continent_req:
            if isinstance(continent_req, dict) and '$in' in continent_req:
                if our_continent not in continent_req['$in']:
                    return False
            elif our_continent != continent_req:
                return False
        
        # Check country
        if country_req:
            if isinstance(country_req, dict) and '$in' in country_req:
                if our_country not in country_req['$in']:
                    return False
            elif our_country != country_req:
                return False
        
        # Check city
        if city_req:
            if isinstance(city_req, dict) and '$in' in city_req:
                if our_city not in city_req['$in']:
                    return False
            elif our_city != city_req:
                return False
        
        return True
    
    def _check_provider_requirement(self, requirement, our_provider):
        """Check provider requirement"""
        if not requirement or not our_provider:
            return True
        
        if isinstance(requirement, dict) and '$in' in requirement:
            return our_provider in requirement['$in']
        else:
            return our_provider == requirement
    
    def _check_energy_requirement(self, requirements, our_energy):
        """Check energy requirements"""
        energy_type_req = requirements.get('energy-type')
        powered_type_req = requirements.get('powered-type')
        consumption_req = requirements.get('consumption')
        
        our_energy_type = our_energy.get('energy-type')
        our_powered_type = our_energy.get('powered-type')
        our_consumption = our_energy.get('consumption')
        
        # Check energy type
        if energy_type_req and our_energy_type != energy_type_req:
            return False
        
        # Check powered type
        if powered_type_req and our_powered_type != powered_type_req:
            return False
        
        # Check consumption
        if consumption_req and isinstance(consumption_req, dict):
            if '$less_or_equal' in consumption_req:
                max_consumption_str = consumption_req['$less_or_equal']
                if isinstance(max_consumption_str, str):
                    max_consumption = float(max_consumption_str.split()[0])  # Extract number
                else:
                    max_consumption = float(max_consumption_str)
                if our_consumption > max_consumption:
                    return False
        
        return True
    
    def _create_resource_offer(self, vm_name: str, capabilities: Dict, match_score: float, count: int):
        """Create a resource offer"""
        # Find best matching instance type
        our_instances = self.capacity.get('capacity', {}).get('instances', {})
        our_pricing = self.capacity.get('pricing', {})
        
        best_instance = None
        best_cost = float('inf')
        
        for instance_type, specs in our_instances.items():
            cost = our_pricing.get(instance_type, float('inf'))
            if cost < best_cost:
                best_instance = instance_type
                best_cost = cost
        
        offer = {
            "vm_name": vm_name,
            "ra_id": self.ra_id,
            "provider": self.credentials.get('provider'),
            "resource_provider": self.capacity.get('metadata', {}).get('resource-provider'),
            "instance_type": best_instance,
            "count": count,
            "match_score": match_score,
            "cost_per_hour": best_cost,
            "location": f"{self.capacity.get('locality', {}).get('city')}, {self.capacity.get('locality', {}).get('country')}",
            "available_immediately": True,
            "estimated_setup_time": "2-5 minutes"
        }
        
        return offer
    
    def _can_fulfill_requirement(self, capabilities: Dict, count: int) -> bool:
        """Simple YES/NO check - can we fulfill this requirement?"""
        
        # Check if we have capacity data
        if not self.capacity.get('capacity', {}).get('instances'):
            return False
        
        our_instances = self.capacity.get('capacity', {}).get('instances', {})
        our_pricing = self.capacity.get('pricing', {})
        our_locality = self.capacity.get('locality', {})
        our_energy = self.capacity.get('energy', {})
        
        # Check host requirements
        host_reqs = capabilities.get('host', {}).get('properties', {})
        host_compatible = False
        
        if host_reqs:
            for instance_type, specs in our_instances.items():
                cpu_match = self._check_cpu_requirement(host_reqs.get('num-cpus'), specs.get('num-cpus'))
                mem_match = self._check_memory_requirement(host_reqs.get('mem-size'), specs.get('mem-size'))
                disk_match = self._check_disk_requirement(host_reqs.get('disk-size'), specs.get('disk-size'))
                
                if cpu_match and mem_match and disk_match:
                    host_compatible = True
                    break
            
            if not host_compatible:
                return False
        
        # Check pricing requirements
        pricing_reqs = capabilities.get('pricing', {}).get('properties', {})
        if pricing_reqs and our_pricing:
            cost_req = pricing_reqs.get('cost')
            if cost_req and not self._check_cost_requirement(cost_req, our_pricing):
                return False
        
        # Check locality requirements
        locality_reqs = capabilities.get('locality', {}).get('properties', {})
        if locality_reqs and our_locality:
            if not self._check_locality_requirement(locality_reqs, our_locality):
                return False
        
        # Check resource provider requirements
        resource_reqs = capabilities.get('resource', {}).get('properties', {})
        if resource_reqs:
            provider_req = resource_reqs.get('provider')
            our_provider = self.capacity.get('metadata', {}).get('resource-provider')
            if not self._check_provider_requirement(provider_req, our_provider):
                return False
        
        # Check energy requirements
        energy_reqs = capabilities.get('energy', {}).get('properties', {})
        if energy_reqs and our_energy:
            if not self._check_energy_requirement(energy_reqs, our_energy):
                return False
        
        # Check if we have enough quota for the requested count
        our_quota = self.capacity.get('capacity', {}).get('instances_quota', {})
        if our_quota:
            # Find suitable instance type and check quota
            for instance_type, specs in our_instances.items():
                cpu_match = self._check_cpu_requirement(host_reqs.get('num-cpus'), specs.get('num-cpus'))
                mem_match = self._check_memory_requirement(host_reqs.get('mem-size'), specs.get('mem-size'))
                disk_match = self._check_disk_requirement(host_reqs.get('disk-size'), specs.get('disk-size'))
                
                if cpu_match and mem_match and disk_match:
                    available_quota = our_quota.get(instance_type, 0)
                    if available_quota >= count:
                        return True
            return False
        
        return True  # If all checks pass
    
    def _create_bid_for_resource(self, resource_name: str, capabilities: Dict, count: int) -> Dict:
        """Create bid information for a resource"""
        
        # Find best matching instance type
        our_instances = self.capacity.get('capacity', {}).get('instances', {})
        our_pricing = self.capacity.get('pricing', {})
        host_reqs = capabilities.get('host', {}).get('properties', {})
        
        best_instance = None
        best_cost = float('inf')
        
        for instance_type, specs in our_instances.items():
            cpu_match = self._check_cpu_requirement(host_reqs.get('num-cpus'), specs.get('num-cpus'))
            mem_match = self._check_memory_requirement(host_reqs.get('mem-size'), specs.get('mem-size'))
            disk_match = self._check_disk_requirement(host_reqs.get('disk-size'), specs.get('disk-size'))
            
            if cpu_match and mem_match and disk_match:
                cost = our_pricing.get(instance_type, float('inf'))
                if cost < best_cost:
                    best_instance = instance_type
                    best_cost = cost
        
        bid = {
            "instance_type": best_instance,
            "cost_per_hour": best_cost,
            "total_cost_per_hour": best_cost * count,
            "currency": "credits",
            "count": count,
            "setup_fee": 0,
            "minimum_duration": "1 hour"
        }
        
        return bid
    
    def _create_resource_definition(self, resource_name: str, capabilities: Dict, count: int) -> Dict:
        """Create resource definition based on our capacity"""
        
        # Find matching instance specs
        our_instances = self.capacity.get('capacity', {}).get('instances', {})
        host_reqs = capabilities.get('host', {}).get('properties', {})
        
        matched_specs = None
        for instance_type, specs in our_instances.items():
            cpu_match = self._check_cpu_requirement(host_reqs.get('num-cpus'), specs.get('num-cpus'))
            mem_match = self._check_memory_requirement(host_reqs.get('mem-size'), specs.get('mem-size'))
            disk_match = self._check_disk_requirement(host_reqs.get('disk-size'), specs.get('disk-size'))
            
            if cpu_match and mem_match and disk_match:
                matched_specs = specs.copy()
                matched_specs['instance_type'] = instance_type
                break
        
        resource_def = {
            "name": resource_name,
            "type": "virtual_machine",
            "count": count,
            "specifications": matched_specs or {},
            "operating_system": self.capacity.get('system', {}).get('os', {}),
            "location": self.capacity.get('locality', {}),
            "provider_info": {
                "provider": self.credentials.get('provider'),
                "resource_provider": self.capacity.get('metadata', {}).get('resource-provider'),
                "capacity_provider": self.capacity.get('metadata', {}).get('capacity-provider')
            }
        }
        
        return resource_def
    
    def _get_available_instances(self, capabilities: Dict) -> Dict:
        """Get list of available instance types that match requirements"""
        
        our_instances = self.capacity.get('capacity', {}).get('instances', {})
        our_quota = self.capacity.get('capacity', {}).get('instances_quota', {})
        host_reqs = capabilities.get('host', {}).get('properties', {})
        
        available = {}
        
        for instance_type, specs in our_instances.items():
            cpu_match = self._check_cpu_requirement(host_reqs.get('num-cpus'), specs.get('num-cpus'))
            mem_match = self._check_memory_requirement(host_reqs.get('mem-size'), specs.get('mem-size'))
            disk_match = self._check_disk_requirement(host_reqs.get('disk-size'), specs.get('disk-size'))
            
            if cpu_match and mem_match and disk_match:
                available[instance_type] = {
                    "specifications": specs,
                    "available_quota": our_quota.get(instance_type, 0),
                    "cost_per_hour": self.capacity.get('pricing', {}).get(instance_type, 0)
                }
        
        return available
    
    def connect_to_network(self):
        """Connect to P2P network using bootstrap peers"""
        if not self.bootstrap_peers:
            self.logger.info("No bootstrap peers configured - running as hub")
            return
        
        for peer_address in self.bootstrap_peers:
            try:
                host, port = peer_address.split(':')
                port = int(port)
                
                self.logger.info(f"Connecting to bootstrap peer: {host}:{port}")
                self.peer.enter(host, port)
                
            except ValueError:
                self.logger.error(f"Invalid bootstrap peer format: {peer_address}")
            except Exception as e:
                self.logger.error(f"Failed to connect to {peer_address}: {e}")
    
    def start(self):
        """Start the Resource Agent"""
        try:
            self.logger.info(f"Starting Resource Agent: {self.ra_id}")
            
            # Initialize P2P peer
            self.initialize_peer()
            
            # Connect to network
            self.connect_to_network()
            
            # Start the peer (this will block)
            self.is_running = True
            self.logger.info(f"RA {self.ra_id} is now running and ready to accept connections...")
            self.peer.start()  # This blocks until stopped
            
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








