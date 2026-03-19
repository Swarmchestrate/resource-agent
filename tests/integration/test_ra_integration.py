#!/usr/bin/env python3
"""
Integration test for Resource Agent.

Submits a job via SwarmchestrateClient and verifies the flow completes.

Usage:
  make test
"""

import sys
sys.path.insert(0, "/app/src")

from job_submission_client import SwarmchestrateClient

REQUEST_PATH = "/app/tests/integration/configs/submit-request.yaml"


if __name__ == "__main__":
    client = SwarmchestrateClient(client_id="test-client")
    client.handle_client_request(REQUEST_PATH)

    print("\n" + "=" * 60, flush=True)
    print("INTEGRATION TEST PASSED", flush=True)
    print("=" * 60, flush=True)
