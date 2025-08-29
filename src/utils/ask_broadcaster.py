#!/usr/bin/env python3
"""
Simple Ask.yaml Broadcaster - Loads ask.yaml and broadcasts requirements directly to P2P network
"""

import yaml
from typing import Dict, List, Any
from pathlib import Path
import logging
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)

class AskBroadcaster:
    """Simple class to load ask.yaml and broadcast requirements directly to P2P network"""
    
    def __init__(self, ask_yaml_path: str = None, p2p_agent=None):
        """Initialize with path to ask.yaml and P2P agent"""
        if ask_yaml_path is None:
            # Default path relative to project root
            project_root = Path(__file__).parent.parent.parent.parent
            self.ask_yaml_path = project_root / "tosca" / "outputs" / "ask.yaml"
        else:
            self.ask_yaml_path = Path(ask_yaml_path)
        
        # P2P agent for actual broadcasting
        self.p2p_agent = p2p_agent
    
    def load_ask_yaml(self) -> Dict[str, Any]:
        """Load the ask.yaml file directly"""
        try:
            if not self.ask_yaml_path.exists():
                raise FileNotFoundError(f"ask.yaml not found at: {self.ask_yaml_path}")
            
            with open(self.ask_yaml_path, 'r', encoding='utf-8') as file:
                ask_requirements = yaml.safe_load(file)
            
            logger.info(f" Loaded ask.yaml from: {self.ask_yaml_path}")
            return ask_requirements
            
        except Exception as e:
            logger.error(f" Error loading ask.yaml: {e}")
            return {}
    
    def extract_requirements_from_ask(self, ask_data: Dict) -> Dict[str, Any]:
        """Extract resource requirements from ask.yaml"""
        
        logger.info(" Extracting requirements from ask.yaml")
        
        vm_requirements = []
        total_vms = 0
        
        for vm_name, vm_config in ask_data.items():
            if 'capabilities' in vm_config:
                vm_count = vm_config.get('count', 1)
                total_vms += vm_count
                
                vm_requirement = {
                    'vm_name': vm_name,
                    'count': vm_count,
                    'metadata': vm_config.get('metadata', {}),
                    'requirements': vm_config['capabilities']
                }
                vm_requirements.append(vm_requirement)
                
                logger.info(f" Extracted {vm_name}: {vm_count} VMs")
        
        logger.info(f" Total VMs from ask.yaml: {total_vms}")
        
        return {
            'total_vms': total_vms,
            'vm_requirements': vm_requirements,
            'extraction_source': str(self.ask_yaml_path)
        }
    
    def create_broadcast_message(self, requirements: Dict) -> Dict[str, Any]:
        """Create P2P broadcast message"""
        
        broadcast_id = f"broadcast_{uuid.uuid4().hex[:8]}_{int(datetime.now().timestamp())}"
        
        message = {
            'message_type': 'resource_request',
            'request_id': broadcast_id,
            'source_ra': 'ra-local',  # This will be set by the calling RA
            'timestamp': datetime.now().isoformat(),
            'resource_requirements': {
                'status': 'ready_for_p2p',
                'message': 'Requirements loaded directly from ask.yaml',
                'resource_requirements': requirements['vm_requirements'],
                'total_vms': requirements['total_vms'],
                'source': 'ask.yaml_direct'
            },
            'status': 'ready_for_broadcast'
        }
        
        logger.info(f" Created broadcast message: {broadcast_id}")
        return message
    
    def broadcast_to_p2p_network(self, broadcast_message: Dict) -> bool:
        """Actually broadcast the message to P2P network"""
        
        if not self.p2p_agent:
            logger.error(" No P2P agent available for broadcasting")
            return False
        
        try:
            # Use the existing P2P broadcast method
            self.p2p_agent.broadcast(
                "resource_request", 
                broadcast_message
            )
            
            logger.info(f" Successfully broadcasted to P2P network: {broadcast_message['request_id']}")
            return True
            
        except Exception as e:
            logger.error(f" Failed to broadcast to P2P network: {e}")
            return False
    
    def broadcast_ask_requirements(self) -> Dict[str, Any]:
        """Main method: load ask.yaml and broadcast to P2P network"""
        
        # Load ask.yaml
        ask_data = self.load_ask_yaml()
        if not ask_data:
            return {
                'status': 'error',
                'message': 'Failed to load ask.yaml'
            }
        
        # Extract requirements
        requirements = self.extract_requirements_from_ask(ask_data)
        
        # Create broadcast message
        broadcast_message = self.create_broadcast_message(requirements)
        
        # Actually broadcast to P2P network
        if self.p2p_agent:
            broadcast_success = self.broadcast_to_p2p_network(broadcast_message)
            
            if broadcast_success:
                return {
                    'status': 'success',
                    'message': 'ask.yaml requirements successfully broadcasted to P2P network',
                    'broadcast_message': broadcast_message,
                    'requirements': requirements,
                    'source': 'ask.yaml_direct',
                    'p2p_status': 'broadcasted'
                }
            else:
                return {
                    'status': 'error',
                    'message': 'Failed to broadcast to P2P network',
                    'broadcast_message': broadcast_message,
                    'requirements': requirements,
                    'source': 'ask.yaml_direct',
                    'p2p_status': 'failed'
                }
        else:
            return {
                'status': 'warning',
                'message': 'ask.yaml requirements prepared but no P2P agent available',
                'broadcast_message': broadcast_message,
                'requirements': requirements,
                'source': 'ask.yaml_direct',
                'p2p_status': 'no_p2p_agent'
            }

def main():
    """Test the Ask Broadcaster (without P2P agent)"""
    print(" Testing Ask Broadcaster (P2P integration)")
    print("=" * 60)
    
    broadcaster = AskBroadcaster()  # No P2P agent for testing
    result = broadcaster.broadcast_ask_requirements()
    
    if result['status'] == 'success':
        print(f" {result['message']}")
        print(f" Total VMs: {result['requirements']['total_vms']}")
        print(f" VMs: {[vm['vm_name'] for vm in result['requirements']['vm_requirements']]}")
        print(f" Broadcast ID: {result['broadcast_message']['request_id']}")
        print(f" P2P Status: {result['p2p_status']}")
    elif result['status'] == 'warning':
        print(f" {result['message']}")
        print(f" Total VMs: {result['requirements']['total_vms']}")
        print(f" VMs: {[vm['vm_name'] for vm in result['requirements']['vm_requirements']]}")
        print(f" Broadcast ID: {result['broadcast_message']['request_id']}")
        print(f" P2P Status: {result['p2p_status']}")
    else:
        print(f" Error: {result['message']}")

if __name__ == "__main__":
    main()
