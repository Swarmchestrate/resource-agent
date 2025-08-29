#!/usr/bin/env python3
"""
Real Resource Requirements Extractor
This module loads ask.yaml and extracts resource requirements for P2P broadcast
"""

import yaml
from typing import Dict, List, Any, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class ResourceRequirementsExtractor:
    """Extracts resource requirements from ask.yaml for P2P broadcast"""
    
    def __init__(self, ask_yaml_path: str = None):
        """Initialize with path to ask.yaml file"""
        if ask_yaml_path is None:
            # Default path relative to project root
            project_root = Path(__file__).parent.parent.parent.parent
            self.ask_yaml_path = project_root / "tosca" / "outputs" / "ask.yaml"
        else:
            self.ask_yaml_path = Path(ask_yaml_path)
    
    def load_ask_yaml(self) -> Dict[str, Any]:
        """Load and parse the ask.yaml file"""
        try:
            if not self.ask_yaml_path.exists():
                raise FileNotFoundError(f"ask.yaml not found at: {self.ask_yaml_path}")
            
            with open(self.ask_yaml_path, 'r', encoding='utf-8') as file:
                requirements = yaml.safe_load(file)
            
            logger.info(f"Successfully loaded ask.yaml from: {self.ask_yaml_path}")
            return requirements
            
        except Exception as e:
            logger.error(f"Error loading ask.yaml: {e}")
            return {}
    
    def extract_resource_requirements(self) -> Dict[str, Any]:
        """Extract resource requirements from ask.yaml for P2P broadcast"""
        logger.info("🔍 Extracting Resource Requirements from ask.yaml")
        
        # Load ask.yaml
        requirements = self.load_ask_yaml()
        if not requirements:
            logger.error("No requirements loaded from ask.yaml")
            return {}
        
        # Extract VM requirements
        vm_requirements = []
        total_vms = 0
        
        for vm_name, vm_config in requirements.items():
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
                
                logger.info(f"📋 Extracted requirements for {vm_name}: {vm_count} VMs")
        
        logger.info(f"✅ Total VMs found: {total_vms}")
        
        return {
            'status': 'success',
            'total_vms': total_vms,
            'vm_requirements': vm_requirements,
            'source_file': str(self.ask_yaml_path)
        }
    
    def get_requirements_for_p2p(self) -> Dict[str, Any]:
        """Get resource requirements formatted for P2P network broadcast"""
        requirements = self.extract_resource_requirements()
        
        if requirements.get('status') != 'success':
            return {'status': 'error', 'message': 'Failed to extract requirements'}
        
        # Format for P2P broadcast
        p2p_requirements = {
            'status': 'ready_for_p2p',
            'total_vms': requirements['total_vms'],
            'vm_requirements': requirements['vm_requirements'],
            'broadcast_timestamp': None,  # Will be set when broadcasting
            'source': 'ask.yaml_validation'
        }
        
        return p2p_requirements

def main():
    """Test the resource requirements extractor"""
    print("🧪 Testing Real Resource Requirements Extractor")
    print("=" * 60)
    
    extractor = ResourceRequirementsExtractor()
    requirements = extractor.extract_resource_requirements()
    
    if requirements.get('status') == 'success':
        print(f"\n📊 Extracted Requirements Summary:")
        print(f"  Total VMs: {requirements['total_vms']}")
        for vm in requirements['vm_requirements']:
            print(f"  • {vm['vm_name']}: {vm['count']} VMs")
            host_req = vm['requirements'].get('host', {}).get('properties', {})
            if 'num-cpus' in host_req:
                print(f"    - CPU: {host_req['num-cpus']}")
            if 'mem-size' in host_req:
                print(f"    - Memory: {host_req['mem-size']}")
    else:
        print("❌ No requirements extracted")

if __name__ == "__main__":
    main()

