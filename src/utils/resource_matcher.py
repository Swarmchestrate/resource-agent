# #!/usr/bin/env python3
# """
# Resource Matching Logic - Compares ask.yaml requirements with RA capacity profiles
# """

# import yaml
# from typing import Dict, List, Any, Tuple
# from pathlib import Path
# import logging

# logger = logging.getLogger(__name__)

# class ResourceMatcher:
#     """Matches resource requirements with RA capacity profiles"""
    
#     def __init__(self, capacity_profile_path: str = None):
#         """Initialize with path to capacity profile"""
#         if capacity_profile_path is None:
#             # Default path relative to project root
#             project_root = Path(__file__).parent.parent.parent
#             self.capacity_profile_path = project_root / "config" / "capacity_profiles.yaml"
#         else:
#             self.capacity_profile_path = Path(capacity_profile_path)
        
#         self.capacity_profile = self.load_capacity_profile()
    
#     def load_capacity_profile(self) -> Dict[str, Any]:
#         """Load the capacity profile for this RA"""
#         try:
#             if not self.capacity_profile_path.exists():
#                 logger.error(f"Capacity profile not found at: {self.capacity_profile_path}")
#                 return {}
            
#             with open(self.capacity_profile_path, 'r', encoding='utf-8') as file:
#                 profiles = yaml.safe_load(file)
            
#             # Get the profile for this RA (we'll need to pass RA ID)
#             logger.info(f"Loaded capacity profiles from: {self.capacity_profile_path}")
#             return profiles
            
#         except Exception as e:
#             logger.error(f"❌ Error loading capacity profile: {e}")
#             return {}
    
#     def get_ra_capacity(self, ra_id: str) -> Dict[str, Any]:
#         """Get capacity profile for specific RA"""
#         if 'capacity_profiles' in self.capacity_profile:
#             return self.capacity_profile['capacity_profiles'].get(ra_id, {})
#         return {}
    
#     def match_vm_requirements(self, vm_requirements: Dict, ra_capacity: Dict) -> Dict[str, Any]:
#         """
#         Match VM requirements with RA capacity
        
#         Args:
#             vm_requirements: Single VM requirements from ask.yaml
#             ra_capacity: RA capacity profile
            
#         Returns:
#             Match result with score and details
#         """
#         try:
#             logger.info(f"Matching VM requirements with RA capacity")
            
#             # Extract requirements
#             host_req = vm_requirements.get('requirements', {}).get('host', {}).get('properties', {})
#             os_req = vm_requirements.get('requirements', {}).get('os', {}).get('properties', {})
#             resource_req = vm_requirements.get('requirements', {}).get('resource', {}).get('properties', {})
#             pricing_req = vm_requirements.get('requirements', {}).get('pricing', {}).get('properties', {})
#             locality_req = vm_requirements.get('requirements', {}).get('locality', {}).get('properties', {})
#             energy_req = vm_requirements.get('requirements', {}).get('energy', {}).get('properties', {})
            
#             # Extract RA capacity
#             host_cap = ra_capacity.get('capabilities', {}).get('host', {}).get('properties', {})
#             os_cap = ra_capacity.get('capabilities', {}).get('os', {}).get('properties', {})
#             resource_cap = ra_capacity.get('capabilities', {}).get('resource', {}).get('properties', {})
#             pricing_cap = ra_capacity.get('capabilities', {}).get('pricing', {}).get('properties', {})
#             locality_cap = ra_capacity.get('capabilities', {}).get('locality', {}).get('properties', {})
#             energy_cap = ra_capacity.get('capabilities', {}).get('energy', {}).get('properties', {})
            
#             # Calculate match scores for each category
#             host_score = self._match_host_requirements(host_req, host_cap)
#             os_score = self._match_os_requirements(os_req, os_cap)
#             resource_score = self._match_resource_requirements(resource_req, resource_cap)
#             pricing_score = self._match_pricing_requirements(pricing_req, pricing_cap)
#             locality_score = self._match_locality_requirements(locality_req, locality_cap)
#             energy_score = self._match_energy_requirements(energy_req, energy_cap)
            
