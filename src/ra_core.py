import logging
import time
from pathlib import Path
import yaml
from typing import Dict, Any
from config import RAConfig
from utils.helpers import generate_reservation_id, validate_app_description, get_app_summary, format_app_description
from utils.resource_offer_system import ResourceRequestBroadcaster


"""
Updated to use new lib_comm v0.3.0 from local directory:
Path: Swarmchestrate_RA/lib_comm/swchp2pcom/
Using SwchPeer class with advanced P2P network features
"""
# Import P2P components from new lib_comm v0.3.0
try:
    import sys
    from pathlib import Path
    # Add new lib_comm to path (local directory)
    lib_comm_path = Path(__file__).parent.parent / "lib_comm"
    if lib_comm_path.exists():
        sys.path.insert(0, str(lib_comm_path))
        from swchp2pcom.swchpeer import SwchPeer
        from swchp2pcom.message_types import SystemMessageType
        P2P_AVAILABLE = True
        print("Successfully imported new lib_comm v0.3.0 P2P library with SwchPeer")
        print(f"Library path: {lib_comm_path}")
    else:
        P2P_AVAILABLE = False
        print(f"ERROR: lib_comm not found at {lib_comm_path}")
except ImportError as e:
    P2P_AVAILABLE = False
    print(f"ERROR: P2P libraries not available ({e})")

