"""
Capability Evaluator for Resource Agent System
Compares ask.yaml requirements with capacity.yaml capabilities
"""

import re
from typing import Dict, Any, List, Optional


def can_fulfill_requirement(ask_requirements: dict, capacity_data: dict) -> bool:
    """
    Check if capacity can fulfill ask requirements.
    Returns True if ALL requirements can be met, False otherwise.
    """
    capabilities = ask_requirements.get('capabilities', {})
    
    for requirement_type, requirement_data in capabilities.items():
        if not isinstance(requirement_data, dict):
            continue
            
        properties = requirement_data.get('properties', {})
        if not properties:
            continue
        

        if not check_requirement_type_requirements(requirement_type, properties, capacity_data):
 #           print(f"requirement_type: {requirement_type} not fulfilled, properties are:\n {properties}\n capacity of the RA is:\n {capacity_data} ")
            return False
    
    return True


def check_requirement_type_requirements(requirement_type: str, properties: dict, capacity_data: dict) -> bool:
    """Check all properties in a requirement_type against capacity"""
    
    if requirement_type == 'host':
        instances = find_in_capacity(capacity_data, ['capacity.instances', 'instances'])
        # Handle flat structure (like AWS UK Edge)
        if not instances:
            capacity_section = capacity_data.get('capacity', {})
            # Check if this is a flat structure with host properties
            if 'num-cpus' in capacity_section or 'mem-size' in capacity_section:
                # Treat the whole capacity section as one instance
                if check_instance_requirements(properties, capacity_section, capacity_data):
                    return True
            return False

        # Handle instances structure (like AWS Cloud and SZTAKI)
            
        for instance_name, instance_data in instances.items():
            if check_instance_requirements(properties, instance_data, capacity_data):
                return True
        return False
    
    else:
        for prop_key, prop_value in properties.items():
            if not check_property_anywhere(requirement_type, prop_key, prop_value, capacity_data):
                return False
        return True


def check_instance_requirements(requirements: dict, instance_data: dict, capacity_data: dict) -> bool:
    """Check if an instance meets all requirements"""
    
    for req_key, req_value in requirements.items():
        if req_key == 'cpu-architecture':
            if not check_architecture_requirement(req_value, capacity_data):
                return False
        
        elif req_key == 'num-cpus':
            instance_cpus = instance_data.get('num-cpus', 0)
            if isinstance(req_value, dict):
                if '$in_range' in req_value:
                    min_cpu, max_cpu = req_value['$in_range']
                    if not (min_cpu <= instance_cpus <= max_cpu):
                        return False
                elif not check_value(req_value, instance_cpus):
                    return False
            elif instance_cpus != req_value:
                return False
        
        elif req_key == 'mem-size':
            instance_mem = parse_number(instance_data.get('mem-size', 0))
            if isinstance(req_value, dict):
                if '$greater_or_equal' in req_value:
                    min_mem = parse_number(req_value['$greater_or_equal'])
                    if instance_mem < min_mem:
                        return False
                elif not check_value(req_value, instance_mem):
                    return False
            else:
                # Plain number is treated as minimum
                min_mem = parse_number(req_value)
                if instance_mem < min_mem:
                    return False
        
        elif req_key == 'disk-size':
            instance_disk = parse_number(instance_data.get('disk-size', 0))
            if isinstance(req_value, dict):
                if '$greater_or_equal' in req_value:
                    min_disk = parse_number(req_value['$greater_or_equal'])
                    if instance_disk < min_disk:
                        return False
                elif not check_value(req_value, instance_disk):
                    return False
            else:
                # Plain number is treated as minimum
                min_disk = parse_number(req_value)
                if instance_disk < min_disk:
                    return False
        
        else:
            # Other properties
            instance_value = instance_data.get(req_key)
            if not check_value(req_value, instance_value):
                return False
    
    return True


def check_property_anywhere(requirement_type: str, prop_key: str, prop_value, capacity_data: dict) -> bool:
    """Find and check a property anywhere in capacity data"""
    
    search_paths = {
        'os': ['system.os', 'os', 'system'],
        'resource': ['metadata', 'meta'],
        'pricing': ['pricing', 'costs', 'price'],
        'locality': ['locality', 'location', 'region'],
        'energy': ['energy', 'power']
    }
    
    paths = search_paths.get(requirement_type, [requirement_type])
    
    for path in paths:
        section = find_in_capacity(capacity_data, [path])
        if section and isinstance(section, dict):
            # Special handling for pricing
            if requirement_type == 'pricing' and prop_key == 'cost':
                # Check if any instance price meets requirement
                if isinstance(prop_value, dict) and '$less_or_equal' in prop_value:
                    max_cost = parse_number(prop_value['$less_or_equal'])
                    for instance_type, price in section.items():
                        if parse_number(price) <= max_cost:
                            return True
                    return False
            
            # Try exact key
            if prop_key in section:
                if check_value(prop_value, section[prop_key]):
                    return True
            
            # Try variations of the key
            for key_variant in get_key_variations(prop_key):
                if key_variant in section:
                    if check_value(prop_value, section[key_variant]):
                        return True
            
            # For resource requirement_type, try prefixed keys
            if requirement_type == 'resource':
                prefixed_keys = [
                    f'resource-{prop_key}',
                    f'capacity-{prop_key}',
                    f'{requirement_type}-{prop_key}'
                ]
                for prefixed in prefixed_keys:
                    if prefixed in section:
                        if check_value(prop_value, section[prefixed]):
                            return True
    
    return False


