# Swarmchestrate Resource Agent

A peer-to-peer (P2P) network of Resource Agents (RAs) representing different cloud VMs that can evaluate TOSCA resource requirements and provide resource bids.


## Quick Start

### Prerequisites
- Python 3.12+
- Virtual environment

### Installation

1. Create and activate virtual environment:
```bash
python -m venv ra_env
source ra_env/bin/activate  # On Windows: ra_env\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

### Running Resource Agents

1. **AWS UK RA (Hub)**:
```bash
python src/aws_uk_ra.py
```

2. **AWS US RA**:
```bash
python src/aws_us_ra.py
```

3. **SZTAKI RA**:
```bash
python src/sztaki_ra.py
```

### Submitting Jobs

Run the job submission client:
```bash
python src/job_submission_client.py
```

## Configuration

Resource Agent configurations are stored in `Config_ras/`:
- `Aws_UK_RA_config.yaml` / `Aws_UK_RA_capacity.yaml`
- `Aws_US_RA_config.yaml` / `Aws_USA_RA_capacity.yaml`
- `Sztaki_RA_config.yaml` / `SZTAKI_RA_capacity.yaml`

## TOSCA Requirements

Example `ask.yaml` files are in `tosca/outputs/` showing resource requirements that RAs can evaluate.

## Network Topology

- **AWS UK RA**: Acts as the bootstrap hub (port ---)
- **AWS US RA**: Connects to UK hub (port ---)
- **SZTAKI RA**: Connects to UK hub (port ---)

The system automatically handles message chunking for large TOSCA files and compiles valid resource combinations from RA responses.
