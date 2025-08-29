#  Resource Agent

A P2P-based resource agent for distributed computing that broadcasts resource requirements and matches them with available capacity.

## Features

- **Direct ask.yaml Broadcasting**: Broadcast resource requirements without TOSCA validation
- **P2P Network Communication**: Peer-to-peer resource discovery and communication
- **Resource Matching**: Binary resource matching system for VM requirements
- **FastAPI Interface**: RESTful API for resource management
- **Real-time Resource Discovery**: Automatic peer discovery and connection management

## Quick Start

1. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Start the Resource Agent:**
   ```bash
   python src/main.py --config config/config.yaml
   ```

3. **Test Broadcasting:**
   ```bash
   python test_broadcast_file.py
   ```

4. **Test Endpoints:**
   ```bash
   python test_endpoints.py
   ```

## Architecture

### **Core Components:**
- **`src/main.py`**: Application entry point and FastAPI server startup
- **`src/ra_core.py`**: Core Resource Agent logic with P2P and message handling
- **`src/config.py`**: Configuration loading and management
- **`src/capacity_loader.py`**: Loads capacity profiles from YAML files

### **API Layer:**
- **`src/api/endpoints.py`**: FastAPI endpoints including `/broadcast-ask` and `/submit`
- **`src/api/__init__.py`**: API package initialization

### **Utility Modules:**
- **`src/utils/resource_offer_system.py`**: Manages resource requests and broadcasting
- **`src/utils/binary_resource_matcher.py`**: Matches VM requirements with RA capacity
- **`src/utils/helpers.py`**: General utility functions


### **Configuration:**
- **`config/config.yaml`**: Main RA configuration
- **`config/capacity_profiles.yaml`**: RA capacity definitions

### **TOSCA Files:**
- **`tosca/outputs/ask.yaml`**: Resource requirements definition 

## API Endpoints

### **Core Endpoints:**
- `GET /`: Root endpoint with basic info
- `GET /status`: Get RA status and configuration
- `GET /health`: Health check endpoint
- `GET /p2p/status`: Get P2P network status and connected peers

### **Resource Management:**
- `POST /broadcast-ask`: **Directly broadcast ask.yaml requirements** 

### **Application Management:**
- `GET /applications/{reservation_id}`: Get application status
- `PUT /applications/{reservation_id}`: Update application
- `DELETE /applications/{reservation_id}`: Delete application

## Resource Broadcasting Workflow

1. **User runs:** `python test_broadcast_file.py`
2. **Script calls:** `POST /broadcast-ask` endpoint
3. **RA loads:** `tosca/outputs/ask.yaml` directly
4. **Requirements extracted:** VM specifications, counts, metadata
5. **P2P broadcast:** Message sent to all connected peers (e.g., Aws-RA2)
6. **Remote RAs process:** Resource matching and offer generation
7. **Results returned:** Resource availability and offers


## Testing

### **Test Scripts:**
- **`test_broadcast_file.py`**: Tests direct ask.yaml broadcasting
- **`test_endpoints.py`**: Tests all available API endpoints

### **Expected Output:**
```
 Testing Direct ask.yaml Broadcasting (No TOSCA Validation)
================================================================================
 RA Status: 200
 Response: {'ra_id': 'ra-local', 'status': 'running', 'p2p_available': True}
 ask.yaml requirements broadcasted successfully!
 RA ID: ra-local
 Broadcast Status: broadcasted_to_p2p_network
 Broadcast Message: ask.yaml requirements broadcasted to all peers
 Received resource request from ra-local
 Processing 2 VM requirements
 Evaluating vm1 (count: 3)
 CAN or CAN'T fulfill the resource request
```


