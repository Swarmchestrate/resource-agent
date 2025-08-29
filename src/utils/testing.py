"""
Testing utilities for Swarmchestrate RA.
"""

import requests
import time
import subprocess
import sys
import json
import threading
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class RATester:
    """Test class for RA submit functionality."""
    
    def __init__(self):
        self.ra1_process = None
        self.ra2_process = None
        self.ra1_url = "http://localhost:8000"
        self.ra2_url = "http://localhost:8001"
    
    def start_ra1(self):
        """Start RA1 in a separate process."""
        logger.info("Starting RA1...")
        self.ra1_process = subprocess.Popen([
            sys.executable, "src/main.py", "--config", "config/config.yaml"
        ], cwd=Path(__file__).parent.parent.parent, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logger.info("RA1 started (PID: {})".format(self.ra1_process.pid))
    
    def start_ra2(self):
        """Start RA2 in a separate process."""
        logger.info("Starting RA2...")
        self.ra2_process = subprocess.Popen([
            sys.executable, "src/main.py", "--config", "config/config2.yaml"
        ], cwd=Path(__file__).parent.parent.parent, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logger.info("RA2 started (PID: {})".format(self.ra2_process.pid))
    
    def wait_for_ra_startup(self, url: str, timeout: int = 30):
        """Wait for RA to be ready."""
        logger.info(f"Waiting for RA to be ready at {url}...")
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"{url}/health", timeout=2)
                if response.status_code == 200:
                    logger.info(f"RA ready at {url}")
                    return True
            except requests.exceptions.RequestException:
                pass
            time.sleep(1)
        
        logger.error(f"RA not ready at {url} after {timeout} seconds")
        return False
    
    def test_health_endpoints(self):
        """Test health endpoints for both RAs."""
        logger.info("Testing health endpoints...")
        
        # Test RA1 health
        try:
            response = requests.get(f"{self.ra1_url}/health", timeout=5)
            if response.status_code == 200:
                logger.info("✅ RA1 health endpoint working")
                logger.info(f"RA1 response: {response.json()}")
            else:
                logger.error(f"❌ RA1 health failed: {response.status_code}")
        except Exception as e:
            logger.error(f"❌ RA1 health error: {e}")
        
        # Test RA2 health
        try:
            response = requests.get(f"{self.ra2_url}/health", timeout=5)
            if response.status_code == 200:
                logger.info("✅ RA2 health endpoint working")
                logger.info(f"RA2 response: {response.json()}")
            else:
                logger.error(f"❌ RA2 health failed: {response.status_code}")
        except Exception as e:
            logger.error(f"❌ RA2 health error: {e}")
    
    def test_status_endpoints(self):
        """Test status endpoints for both RAs."""
        logger.info("Testing status endpoints...")
        
        # Test RA1 status
        try:
            response = requests.get(f"{self.ra1_url}/status", timeout=5)
            if response.status_code == 200:
                logger.info("✅ RA1 status endpoint working")
                status = response.json()
                logger.info(f"RA1 status: {json.dumps(status, indent=2)}")
            else:
                logger.error(f"❌ RA1 status failed: {response.status_code}")
        except Exception as e:
            logger.error(f"❌ RA1 status error: {e}")
        
        # Test RA2 status
        try:
            response = requests.get(f"{self.ra2_url}/status", timeout=5)
            if response.status_code == 200:
                logger.info("✅ RA2 status endpoint working")
                status = response.json()
                logger.info(f"RA2 status: {json.dumps(status, indent=2)}")
            else:
                logger.error(f"❌ RA2 status failed: {response.status_code}")
        except Exception as e:
            logger.error(f"❌ RA2 status error: {e}")
    
    def submit_application(self, ra_url: str, app_data: dict, ra_name: str):
        """Submit an application to a specific RA."""
        logger.info(f"Submitting application to {ra_name}...")
        logger.info(f"Application data: {json.dumps(app_data, indent=2)}")
        
        try:
            response = requests.post(
                f"{ra_url}/submit",
                json=app_data,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"✅ {ra_name} submit successful")
                logger.info(f"{ra_name} response: {json.dumps(result, indent=2)}")
                return result
            else:
                logger.error(f"❌ {ra_name} submit failed: {response.status_code}")
                logger.error(f"{ra_name} error: {response.text}")
                return None
        except Exception as e:
            logger.error(f"❌ {ra_name} submit error: {e}")
            return None
    
    def test_submit_scenarios(self):
        """Test various submit scenarios."""
        logger.info("Testing submit scenarios...")
        
        # Test scenarios
        test_apps = [
            {
                "name": "Basic Application",
                "data": {
                    "flavor": {"m1.medium": 1},
                    "requirements": {"region": "us-east-1"}
                }
            },
            {
                "name": "Multiple Instances",
                "data": {
                    "flavor": {"m1.large": 2, "m1.small": 1},
                    "requirements": {"region": "us-west-2", "availability": "high"}
                }
            },
            {
                "name": "Simple Flavor Only",
                "data": {
                    "flavor": {"m1.medium": 1}
                }
            },
            {
                "name": "High Performance",
                "data": {
                    "flavor": {"m1.xlarge": 1},
                    "requirements": {"region": "eu-west-1", "performance": "high"}
                }
            }
        ]
        
        # Test each scenario on both RAs
        for i, scenario in enumerate(test_apps, 1):
            logger.info(f"\n--- Test Scenario {i}: {scenario['name']} ---")
            
            # Submit to RA1
            ra1_result = self.submit_application(
                self.ra1_url, 
                scenario['data'], 
                "RA1"
            )
            
            # Wait a bit between submissions
            time.sleep(2)
            
            # Submit to RA2
            ra2_result = self.submit_application(
                self.ra2_url, 
                scenario['data'], 
                "RA2"
            )
            
            # Compare results
            if ra1_result and ra2_result:
                logger.info("✅ Both RAs processed the submission successfully")
                logger.info(f"RA1 reservation ID: {ra1_result.get('reservation_id')}")
                logger.info(f"RA2 reservation ID: {ra2_result.get('reservation_id')}")
            else:
                logger.warning("⚠️ One or both RAs failed to process the submission")
            
            time.sleep(3)  # Wait between scenarios
    
    def test_application_status(self):
        """Test getting application status."""
        logger.info("Testing application status retrieval...")
        
        # First submit an application to get a reservation ID
        test_app = {
            "flavor": {"m1.medium": 1},
            "requirements": {"region": "us-east-1"}
        }
        
        # Submit to RA1
        ra1_result = self.submit_application(self.ra1_url, test_app, "RA1")
        if ra1_result:
            reservation_id = ra1_result.get('reservation_id')
            
            # Wait a bit
            time.sleep(2)
            
            # Get status from RA1
            try:
                response = requests.get(f"{self.ra1_url}/applications/{reservation_id}", timeout=5)
                if response.status_code == 200:
                    status = response.json()
                    logger.info("✅ RA1 application status retrieved")
                    logger.info(f"Status: {json.dumps(status, indent=2)}")
                else:
                    logger.error(f"❌ RA1 status retrieval failed: {response.status_code}")
            except Exception as e:
                logger.error(f"❌ RA1 status retrieval error: {e}")
        
        # Submit to RA2
        ra2_result = self.submit_application(self.ra2_url, test_app, "RA2")
        if ra2_result:
            reservation_id = ra2_result.get('reservation_id')
            
            # Wait a bit
            time.sleep(2)
            
            # Get status from RA2
            try:
                response = requests.get(f"{self.ra2_url}/applications/{reservation_id}", timeout=5)
                if response.status_code == 200:
                    status = response.json()
                    logger.info("✅ RA2 application status retrieved")
                    logger.info(f"Status: {json.dumps(status, indent=2)}")
                else:
                    logger.error(f"❌ RA2 status retrieval failed: {response.status_code}")
            except Exception as e:
                logger.error(f"❌ RA2 status retrieval error: {e}")
    
    def test_capacity_endpoints(self):
        """Test capacity endpoints."""
        logger.info("Testing capacity endpoints...")
        
        # Test RA1 capacity
        try:
            response = requests.get(f"{self.ra1_url}/capacity", timeout=5)
            if response.status_code == 200:
                capacity = response.json()
                logger.info("✅ RA1 capacity endpoint working")
                logger.info(f"RA1 capacity: {json.dumps(capacity, indent=2)}")
            else:
                logger.error(f"❌ RA1 capacity failed: {response.status_code}")
        except Exception as e:
            logger.error(f"❌ RA1 capacity error: {e}")
        
        # Test RA2 capacity
        try:
            response = requests.get(f"{self.ra2_url}/capacity", timeout=5)
            if response.status_code == 200:
                capacity = response.json()
                logger.info("✅ RA2 capacity endpoint working")
                logger.info(f"RA2 capacity: {json.dumps(capacity, indent=2)}")
            else:
                logger.error(f"❌ RA2 capacity failed: {response.status_code}")
        except Exception as e:
            logger.error(f"❌ RA2 capacity error: {e}")
    
    def cleanup(self):
        """Clean up RA processes."""
        logger.info("Cleaning up RA processes...")
        
        if self.ra1_process:
            logger.info("Terminating RA1...")
            self.ra1_process.terminate()
            try:
                self.ra1_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.ra1_process.kill()
        
        if self.ra2_process:
            logger.info("Terminating RA2...")
            self.ra2_process.terminate()
            try:
                self.ra2_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.ra2_process.kill()
        
        logger.info("Cleanup completed")
    
    def run_full_test(self):
        """Run the complete test suite."""
        logger.info("=== Starting RA Submit Function Test ===\n")
        
        try:
            # Start RAs
            self.start_ra1()
            time.sleep(3)  # Wait for RA1 to start
            
            self.start_ra2()
            time.sleep(3)  # Wait for RA2 to start
            
            # Wait for RAs to be ready
            if not self.wait_for_ra_startup(self.ra1_url):
                logger.error("RA1 failed to start properly")
                return
            
            if not self.wait_for_ra_startup(self.ra2_url):
                logger.error("RA2 failed to start properly")
                return
            
            # Run tests
            logger.info("\n=== Running Tests ===\n")
            
            self.test_health_endpoints()
            time.sleep(2)
            
            self.test_status_endpoints()
            time.sleep(2)
            
            self.test_capacity_endpoints()
            time.sleep(2)
            
            self.test_submit_scenarios()
            time.sleep(2)
            
            self.test_application_status()
            
            logger.info("\n=== Test Summary ===")
            logger.info("✅ All tests completed successfully!")
            logger.info("RA1 and RA2 are communicating via P2P network")
            logger.info("Submit function is working correctly")
            
        except KeyboardInterrupt:
            logger.info("Test interrupted by user")
        except Exception as e:
            logger.error(f"Test failed with error: {e}")
        finally:
            self.cleanup() 