#             # Calculate overall score
#             total_score = (host_score + os_score + resource_score + 
#                           pricing_score + locality_score + energy_score) / 6
            
#             # Determine if requirements can be fulfilled
#             can_fulfill = total_score >= 70  # 70% threshold
            
#             match_result = {
#                 'can_fulfill': can_fulfill,
#                 'total_score': round(total_score, 2),
#                 'category_scores': {
#                     'host': host_score,
#                     'os': os_score,
#                     'resource': resource_score,
#                     'pricing': pricing_score,
#                     'locality': locality_score,
#                     'energy': energy_score
#                 },
#                 'fulfillment_details': {
#                     'host': host_score >= 70,
#                     'os': os_score >= 70,
#                     'resource': resource_score >= 70,
#                     'pricing': pricing_score >= 70,
#                     'locality': locality_score >= 70,
#                     'energy': energy_score >= 70
#                 }
#             }
            
#             logger.info(f"VM matching completed - Score: {total_score}%, Can fulfill: {can_fulfill}")
#             return match_result
            
#         except Exception as e:
#             logger.error(f"❌ Error matching VM requirements: {e}")
#             return {
#                 'can_fulfill': False,
#                 'total_score': 0,
#                 'error': str(e)
#             }
    
#     def _match_host_requirements(self, host_req: Dict, host_cap: Dict) -> float:
#         """Match host requirements (CPU, memory, storage)"""
#         score = 0
#         total_checks = 0
        
#         # CPU matching
#         if 'num-cpus' in host_req and 'num-cpus' in host_cap:
#             total_checks += 1
#             req_cpus = host_req['num-cpus']
#             cap_cpus = host_cap['num-cpus']
            
#             if isinstance(req_cpus, dict) and '$in_range' in req_cpus:
#                 # Range requirement: { $in_range: [2, 4] }
#                 min_cpus, max_cpus = req_cpus['$in_range']
#                 if min_cpus <= cap_cpus <= max_cpus:
#                     score += 100
#                 elif cap_cpus >= min_cpus:
#                     score += 80
#                 else:
#                     score += 0
#             else:
#                 # Exact requirement
#                 if req_cpus == cap_cpus:
#                     score += 100
#                 else:
#                     score += 0
        
#         # Memory matching
#         if 'mem-size' in host_req and 'mem-size' in host_cap:
#             total_checks += 1
#             req_mem = host_req['mem-size']
#             cap_mem = host_cap['mem-size']
            
#             if isinstance(req_mem, dict) and '$greater_or_equal' in req_mem:
#                 # Minimum requirement: { $greater_or_equal: "16 GB" }
#                 req_mem_gb = self._parse_memory_gb(req_mem['$greater_or_equal'])
#                 cap_mem_gb = self._parse_memory_gb(cap_mem)
                
#                 if cap_mem_gb >= req_mem_gb:
#                     score += 100
#                 else:
#                     score += 0
#             else:
#                 # Exact requirement
#                 if req_mem == cap_mem:
#                     score += 100
#                 else:
#                     score += 0
        
#         # Storage matching
#         if 'disk-size' in host_req and 'disk-size' in host_cap:
#             total_checks += 1
#             req_storage = host_req['disk-size']
#             cap_storage = host_cap['disk-size']
            
#             if isinstance(req_storage, dict) and '$greater_or_equal' in req_storage:
#                 # Minimum requirement
#                 req_storage_gb = self._parse_storage_gb(req_storage['$greater_or_equal'])
#                 cap_storage_gb = self._parse_storage_gb(cap_storage)
                
