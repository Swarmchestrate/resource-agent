#!/usr/bin/env python3
"""
Job Submission Client
Submits resource requests to RA network and compiles responses
"""
import yaml
import time
import logging
import sys
import random
from pathlib import Path
from itertools import product
from swchp2pcom import SwchPeer


class JobSubmissionClient:
    """Client for submitting jobs and collecting resource offers"""

    def __init__(self, client_id="job-client"):
        self.client_id = client_id
        self.peer = None
        self.job_responses = {}
        self.job_complete = False

        # Setup minimal logging
        logging.basicConfig(level=logging.WARNING)
        self.logger = logging.getLogger(f"JobClient-{client_id}")

    def load_ask_yaml(self, file_path):
        """Load ask.yaml file with path resolution"""
        try:
            path = Path(file_path)
            
            # Resolve relative paths when running from src directory
            if Path.cwd().name == 'src' and not path.is_absolute() and not str(file_path).startswith('../'):
                path = Path("../") / file_path
            
            if not path.exists():
                print(f"File not found: {path.resolve()}")
                return None
            
            with open(path, 'r') as f:
                yaml_data = yaml.safe_load(f)
                
            if yaml_data:
                print(f"Loaded {len(yaml_data)} resource requests from ask.yaml")
                # Generate resource summary
                resource_details = []
                for name, data in yaml_data.items():
                    count = data.get('count', 1) if isinstance(data, dict) else 1
                    capabilities = data.get('capabilities', {}) if isinstance(data, dict) else {}
                    category_count = len(capabilities)
                    resource_details.append(f"{name}(×{count}, {category_count} requirements)")
                print(f"📋 Resources: {', '.join(resource_details)}")
            else:
                print("YAML data is None or empty")
                
            return yaml_data
            
        except Exception as e:
            print(f"Failed to load ask.yaml: {e}")
            return None

    def submit_job(self, ask_yaml_path, hub_host="35.179.157.83", hub_port=5001):
        """Submit job to RA network via hub"""
        ask_data = self.load_ask_yaml(ask_yaml_path)
        if not ask_data:
            return False

        print("Swarmchestrate Job Submission Client")
        print("=" * 60)

        # Initialize P2P client
        self.peer = SwchPeer(
            peer_id=self.client_id,
            enable_rejoin=False,
            metadata={"peer_type": "JOB_CLIENT", "client_id": self.client_id}
        )

        # Register response handler
        self.peer.register_message_handler("MSG_RESOURCE_RESPONSE", self._handle_resource_response)

        def on_entered():
            print(f"Connected to hub {hub_host}:{hub_port}")

            # Find hub RA
            hub_ras = self.peer.find_peers({"peer_type": "RA", "ra_id": "Aws-UK-RA"})
            if not hub_ras:
                print("Hub RA (Aws-UK-RA) not found!")
                return

            hub_ra_id = hub_ras[0]
            print(f"Connected to hub: {hub_ra_id}")

            # Create job submission message
            job_message = {
                "job_id": f"job_{int(time.time())}",
                "client_id": self.client_id,
                "ask_yaml": ask_data,
                "timestamp": time.time(),
                "action": "broadcast_job"
            }

            print("📡 Broadcasting job to all RAs...")
            self.peer.send(hub_ra_id, "MSG_JOB_SUBMIT", job_message)
            print("Waiting for responses...")

        try:
            self.peer.enter(hub_host, hub_port).addCallback(lambda _: on_entered())
            self.peer.start()

        except Exception as e:
            self.logger.error(f"Failed to connect: {e}")
            return False

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
        if len(self.job_responses.get(job_id, {})) >= len(all_ras):
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
            
            for i, combination in enumerate(valid_combinations, 1):
                combo_str = f"{i}. "
                
                resource_items = []
                for resource_name in sorted(combination.keys()):
                    allocation = combination[resource_name]
                    ra_id = allocation['ra_id']
                    resource_items.append(f"{resource_name}: {ra_id}")
                
                combo_str += ", ".join(resource_items)
                print(combo_str)
            
            print("-" * 60)
            
            # Randomly select one combination
            selected_index = random.randint(0, len(valid_combinations) - 1)
            selected_combination = valid_combinations[selected_index]
            
            print(f"\nSELECTED OFFER (Randomly chosen: #{selected_index + 1}):")
            print("=" * 60)
            
            resource_items = []
            for resource_name in sorted(selected_combination.keys()):
                allocation = selected_combination[resource_name]
                ra_id = allocation['ra_id']
                resource_items.append(f"{resource_name}: {ra_id}")
            
            print(", ".join(resource_items))
            print("=" * 60)
        else:
            print("No valid combinations found!")
            print("   No combination can fulfill all resource requirements.")

        # Complete job processing
        time.sleep(1)
        self.job_complete = True
        self.peer.leave().addCallback(lambda _: self.peer.stop())

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
                    'instance_type': response.get('bid', {}).get('instance_type', 'unknown')
                }

            valid_combinations.append(combination)

        return valid_combinations


def main():
    if len(sys.argv) < 2:
        sys.exit("Error: ask.yaml path required")

    ask_yaml_path = sys.argv[1]
    hub_host = sys.argv[2] if len(sys.argv) > 2 else "35.179.157.83"
    hub_port = int(sys.argv[3]) if len(sys.argv) > 3 else 5001

    client = JobSubmissionClient()
    client.submit_job(ask_yaml_path, hub_host, hub_port)


if __name__ == "__main__":
    main()
