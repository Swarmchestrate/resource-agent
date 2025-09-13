# Swarmchestrate - Resource Agent
The Resource Agent (RA) is a core component of Swarmchestrate with two main roles: (1) abstracting and representing one or more Capacities to provide access to their resources, and (2) collaborating with other RAs to discover and allocate suitable resources across the full resource stack for submitted applications. This collaboration is enabled through the P2P network, which is automatically formed when RAs are instantiated.

## Quick Start

### Prerequisites
- Python 3.12+
- Virtual environment

### Installation

1. Create and activate a virtual environment:
```bash
python -m venv ra_env
source ra_env/bin/activate  # On Windows: ra_env\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage
Run the following command to instantiate an RA

```bash
python src/ra.py [arg1] [arg2]
```
### Arguments
- `arg1` (Optional): Path to the RA configuration file. 
- `arg2` (Optional): Path to the Capacity configuration file.

  The templates of these config files are available in the config/ directory.

### Resource selection jobs
Run the Job submission client script to submit a request to select resources for a given application:

```bash
python job_submission_client.py [arg1] [arg2] [arg3] 
```
### Arguments
- `arg1` (Mandatory): Path to the YAML-based resource requirements file. An example template can be found in tosca/output/ask.yaml.
- `arg2` (Mandatory): IP address of the RA to which the request is submitted.
- `arg3` (Mandatory): Port number of the RA to which the request is submitted.

