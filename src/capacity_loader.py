#!/usr/bin/env python3
"""
Resource Matching System: Capacity Profiles Loader
This module handles loading and parsing capacity_profiles.yaml files
"""

import yaml
from typing import Dict, List, Any, Optional
from pathlib import Path

class CapacityProfilesLoader:
    """Loads and manages RA capacity profiles"""
    
    def __init__(self, capacity_profiles_path: str = None):
        """Initialize with path to capacity_profiles.yaml file"""
        if capacity_profiles_path is None:
            # Default path relative to project root
            project_root = Path(__file__).parent.parent
            self.capacity_profiles_path = project_root / "config" / "capacity_profiles.yaml"
        else:
            self.capacity_profiles_path = Path(capacity_profiles_path)
    
    def load_capacity_profiles(self) -> Dict[str, Any]:
        """Load and parse the capacity_profiles.yaml file"""
        try:
            if not self.capacity_profiles_path.exists():
                raise FileNotFoundError(f"capacity_profiles.yaml not found at: {self.capacity_profiles_path}")
            
            with open(self.capacity_profiles_path, 'r', encoding='utf-8') as file:
                profiles = yaml.safe_load(file)
            
            print(f"Successfully loaded capacity profiles from: {self.capacity_profiles_path}")
            return profiles
            
        except Exception as e:
            print(f" Error loading capacity profiles: {e}")
            return {}
    
    def get_available_ras(self, profiles: Dict[str, Any]) -> List[str]:
        """Get list of available Resource Agents"""
        if 'capacity_profiles' not in profiles:
            return []
        
        ra_list = list(profiles['capacity_profiles'].keys())
        print(f" Found {len(ra_list)} Resource Agents: {', '.join(ra_list)}")
        return ra_list
    
    def get_ra_capabilities(self, profiles: Dict[str, Any], ra_name: str) -> Dict[str, Any]:
        """Get capabilities for a specific RA"""
        if 'capacity_profiles' not in profiles or ra_name not in profiles['capacity_profiles']:
            return {}
        
        ra_profile = profiles['capacity_profiles'][ra_name]
        return ra_profile.get('capabilities', {})
    
    def analyze_ra_capacity(self, profiles: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Analyze capacity of each RA"""
        capacity_analysis = {}
        
        if 'capacity_profiles' not in profiles:
            return capacity_analysis
        
        for ra_name, ra_profile in profiles['capacity_profiles'].items():
            capabilities = ra_profile.get('capabilities', {})
            host_caps = capabilities.get('host', {}).get('properties', {})
            
            analysis = {
                'metadata': ra_profile.get('metadata', {}),
                'cpu_cores': host_caps.get('num-cpus', 0),
                'memory_gb': self._parse_memory(host_caps.get('mem-size', '0 GB')),
                'storage_gb': self._parse_storage(host_caps.get('disk-size', '0 GB')),
                'architecture': host_caps.get('cpu-architecture', 'unknown'),
                'cost_per_hour': self._parse_cost(capabilities.get('pricing', {}).get('properties', {}).get('cost', '0 credit/hr')),
                'location': capabilities.get('locality', {}).get('properties', {}),
                'energy': capabilities.get('energy', {}).get('properties', {})
            }
            
            capacity_analysis[ra_name] = analysis
            print(f" {ra_name}: {analysis['cpu_cores']} cores, {analysis['memory_gb']} GB RAM, {analysis['storage_gb']} GB storage")
        
        return capacity_analysis
    
    def _parse_memory(self, memory_str: str) -> float:
        """Parse memory string to GB value"""
        try:
            if 'GB' in memory_str:
                return float(memory_str.replace('GB', '').strip())
            elif 'MB' in memory_str:
                return float(memory_str.replace('MB', '').strip()) / 1024
            else:
                return 0.0
        except:
            return 0.0
    
    def _parse_storage(self, storage_str: str) -> float:
        """Parse storage string to GB value"""
        try:
            if 'GB' in storage_str:
                return float(storage_str.replace('GB', '').strip())
            elif 'TB' in storage_str:
                return float(storage_str.replace('TB', '').strip()) * 1024
            else:
                return 0.0
        except:
            return 0.0
    
    def _parse_cost(self, cost_str: str) -> float:
        """Parse cost string to numeric value"""
        try:
            if 'credit/hr' in cost_str:
                return float(cost_str.replace('credit/hr', '').strip())
            else:
                return 0.0
        except:
            return 0.0
    
    def get_capacity_summary(self) -> Dict[str, Any]:
        """Main method to get capacity summary"""
        print("🔍 Step 2: Loading RA Capacity Profiles")
        print("=" * 60)
        
        # Load capacity profiles
        profiles = self.load_capacity_profiles()
        if not profiles:
            return {}
        
        # Get available RAs
        available_ras = self.get_available_ras(profiles)
        
        # Analyze capacity
        capacity_analysis = self.analyze_ra_capacity(profiles)
        
        print(f" Total RAs analyzed: {len(capacity_analysis)}")
        print("=" * 60)
        
        return {
            'profiles': profiles,
            'available_ras': available_ras,
            'capacity_analysis': capacity_analysis
        }

def main():
    """Test the capacity profiles loader"""
    print(" Testing Capacity Profiles Loader")
    print("=" * 60)
    
    loader = CapacityProfilesLoader()
    summary = loader.get_capacity_summary()
    
    if summary:
        print("\n Capacity Summary:")
        for ra_name, analysis in summary['capacity_analysis'].items():
            print(f"  • {ra_name}:")
            print(f"    - CPU: {analysis['cpu_cores']} cores")
            print(f"    - RAM: {analysis['memory_gb']} GB")
            print(f"    - Storage: {analysis['storage_gb']} GB")
            print(f"    - Cost: {analysis['cost_per_hour']} credit/hr")
    else:
        print(" No capacity profiles loaded")

if __name__ == "__main__":
    main()