#                 if cap_storage_gb >= req_storage_gb:
#                     score += 100
#                 else:
#                     score += 0
#             else:
#                 # Exact requirement
#                 if req_storage == cap_storage:
#                     score += 100
#                 else:
#                     score += 0
        
#         return score / max(total_checks, 1)
    
#     def _match_os_requirements(self, os_req: Dict, os_cap: Dict) -> float:
#         """Match OS requirements"""
#         score = 0
#         total_checks = 0
        
#         # OS type matching
#         if 'type' in os_req and 'type' in os_cap:
#             total_checks += 1
#             if os_req['type'] == os_cap['type']:
#                 score += 100
#             else:
#                 score += 0
        
#         # Distribution matching
#         if 'distribution' in os_req and 'distribution' in os_cap:
#             total_checks += 1
#             if os_req['distribution'] == os_cap['distribution']:
#                 score += 100
#             else:
#                 score += 0
        
#         return score / max(total_checks, 1)
    
#     def _match_resource_requirements(self, resource_req: Dict, resource_cap: Dict) -> float:
#         """Match resource requirements (provider, type)"""
#         score = 0
#         total_checks = 0
        
#         # Provider matching
#         if 'provider' in resource_req and 'provider' in resource_cap:
#             total_checks += 1
#             req_provider = resource_req['provider']
#             cap_provider = resource_cap['provider']
            
#             if isinstance(req_provider, dict) and '$in' in req_provider:
#                 # List requirement: { $in: ["Amazon", "Azure"] }
#                 if cap_provider in req_provider['$in']:
#                     score += 100
#                 else:
#                     score += 0
#             else:
#                 # Exact requirement
#                 if req_provider == cap_provider:
#                     score += 100
#                 else:
#                     score += 0
        
#         return score / max(total_checks, 1)
    
#     def _match_pricing_requirements(self, pricing_req: Dict, pricing_cap: Dict) -> float:
#         """Match pricing requirements"""
#         score = 0
#         total_checks = 0
        
#         # Cost matching
#         if 'cost' in pricing_req and 'cost' in pricing_cap:
#             total_checks += 1
#             req_cost = pricing_req['cost']
#             cap_cost = pricing_cap['cost']
            
#             if isinstance(req_cost, dict) and '$less_or_equal' in req_cost:
#                 # Maximum requirement: { $less_or_equal: "1 credit/hr" }
#                 req_cost_val = self._parse_cost(req_cost['$less_or_equal'])
#                 cap_cost_val = self._parse_cost(cap_cost)
                
#                 if cap_cost_val <= req_cost_val:
#                     score += 100
#                 else:
#                     score += 0
#             else:
#                 # Exact requirement
#                 if req_cost == cap_cost:
#                     score += 100
#                 else:
#                     score += 0
        
#         return score / max(total_checks, 1)
    
#     def _match_locality_requirements(self, locality_req: Dict, locality_cap: Dict) -> float:
#         """Match locality requirements"""
#         score = 0
#         total_checks = 0
        
#         # Continent matching
#         if 'continent' in locality_req and 'continent' in locality_cap:
#             total_checks += 1
#             req_continent = locality_req['continent']
#             cap_continent = locality_cap['continent']
            
#             if isinstance(req_continent, dict) and '$in' in req_continent:
#                 # List requirement
#                 if cap_continent in req_continent['$in']:
#                     score += 100
#                 else:
#                     score += 0
#             else:
#                 # Exact requirement
#                 if req_continent == cap_continent:
#                     score += 100
#                 else:
#                     score += 0
        
#         return score / max(total_checks, 1)
    
#     def _match_energy_requirements(self, energy_req: Dict, energy_cap: Dict) -> float:
#         """Match energy requirements"""
#         score = 0
#         total_checks = 0
        
#         # Energy type matching
#         if 'energy-type' in energy_req and 'energy-type' in energy_cap:
#             total_checks += 1
#             req_energy = energy_req['energy-type']
#             cap_energy = energy_cap['energy-type']
            
