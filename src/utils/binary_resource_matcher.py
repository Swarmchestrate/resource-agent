class BinaryResourceMatcher:
    def __init__(self):
        pass
    
    def match_vm_requirements(self, vm_req, ra_capacity):
        """Binary matching - returns True/False based on requirement fulfillment"""

        if not self._check_host_requirements(vm_req.get('requirements', {}).get('host', {}), 
                                            ra_capacity.get('capabilities', {}).get('host', {})):
            return {'can_fulfill': False, 'reason': 'Host requirements not met'}
            
        if not self._check_os_requirements(vm_req.get('requirements', {}).get('os', {}), 
                                        ra_capacity.get('capabilities', {}).get('os', {})):
            return {'can_fulfill': False, 'reason': 'OS requirements not met'}
            
        if not self._check_resource_requirements(vm_req.get('requirements', {}).get('resource', {}), 
                                                ra_capacity.get('capabilities', {}).get('resource', {})):
            return {'can_fulfill': False, 'reason': 'Resource requirements not met'}
            
        if not self._check_pricing_requirements(vm_req.get('requirements', {}).get('pricing', {}), 
                                            ra_capacity.get('capabilities', {}).get('pricing', {})):
            return {'can_fulfill': False, 'reason': 'Pricing requirements not met'}
            
        if not self._check_locality_requirements(vm_req.get('requirements', {}).get('locality', {}), 
                                                ra_capacity.get('capabilities', {}).get('locality', {})):
            return {'can_fulfill': False, 'reason': 'Locality requirements not met'}
            
        if not self._check_energy_requirements(vm_req.get('requirements', {}).get('energy', {}), 
                                            ra_capacity.get('capabilities', {}).get('energy', {})):
            return {'can_fulfill': False, 'reason': 'Energy requirements not met'}
        
        return {'can_fulfill': True, 'reason': 'All requirements fulfilled'}

    def _check_host_requirements(self, host_req, host_cap):
        """Validate CPU, memory, and disk requirements"""
        properties_req = host_req.get('properties', {})
        properties_cap = host_cap.get('properties', {})
        
        # Check CPU requirements
        if 'num-cpus' in properties_req:
            req_cpus = properties_req['num-cpus']
            cap_cpus = properties_cap.get('num-cpus', 0)
            
            if isinstance(req_cpus, dict) and '$in_range' in req_cpus:
                min_cpus, max_cpus = req_cpus['$in_range']
                if not (min_cpus <= cap_cpus <= max_cpus):
                    return False
            elif req_cpus != cap_cpus:
                return False
        
        # Check memory requirements
        if 'mem-size' in properties_req:
            req_mem = properties_req['mem-size']
            cap_mem = properties_cap.get('mem-size', '0 GB')
            
            if isinstance(req_mem, dict) and '$greater_or_equal' in req_mem:
                min_mem_gb = self._parse_memory_gb(req_mem['$greater_or_equal'])
                cap_mem_gb = self._parse_memory_gb(cap_mem)
                if cap_mem_gb < min_mem_gb:
                    return False
            elif req_mem != cap_mem:
                return False
        
        # Check disk requirements
        if 'disk-size' in properties_req:
            req_disk = properties_req['disk-size']
            cap_disk = properties_cap.get('disk-size', '0 GB')
            
            if isinstance(req_disk, dict) and '$greater_or_equal' in req_disk:
                min_disk_gb = self._parse_storage_gb(req_disk['$greater_or_equal'])
                cap_disk_gb = self._parse_storage_gb(cap_disk)
                if cap_disk_gb < min_disk_gb:
                    return False
            elif req_disk != cap_disk:
                return False
        
        return True

    def _check_os_requirements(self, os_req, os_cap):
        """Validate operating system requirements"""
        properties_req = os_req.get('properties', {})
        properties_cap = os_cap.get('properties', {})
        
        # Check OS type
        if 'type' in properties_req:
            if properties_req['type'] != properties_cap.get('type'):
                return False
        
        # Check distribution
        if 'distribution' in properties_req:
            if properties_req['distribution'] != properties_cap.get('distribution'):
                return False
                
        # Check version
        if 'version' in properties_req:
            if properties_req['version'] != properties_cap.get('version'):
                return False
        
        return True

    def _check_resource_requirements(self, resource_req, resource_cap):
        """Validate provider and resource type requirements"""
        properties_req = resource_req.get('properties', {})
        properties_cap = resource_cap.get('properties', {})
        
        # Check provider
        if 'provider' in properties_req:
            req_provider = properties_req['provider']
            cap_provider = properties_cap.get('provider')
            
            if isinstance(req_provider, dict) and '$in' in req_provider:
                if cap_provider not in req_provider['$in']:
                    return False
            elif req_provider != cap_provider:
                return False
        
        return True

    def _check_pricing_requirements(self, pricing_req, pricing_cap):
        """Validate cost and pricing requirements"""
        properties_req = pricing_req.get('properties', {})
        properties_cap = pricing_cap.get('properties', {})
        
        # Check cost
        if 'cost' in properties_req:
            req_cost = properties_req['cost']
            cap_cost = properties_cap.get('cost', '0 credit/hr')
            
            if isinstance(req_cost, dict) and '$less_or_equal' in req_cost:
                max_budget = self._parse_cost(req_cost['$less_or_equal'])
                actual_cost = self._parse_cost(cap_cost)
                if actual_cost > max_budget:
                    return False
            elif req_cost != cap_cost:
                return False
        
        return True

    def _check_locality_requirements(self, locality_req, locality_cap):
        """Validate location and geographical requirements"""
        properties_req = locality_req.get('properties', {})
        properties_cap = locality_cap.get('properties', {})
        
        # Check continent
        if 'continent' in properties_req:
            req_continent = properties_req['continent']
            cap_continent = properties_cap.get('continent')
            
            if isinstance(req_continent, dict) and '$in' in req_continent:
                if cap_continent not in req_continent['$in']:
                    return False
            elif req_continent != cap_continent:
                return False
        
        # Check country
        if 'country' in properties_req:
            req_country = properties_req['country']
            cap_country = properties_cap.get('country')
            
            if isinstance(req_country, dict) and '$in' in req_country:
                if cap_country not in req_country['$in']:
                    return False
            elif req_country != cap_country:
                return False
        
        return True

    def _check_energy_requirements(self, energy_req, energy_cap):
        """Validate energy and power requirements"""
        properties_req = energy_req.get('properties', {})
        properties_cap = energy_cap.get('properties', {})
        
        # Check energy type
        if 'energy-type' in properties_req:
            if properties_req['energy-type'] != properties_cap.get('energy-type'):
                return False
        
        return True

    def _parse_memory_gb(self, mem_str):
        """Parse memory string to GB value"""
        if isinstance(mem_str, str):
            return float(mem_str.split()[0])
        return float(mem_str)

    def _parse_storage_gb(self, storage_str):
        """Parse storage string to GB value"""
        if isinstance(storage_str, str):
            return float(storage_str.split()[0])
        return float(storage_str)

    def _parse_cost(self, cost_str):
        """Parse cost string to numerical value"""
        if isinstance(cost_str, str):
            return float(cost_str.split()[0])
        return float(cost_str)