def check_architecture_requirement(required: str, capacity_data: dict) -> bool:
    """Check architecture requirement against capacity"""
    
    arch_locations = [
        'system.supported-architecture',
        'system.supported_architecture',
        'system.architecture',
        'hardware.architecture',
        'system.arch'
    ]
    
    for location in arch_locations:
        arch_data = find_in_capacity(capacity_data, [location])
        if arch_data:
            if isinstance(arch_data, dict):
                if check_architecture_dict(required, arch_data):
                    return True
            elif isinstance(arch_data, list):
                if check_architecture_list(required, arch_data):
                    return True
            elif isinstance(arch_data, str):
                if check_architecture_string(required, arch_data):
                    return True
    
    return False


def check_architecture_dict(required: str, arch_dict: dict) -> bool:
    """Check architecture against dict format {x86: yes}"""
    if required in arch_dict:
        value = arch_dict[required]
        return value in ['yes', True, 'true', 1, 'Yes', 'TRUE']
    
    required_base = required.lower().replace('_64', '').replace('64', '').replace('-', '').replace('_', '')
    for key, value in arch_dict.items():
        key_base = key.lower().replace('_64', '').replace('64', '').replace('-', '').replace('_', '')
        if required_base == key_base:
            return value in ['yes', True, 'true', 1, 'Yes', 'TRUE']
    
    return False


def check_architecture_list(required: str, arch_list: list) -> bool:
    """Check architecture against list format ["x86_64", "amd64"]"""
    if required in arch_list:
        return True
    
    required_base = required.lower().replace('_64', '').replace('64', '').replace('-', '').replace('_', '')
    for arch in arch_list:
        arch_base = arch.lower().replace('_64', '').replace('64', '').replace('-', '').replace('_', '')
        if required_base == arch_base:
            return True
    
    return False


def check_architecture_string(required: str, arch_str: str) -> bool:
    """Check architecture against string format"""
    if required.lower() == arch_str.lower():
        return True
    
    required_base = required.lower().replace('_64', '').replace('64', '').replace('-', '').replace('_', '')
    arch_base = arch_str.lower().replace('_64', '').replace('64', '').replace('-', '').replace('_', '')
    return required_base == arch_base


def get_key_variations(key: str) -> list:
    """Get variations of a key (hyphen vs underscore)"""
    variations = [key]
    if '-' in key:
        variations.append(key.replace('-', '_'))
    if '_' in key:
        variations.append(key.replace('_', '-'))
    return variations


def find_in_capacity(capacity_data: dict, paths: list):
    """Find a value in capacity data using dot notation paths"""
    for path in paths:
        if '.' in path:
            keys = path.split('.')
            current = capacity_data
            for key in keys:
                if isinstance(current, dict) and key in current:
                    current = current[key]
                else:
                    current = None
                    break
            if current is not None:
                return current
        else:
            if path in capacity_data:
                return capacity_data[path]
    
    return None


def check_value(requirement, capacity_value) -> bool:
    """Check if a capacity value meets a requirement"""
    if requirement is None:
        return True
    
    if capacity_value is None:
        return False
    
    if isinstance(requirement, dict):
        for operator, expected in requirement.items():
            if operator == '$in':
                if not isinstance(expected, list):
                    return capacity_value == expected
                if capacity_value not in expected:
                    return False
            elif operator == '$in_range':
                if len(expected) == 2:
                    num_val = parse_number(capacity_value)
                    if not (expected[0] <= num_val <= expected[1]):
                        return False
            elif operator == '$greater_or_equal':
                if parse_number(capacity_value) < parse_number(expected):
                    return False
            elif operator == '$less_or_equal':
                if parse_number(capacity_value) > parse_number(expected):
                    return False
            elif operator == '$greater_than':
                if parse_number(capacity_value) <= parse_number(expected):
                    return False
            elif operator == '$less_than':
                if parse_number(capacity_value) >= parse_number(expected):
                    return False
        return True
    
    if isinstance(requirement, str) and isinstance(capacity_value, str):
        return requirement.lower() == capacity_value.lower()
    
    return requirement == capacity_value
def parse_number(value) -> float:
    """Extract numeric value from strings like '16 GB' or '100 W'"""
    if isinstance(value, (int, float)):
        return float(value)
    
    if isinstance(value, str):
        match = re.search(r'(-?\d+\.?\d*)', value)
        if match:
            return float(match.group(1))
    
    return 0

def get_matching_instances(capabilities: dict, capacity_data: dict) -> List[str]:
    """Get list of instances that match host requirements"""
    instances = capacity_data.get('capacity', {}).get('instances', {})
    # Handle flat structure
    if not instances:
        capacity_section = capacity_data.get('capacity', {})
        if any(key in capacity_section for key in ['num-cpus', 'mem-size', 'disk-size']):
            host_props = capabilities.get('host', {}).get('properties', {})
            if not host_props:
                return ['single-config']  # Changed from 'default'

            if check_instance_requirements(host_props, capacity_section, capacity_data):
                return ['single-config']  # Changed from 'default'
        return []
    
    # Handle instances structure
    host_props = capabilities.get('host', {}).get('properties', {})
    if not host_props:
        return list(instances.keys())
    
    matching = []
    for instance_name, instance_data in instances.items():
        if check_instance_requirements(host_props, instance_data, capacity_data):
            matching.append(instance_name)
    
    return matching