# Resource Agent class
class ResourceAgent:
    def __init__(self, config: RAConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.p2p_agent = None
        self.resource_request_broadcaster = ResourceRequestBroadcaster(config.id)
        self.initialize()

    def initialize(self):
        """Initialize RA with config, P2P network, and capacity registry."""
        self.logger.info(f"Starting RA {self.config.id} for capacity {self.config.capacity_id}")
        
        # Initialize P2P network with new SwchPeer
        if P2P_AVAILABLE:
            try:
                # Prepare metadata for the new SwchPeer
                metadata = {
                    "universe": self.config.universe_id,
                    "peer_type": "ra",
                    "capacity": self.config.capacity_id,
                    "description": f"Resource Agent {self.config.id}"
                }
                
                # For local RA, use actual machine IP; for EC2, use public IP
                public_ip = "18.130.228.37" if self.config.id == "ra-ec2" else self.config.domain
                
                self.p2p_agent = SwchPeer(
                    peer_id=self.config.id,
                    listen_ip=self.config.domain,
                    listen_port=self.config.p2p_port,
                    public_ip=public_ip,
                    public_port=self.config.p2p_port,
                    metadata=metadata,
                    enable_rejoin=True
                )
                
                # Register message handlers using new API
                self.p2p_agent.register_message_handler("user_client_submit", self.handle_submit)
                self.p2p_agent.register_message_handler("test", self.handle_test_message)
                
                # Register Resource Request message handler (for future phases)
                self.p2p_agent.register_message_handler("resource_request", self.handle_resource_request)
                # Register Resource Offers message handler (for collecting offers)
                self.p2p_agent.register_message_handler("resource_offers", self.handle_resource_offers)
                self.logger.info(f"Registered message handlers:")
                self.logger.info(f"   - user_client_submit: {self.handle_submit}")
                self.logger.info(f"   - test: {self.handle_test_message}")
                self.logger.info(f"   - resource_request: {self.handle_resource_request}")
                self.logger.info(f"   - resource_offers: {self.handle_resource_offers}")
                self.logger.info(f"Advanced P2P Agent (SwchPeer) initialized on {self.config.domain}:{self.config.p2p_port}")
                self.logger.info(f"Agent metadata: {metadata}")
            except Exception as e:
                self.logger.error(f"Failed to initialize P2P agent: {e}")
                self.p2p_agent = None
        else:
            # P2P library not available - fail with clear error
            raise ImportError(
                "P2P library (lib_comm) is not available. "
                "Please ensure lib_comm directory exists and dependencies are installed. "
                f"Expected path: {lib_comm_path}"
            )

        # Capacity registry not needed - we use TOSCA YAML files for resource requirements
        self.logger.info("Resource Agent initialized - using TOSCA YAML for resource definitions")

    def connect_to_peers(self):
        """Connect to other RAs in the network using bootstrap_peers."""
        if not self.p2p_agent:
            self.logger.warning("P2P agent not available, skipping peer connection")
            return

        try:
            # Use bootstrap_peers from configuration
            if hasattr(self.config, 'bootstrap_peers') and self.config.bootstrap_peers:
                for peer in self.config.bootstrap_peers:
                    if ':' in peer:
                        host, port = peer.split(':')
                        port = int(port)
                        self.logger.info(f"Connecting {self.config.id} to {host}:{port}...")
                        
                        # Use the SwchPeer enter method with async callback handling
                        deferred = self.p2p_agent.enter(host, port)
                        
                        def connection_success(result):
                            self.logger.info(f"Successfully connected to {host}:{port}")
                            # Check current peer count
                            peer_count = self.p2p_agent.get_connection_count()
                            self.logger.info(f"Current peer connections: {peer_count}")
                            
                        def connection_failed(failure):
                            self.logger.error(f"Failed to connect to {host}:{port}: {failure}")
                        
                        deferred.addCallback(connection_success)
                        deferred.addErrback(connection_failed)
                        
                    else:
                        self.logger.warning(f"Invalid bootstrap peer format: {peer}")
            else:
                self.logger.info(f"No bootstrap peers configured for {self.config.id}")
            
            self.logger.info("Bootstrap connection attempts initiated")
        except Exception as e:
            self.logger.error(f"Failed to connect to peers: {e}")

    def test_p2p(self):
        """Send a test message via P2P network."""
        if not self.p2p_agent:
            self.logger.warning("P2P agent not available, skipping test message")
            return

        try:
            # Use the new SwchPeer API: broadcast(message_type, payload)
            from datetime import datetime
            message_payload = {"content": f"Hello from {self.config.id}", "timestamp": datetime.now().isoformat()}
            self.logger.info(f"Broadcasting test message: {message_payload}")
            self.p2p_agent.broadcast("test", message_payload)
        except Exception as e:
            self.logger.error(f"Failed to send test message: {e}")

    def handle_submit(self, protocol, message: dict):
        """Handle incoming application submission from P2P network."""
        app_desc = message.get("app_description", {})
        client_id = message.get("client_id", "unknown")
        self.logger.info(f"Received submission from {client_id}: {app_desc}")
        
        # Process the submission
        reservation_id = self.submit_application(app_desc)
        
        # Send acknowledgment
        response = {"message_type": "ack", "reservation_id": reservation_id}
        protocol.send_message(response)
        
        self.logger.info(f"Processed submission, reservation ID: {reservation_id}")

    def submit_application(self, app_desc: dict) -> str:
        """Process application submission."""
        self.logger.info(f"Processing application submission: {app_desc}")
        
        # For TOSCA submissions, app_desc already contains the parsed structure
        # No need to format it - use it directly
        formatted_app_desc = app_desc
        
        # Validate that we have TOSCA data
        if not isinstance(formatted_app_desc, dict) or 'resource_requirements' not in formatted_app_desc:
            self.logger.error("Invalid TOSCA data structure")
            raise ValueError("Invalid TOSCA data structure")
        
        # Get application summary for logging
        app_summary = get_app_summary(formatted_app_desc)
        self.logger.info(f"Application summary: {app_summary}")
        
        # Generate reservation ID using utility function
        reservation_id = generate_reservation_id(self.config.id, formatted_app_desc)
        
        # Use Resource Request Broadcaster to create and broadcast resource request
        if self.p2p_agent and P2P_AVAILABLE:
            try:
                # Create resource request using the Resource Request Broadcaster
                resource_request = self.resource_request_broadcaster.create_and_broadcast_request(formatted_app_desc)
                
                # Broadcast the resource request to all peers
                self.p2p_agent.broadcast("resource_request", resource_request)
                self.logger.info(f"Broadcasted resource request: {resource_request['request_id']}")
                
                # Store the request ID for tracking
                request_id = resource_request['request_id']
                
            except Exception as e:
                self.logger.error(f"Failed to broadcast resource request: {e}")
                request_id = None
        
        return reservation_id

    def update_application(self, reservation_id: str, app_desc: dict) -> bool:
        """Update an existing application."""
        self.logger.info(f"Updating application {reservation_id}: {app_desc}")
        
        # Capacity registry not available - returning mock success
        self.logger.warning("Capacity registry not available - returning mock success")
        return True

    def delete_application(self, reservation_id: str) -> bool:
        """Delete an application and free resources."""
        self.logger.info(f"Deleting application {reservation_id}")
        
        # Capacity registry not available - returning mock success
        self.logger.warning("Capacity registry not available - returning mock success")
        return True

    def get_status(self, reservation_id: str) -> dict:
        """Get application status."""
        self.logger.info(f"Getting status for {reservation_id}")
        
        # Capacity registry not available - returning mock success
        return {
            "reservation_id": reservation_id,
            "status": "active",
            "ra_id": self.config.id
        }

    def handle_test_message(self, sender_id: str, message: dict):
        """Handle incoming test messages from P2P network."""
        try:
            self.logger.info(f"Received test message from {sender_id}")
            self.logger.info(f"Test message: {message}")
            
            # Extract payload if available
            payload = message.get('payload', {})
            if payload:
                self.logger.info(f"Test content: {payload.get('content', 'No content')}")
                self.logger.info(f"Timestamp: {payload.get('timestamp', 'No timestamp')}")
            
            # Optional: Send acknowledgment back
            if self.p2p_agent:
                response_payload = {
                    "response": "test_received",
                    "timestamp": time.time(),
                    "recipient": self.config.id,
                    "original_sender": sender_id
                }
                self.p2p_agent.send(sender_id, "test_ack", response_payload)
                self.logger.info(f"Sent test acknowledgment to {sender_id}")
                
        except Exception as e:
            self.logger.error(f"Error handling test message from {sender_id}: {e}")

    def handle_resource_request(self, sender_id: str, message: dict):
        """Handle incoming resource requests from other RAs - Binary matching system."""
        try:
            self.logger.info(f"Received resource request from {sender_id}")
            
            # Extract request information
            request_id = message.get("request_id")
            resource_requirements = message.get("resource_requirements", {})
            vm_requirements = resource_requirements.get('resource_requirements', [])
            
            self.logger.info(f"Processing {len(vm_requirements)} VM requirements")
            
            # Use binary matcher - no scoring
            from utils.binary_resource_matcher import BinaryResourceMatcher
            matcher = BinaryResourceMatcher()
            
            # Load capacity profile
            ra_capacity = self._load_ra_capacity_profile()
            
            offers = []
            
            # Check each VM requirement - binary decision only
            for vm_req in vm_requirements:
                vm_name = vm_req.get('vm_name', 'unknown')
                vm_count = vm_req.get('count', 1)
                
                self.logger.info(f"Evaluating {vm_name} (count: {vm_count})")
                
                # Binary check: can fulfill or cannot fulfill
                match_result = matcher.match_vm_requirements(vm_req, ra_capacity)
                
                if match_result['can_fulfill']:
                    # YES - create offer
                    self.logger.info(f"CAN fulfill {vm_name}: {match_result['reason']}")
                    
                    offer = {
                        'offer_id': f"offer_{self.config.id}_{vm_name}",
                        'ra_id': self.config.id,
                        'request_id': request_id,
                        'vm_name': vm_name,
                        'count': vm_count,
                        'status': 'can_fulfill',
                        'message': match_result['reason']
                    }
                    offers.append(offer)
                else:
                    # NO - don't send offer
                    self.logger.info(f"CANNOT fulfill {vm_name}: {match_result['reason']}")
            
            # Send offers back only if we can fulfill requirements
            if offers:
                offer_response = {
                    'message_type': 'resource_offers',
                    'request_id': request_id,
                    'source_ra': self.config.id,
                    'offers': offers,
                    'timestamp': time.time()
                }
                
                if self.p2p_agent:
                    self.p2p_agent.send(sender_id, "resource_offers", offer_response)
                    self.logger.info(f"Sent {len(offers)} offers to {sender_id}")
            else:
                self.logger.info(f"No offers sent - cannot fulfill any requirements")
                
        except Exception as e:
            self.logger.error(f"Error processing resource request: {e}")

    def _load_ra_capacity_profile(self):
        """Load this RA's capacity configuration from capacity_profiles.yaml"""
        try:
            import yaml
            from pathlib import Path
            
            capacity_file = Path("config/capacity_profiles.yaml")
            with open(capacity_file, 'r') as file:
                capacity_data = yaml.safe_load(file)
            
            return capacity_data['capacity_profiles'].get(self.config.id, {})
        except Exception as e:
            self.logger.error(f"Error loading capacity profile: {e}")
            return {}

    def handle_resource_offers(self, sender_id: str, message: dict):
        """Handle incoming resource offers from other RAs - Binary system."""
        try:
            self.logger.info(f"Received resource offers from {sender_id}")
            self.logger.info(f"Offer details: {message}")
            
            # Extract offer information
            request_id = message.get("request_id")
            source_ra = message.get("source_ra")
            offers = message.get("offers", [])
            timestamp = message.get("timestamp")
            
            if not request_id or not offers:
                self.logger.warning("Resource offers missing request_id or offers")
                return
            
            self.logger.info(f"Received {len(offers)} offers for request {request_id} from {source_ra}")
            
            # Store offers for this request
            if not hasattr(self, 'pending_offers'):
                self.pending_offers = {}
            
            if request_id not in self.pending_offers:
                self.pending_offers[request_id] = []
            
            # Add offers to pending list - binary format (no scores)
            for offer in offers:
                offer['received_from'] = source_ra
                offer['received_at'] = timestamp
                self.pending_offers[request_id].append(offer)
                
                # Log binary offer without expecting match_score
                self.logger.info(f"Stored offer: {offer['offer_id']} from {source_ra} "
                               f"for {offer['vm_name']} - Status: {offer.get('status', 'unknown')}")
            
            # Log total offers collected
            total_offers = len(self.pending_offers[request_id])
            self.logger.info(f"Total offers collected for {request_id}: {total_offers}")
            
            # Simple binary system - just log which RAs can fulfill
            if total_offers >= 1:
                self.logger.info(f"Binary offers available for {request_id}")
                self.logger.info(f"RAs that can fulfill: {[f'{o['ra_id']}:{o['vm_name']}' for o in self.pending_offers[request_id]]}")
            
        except Exception as e:
            self.logger.error(f"Error handling resource offers from {sender_id}: {e}")

    def start(self):
        """Start the P2P reactor."""
        self.logger.info("Starting P2P reactor...")
        
        # Connect to peers
        self.connect_to_peers()
        
        # Send test message
        self.test_p2p()
        
        if self.p2p_agent and P2P_AVAILABLE:
            try:
                self.logger.info("Advanced P2P agent (SwchPeer) server is running")
                self.logger.info(f"Listening on {self.config.domain}:{self.config.p2p_port}")
                
                # Start the Twisted reactor (this is blocking!)
                self.logger.info("Starting P2P reactor loop...")
                self.p2p_agent.start()  # This blocks until reactor stops
                    
            except KeyboardInterrupt:
                self.logger.info("P2P reactor stopped by user")
            except Exception as e:
                self.logger.error(f"Failed to start P2P reactor: {e}")

