#!/usr/bin/env python3
"""
Job Submission Client - Submits ask.yaml to P2P network
Based on the Swarmchestrate workflow diagram
"""
import yaml
import time
import logging
import sys
from pathlib import Path
from swchp2pcom import SwchPeer


class JobSubmissionClient:
    """Client that submits TOSCA ask.yaml files to the P2P network"""

    def __init__(self, client_id="job-client"):
        self.client_id = client_id
        self.peer = None
        self.job_responses = {}
        self.job_complete = False

        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(f"JobClient-{client_id}")

    def load_ask_yaml(self, file_path):
        """Load ask.yaml file"""
        try:
            with open(file_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            self.logger.error(f"Failed to load ask.yaml: {e}")
            return None

    def submit_job(self, ask_yaml_path, hub_host="35.179.157.83", hub_port=5001):
        """Submit job to P2P network via hub"""

        # Load ask.yaml
        ask_data = self.load_ask_yaml(ask_yaml_path)
        if not ask_data:
            return False

        print("Swarmchestrate Job Submission Client")
        print("=" * 60)
        print(f"Loading ask.yaml: {ask_yaml_path}")
        print(f"Found {len(ask_data)} VM requests")

        # Initialize P2P client
        self.peer = SwchPeer(
            peer_id=self.client_id,
            enable_rejoin=False,
            metadata={"peer_type": "JOB_CLIENT"}
        )

        # Register message handlers
        self.peer.register_message_handler("MSG_RESOURCE_RESPONSE", self._handle_resource_response)
        self.peer.register_message_handler("MSG_JOB_RESULT", self._handle_job_result)

        def on_entered():
            print(f" Connected to P2P network via hub {hub_host}:{hub_port}")

            # Find hub RA
            hub_ras = self.peer.find_peers({"peer_type": "RA", "ra_id": "Aws-UK-RA"})
            if not hub_ras:
                print(" Hub RA not found!")
                return

            hub_ra_id = hub_ras[0]
            print(f"Found hub RA: {hub_ra_id}")

            # Submit job to hub for broadcasting
            job_message = {
                "job_id": f"job_{int(time.time())}",
                "client_id": self.client_id,
                "ask_yaml": ask_data,
                "timestamp": time.time(),
                "action": "broadcast_job"
            }

            print("Broadcasting job to all RAs via hub...")
            self.peer.send(hub_ra_id, "MSG_JOB_SUBMIT", job_message)

            # Wait for responses
            print("Waiting for resource offers from RAs...")

        try:
            self.peer.enter(hub_host, hub_port).addCallback(lambda _: on_entered())
            self.peer.start()

        except Exception as e:
            self.logger.error(f"Failed to connect: {e}")
            return False

    def _handle_resource_response(self, peer_id, message):
        """Handle YES/NO resource responses from RAs"""
        print(f"Resource response received from {peer_id}")

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

        print(f"    RA: {ra_id} ({provider})")
        for resource_name, response in responses.items():
            answer = response.get('answer', 'unknown')
            if answer == 'yes':
                cost = response.get('bid', {}).get('cost_per_hour', 'N/A')
                print(f"      ✅ {resource_name}: YES (Cost: {cost} credits/hr)")
            else:
                reason = response.get('reason', 'No reason provided')
                print(f"      ❌ {resource_name}: NO ({reason})")

        # Check if we have responses from all RAs
        all_ras = self.peer.find_peers({"peer_type": "RA"})
        if len(self.job_responses.get(job_id, {})) >= len(all_ras):
            self._compile_valid_combinations(job_id)

    def _compile_valid_combinations(self, job_id):
        """Compile all possible valid resource combinations"""
        print("\nCompiling all possible resource offers...")
        print("=" * 60)

        ra_responses = self.job_responses.get(job_id, {})

        # Display all responses in a table format
        print("Response Summary:")
        print("-" * 60)

        # Get all resource names from ask.yaml
        ask_data = None
        for ra_id, ra_data in ra_responses.items():
            if ra_data['responses']:
                ask_data = list(ra_data['responses'].keys())
                break

        if not ask_data:
            print("❌ No resource requirements found")
            return

        # Create response matrix
        print(f"{'RA (Provider)':<20} {'Resource1':<15} {'Resource2':<15}")
        print("-" * 60)

        for ra_id, ra_data in ra_responses.items():
            provider = ra_data['provider']
            responses = ra_data['responses']

            resource1_answer = responses.get('resource1', {}).get('answer', 'N/A')
            resource2_answer = responses.get('resource2', {}).get('answer', 'N/A')

            print(f"{ra_id} ({provider})"[:19].ljust(20) +
                  f"{resource1_answer}"[:14].ljust(15) +
                  f"{resource2_answer}"[:14].ljust(15))

        print("\nFinding valid resource combinations...")
        print("=" * 60)

        # Find all valid combinations
        valid_combinations = self._find_valid_combinations(ra_responses, ask_data)

        if valid_combinations:
            print(f"✅ Found {len(valid_combinations)} valid combination(s):")
            print("-" * 60)

            for i, combination in enumerate(valid_combinations, 1):
                print(f"Combination {i}:")
                total_cost = 0

                for resource_name, allocation in combination.items():
                    ra_id = allocation['ra_id']
                    provider = allocation['provider']
                    cost = allocation['cost_per_hour']
                    count = allocation['count']
                    total_cost += cost * count

                    print(f"  • {resource_name}: {ra_id} ({provider}) - {cost} credits/hr × {count}")

                print(f"  Total Cost: {total_cost:.2f} credits/hr")
                print()
        else:
            print("❌ No valid combinations found!")
            print("   No single combination can fulfill all resource requirements.")

        # Simulate job completion
        time.sleep(2)
        self.job_complete = True
        self.peer.leave().addCallback(lambda _: self.peer.stop())

    def _find_valid_combinations(self, ra_responses, resource_names):
        """Find all valid combinations that can fulfill all resource requirements"""
        from itertools import product

        valid_combinations = []

        # For each resource, get list of RAs that can provide it
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

        # Check if all resources have at least one provider
        for resource_name, providers in resource_providers.items():
            if not providers:
                print(f"No RA can provide {resource_name}")
                return []

        # Generate all possible combinations
        provider_lists = [resource_providers[name] for name in resource_names]

        for combination_tuple in product(*provider_lists):
            combination = {}

            # Create combination dictionary
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

    def _handle_job_result(self, peer_id, message):
        """Handle job execution results"""
        print(f"✅ Job result from {peer_id}: {message}")


def main():
    """Main function"""
    if len(sys.argv) < 2:
        print("Usage: python job_submission_client.py <ask.yaml_path>")
        print("Example: python job_submission_client.py tosca/outputs/ask.yaml")
        sys.exit(1)

    ask_yaml_path = sys.argv[1]

    if not Path(ask_yaml_path).exists():
        print(f"❌ File not found: {ask_yaml_path}")
        sys.exit(1)

    client = JobSubmissionClient()
    client.submit_job(ask_yaml_path)


if __name__ == "__main__":
    main()