#             if isinstance(req_energy, dict) and '$in' in req_energy:
#                 # List requirement
#                 if cap_energy in req_energy['$in']:
#                     score += 100
#                 else:
#                     score += 0
#             else:
#                 # Exact requirement
#                 if req_energy == cap_energy:
#                     score += 100
#                 else:
#                     score += 0
        
#         return score / max(total_checks, 1)
    
#     def _parse_memory_gb(self, memory_str: str) -> float:
#         """Parse memory string to GB value"""
#         try:
#             if 'GB' in memory_str:
#                 return float(memory_str.replace('GB', '').strip())
#             elif 'MB' in memory_str:
#                 return float(memory_str.replace('MB', '').strip()) / 1024
#             else:
#                 return 0
#         except:
#             return 0
    
#     def _parse_storage_gb(self, storage_str: str) -> float:
#         """Parse storage string to GB value"""
#         try:
#             if 'GB' in storage_str:
#                 return float(storage_str.replace('GB', '').strip())
#             else:
#                 return 0
#         except:
#             return 0
    
#     def _parse_cost(self, cost_str: str) -> float:
#         """Parse cost string to numeric value"""
#         try:
#             # Handle both "1 credit / hr" and "0.0416 credit/hr" formats
#             if 'credit/hr' in cost_str or 'credit / hr' in cost_str:
#                 # Remove "credit/hr" or "credit / hr" and any extra spaces
#                 if 'credit/hr' in cost_str:
#                     parsed = cost_str.replace('credit/hr', '').strip()
#                 else:
#                     parsed = cost_str.replace('credit / hr', '').strip()
#                 # Handle case where there might be extra spaces: "1 " -> "1"
#                 parsed = parsed.strip()
#                 result = float(parsed)
#                 return result
#             else:
#                 return 0
#         except Exception as e:
#             return 0

# def main():
#     """Test the Resource Matcher"""
#     print("🧪 Testing Resource Matcher")
#     print("=" * 50)
    
#     matcher = ResourceMatcher()
    
#     # Test with real ask.yaml requirements for vm1
#     test_requirements = {
#         'vm_name': 'vm1',
#         'requirements': {
#             'host': {
#                 'properties': {
#                     'num-cpus': {'$in_range': [2, 4]},
#                     'mem-size': {'$greater_or_equal': '16 GB'},
#                     'disk-size': '10 GB',
#                     'cpu-architecture': 'x86_64'
#                 }
#             },
#             'os': {
#                 'properties': {
#                     'type': 'linux',
#                     'distribution': 'ubuntu',
#                     'version': '22.04'
#                 }
#             },
#             'resource': {
#                 'properties': {
#                     'provider': {'$in': ['Amazon', 'Azure']},
#                     'capacity-provider': 'ACME',
#                     'type': 'cloud'
#                 }
#             },
#             'pricing': {
#                 'properties': {
#                     'cost': {'$less_or_equal': '1 credit / hr'}
#                 }
#             },
#             'locality': {
#                 'properties': {
#                     'continent': {'$in': ['Europe', 'Asia']},
#                     'country': {'$in': ['Spain', 'UK', 'India']},
#                     'city': {'$in': ['Madrid', 'London', 'Mumbai']}
#                 }
#             },
#             'energy': {
#                 'properties': {
#                     'energy-type': 'Green',
#                     'powered-type': 'Battery',
#                     'consumption': {'$less_or_equal': '100 W'}
#                 }
#             }
#         }
#     }
    
#     # Test with aws-ra2 capacity
#     aws_ra2_capacity = matcher.get_ra_capacity('aws-ra2')
#     if aws_ra2_capacity:
#         result = matcher.match_vm_requirements(test_requirements, aws_ra2_capacity)
#         print(f"✅ Matching result: {result}")
#     else:
#         print("❌ Could not load aws-ra2 capacity profile")

# if __name__ == "__main__":
#     main()
