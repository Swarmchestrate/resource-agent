# Swarmchestrate - Resource Agent
The Resource Agent (RA) is a core component of Swarmchestrate with two main roles: (1) abstracting and representing one or more Capacities to provide access to their resources, and (2) collaborating with other RAs to discover and allocate suitable resources across the full resource stack for submitted applications. This collaboration is enabled through the P2P network, which is automatically formed when RAs are instantiated.

## Feature Status 
This section outlines the key functions implemented in RA and the existing limitations.

### Features:

#### Handling application submit request:

Step 1: Validate and Process Application

- Validate the application’s TOSCA file.
- Extract resource requirements and QoS requirements for offer generation and ranking.

---

Step 2: Perform Distributed Resource Discovery

- Broadcast resource requirements to all participating RAs.
- Each RA evaluates local resource availability and sends the results back to the main RA.
- Capacity status update accordingly.

---

Step 3: Rank and Select Deployment Offer

- The main RA compiles all feasible offers (an offer is a set of computing resources that fulfils the application’s resource requirements) based on the resource availability reported by each RA.
- The main RA selects the best offer using an AI-based ranking algorithm.

---

Step 4: Provision Swarm Cluster

- The main RA launches a Lead Resource (selected at random) and deploys the k3s master node on it using the Cluster Builder library.
- The main RA prepares the Swarm Agent configuration files, copies the deployment manifests of all system components to the master node, and applies them.
- The main RA launches the remaining resources and deploys k3s worker nodes to join the master node using the Cluster Builder library.


#### Handling application query request:
- Return the current status of the given application ID.

#### Handling application delete request:
- Destory the swarm of the given application ID.

### Limitations:

#### Handling application submit request:

Step 1: Validates and processes application
- Submits the Application Deployment Template (ADT) to the Knowledge Base (KB).
- Extracts Monitoring metrics resource requirements, QoS requirements for offer generation and ranking.
  
---

Step 3: Rank and Select Deployment Offer
- Integrate private ranking.

---

Step 4: Provision Swarm Cluster
- Deploy monitoring system and AI reconfiguration agent.

#### Handling capacity query request:
- Return the capacity status of the given RA ID.

## Quick Start

### Prerequisites
- Python 3.12+
- Virtual environment
- puccini (For tosca library)
- opentofu (For cluster-builder library)
  

### Prerequisites Installation

1. Create and activate a virtual environment:
```bash
python -m venv ra_env
source ra_env/bin/activate  # On Windows: ra_env\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Install puccini on Linux:

```sh
wget https://github.com/Swarmchestrate/tosca/releases/download/v0.2.4/go-puccini_0.22.7-SNAPSHOT-3e85b40_linux_amd64.deb
sudo dpkg -i go-puccini_0.22.7-SNAPSHOT-3e85b40_linux_amd64.deb || sudo apt --fix-broken install -y
```

4. Install opentofu on Linux by following steps on https://opentofu.org/docs/intro/install/deb/ 

Download the installer script:
```sh
curl --proto '=https' --tlsv1.2 -fsSL https://get.opentofu.org/install-opentofu.sh -o install-opentofu.sh
```

Give it execution permissions:
```sh   
chmod +x install-opentofu.sh
```

Run the installer:
```sh   
./install-opentofu.sh --install-method deb
```

Verify installation:
```sh
tofu --version
```

Remove the installer:
```sh 
rm -f install-opentofu.sh
```

### RA Installation
```sh
git clone git@github.com:Swarmchestrate/resource-agent.git
```

## Usage

### RA
Run the following command to instantiate an RA

```bash
python src/ra.py [arg1] [arg2]
```
#### Arguments
- `arg1` (Optional): Path to the RA configuration file. 
- `arg2` (Optional): Path to the Capacity configuration file.

The templates of these config files are available in the config/ directory, arg1 template is ra-config.yaml and arg2 template is capacity-config.yaml.

### Client
Run the Job submission client script to submit a request to the main ra:

```bash
python src/job_submission_client.py [arg1] 
```
#### Arguments
- `arg1` (Mandatory): Path to the YAML-based submission file. One could submit/query/delete an application. An example template can be found in client/template.yaml.

## Development Environment Setup

This section outlines all the necessary steps to build a complete universe from the ground up.

### Prerequisites
- Resource Agent
- PostgreSQL

### Prerequisites Installation

1. Install Resource Agent based on above installation guide
   
2. Install PostgreSQL


Option 1: Service-Based Installation

Follow the official PostgreSQL installation guide based on your OS:
https://www.postgresql.org/download/

For an example setup using steps relevant to this project, see:
https://github.com/Swarmchestrate/cluster-builder/blob/main/docs/database_setup.md

Option 2: Docker-Based Installation

Requirements:
 - Docker (if you plan to use a Docker-based installation)

Run the following commands to set up PostgreSQL in Docker:
```bash
docker rm pg-db || echo "No container to remove"
docker run --name pg-db -e POSTGRES_USER=admin -e POSTGRES_PASSWORD=adminpass -e POSTGRES_DB=swarmchestrate -p 5432:5432 -d postgres
```

## Universe Setup

A Swarmchestrate universe consists of:

- One **main Resource Agent**
- One or more **additional Resource Agents**
- A **PostgreSQL server**

After successfully installing the Resource Agents and the PostgreSQL server, you must configure the Resource Agent configuration files and the environment variables required by the `cluster-builder` library.

---

### Step 1: Configure and Activate Environment Variables

Edit the environment configuration file:

```bash
vim /cluster-builder-env/env
```

Update the following sections to match your setup:

- `## PG Configuration` — PostgreSQL connection details  
- `## AWS Auth` — AWS credentials  
- `## OpenStack Auth` — OpenStack credentials  

Then activate the environment variables:

```bash
cp /cluster-builder-env/env .env
set -a
. .env
set +a
```

---

### Step 2: Configure and Launch the Main Resource Agent

Edit the main Resource Agent configuration:

```bash
vim config/ra-config.yaml
```

- Update all keys according to the provided comments.
- Leave `bootstrap_peers: []` unchanged for the main Resource Agent.

Edit the capacity configuration:

```bash
vim config/capacity-config.yaml
```

- Update the capacity values as needed.

Launch the main Resource Agent:

```bash
python src/ra.py [arg1] [arg2]
```

---

### Step 3: Configure and Launch Additional Resource Agents

For each additional Resource Agent:

Edit the configuration file:

```bash
vim config/ra-config.yaml
```

- Update all keys according to the comments.
- Set `bootstrap_peers` to the main Resource Agent address:

```yaml
bootstrap_peers: ["<hub_ra_ip>:<port>"]
```

Edit the capacity configuration:

```bash
vim config/capacity-config.yaml
```

- Update the capacity values as needed.

Launch the Resource Agent:

```bash
python src/ra.py [arg1] [arg2]
```

The agent will automatically join the main Resource Agent.

---

### Step 4: Configure and Launch the Client

Edit the client submission template:

```bash
vim /client/template.yaml
```

- Update all keys according to the provided comments.

Launch the client and submit a request to the main Resource Agent:

```bash
python src/job_submission_client.py [arg1]
```


<!--
### Cluster-builder
The cluster-builder library requires environment varibles that store cloud credentials and container registry credentials. 
A template can be found in cluster-builder-env/env
Note that, in the real deployment, the env file should be stored in the e2e-demo folder as e2e-demo/.env. 
To load it, one should run the following commands in the e2e-demo folder:

```bash
set -a
. .env
set +a 
```
-->

## Docker

The image is published to `ghcr.io/swarmchestrate/resource-agent`. Tagged releases produce `latest` and semver tags; pushes to `main` produce the `dev` tag.

```bash
docker pull ghcr.io/swarmchestrate/resource-agent:latest
```

Config files must be mounted at runtime. Mount your configured `config/` directory into the container:

```bash
docker run -v ./config:/app/config ghcr.io/swarmchestrate/resource-agent:latest
```

To pass custom config file paths:

```bash
docker run -v ./config:/app/config ghcr.io/swarmchestrate/resource-agent:latest /app/config/ra-config.yaml /app/config/capacity-config.yaml
```

If the RA requires SSH access to provision VMs, mount the SSH key and ensure `ssh_key_path` in `ra-config.yaml` points to the mounted path (e.g., `/app/keys/my-key.pem`):

```bash
docker run -v ./config:/app/config -v ~/.ssh/my-key.pem:/app/keys/my-key.pem:ro ghcr.io/swarmchestrate/resource-agent:latest
```

Environment variables required by `cluster-builder` (cloud credentials, PostgreSQL config) should be passed via `--env-file`:

```bash
docker run -v ./config:/app/config --env-file .env ghcr.io/swarmchestrate/resource-agent:latest
```

## Contact
For any questions or feedback, feel free to reach out:

- Amjad Ullah, Email: a.ullah@napier.ac.uk
- Ze Wang, Email: z.wang3@napier.ac.uk
- Sajid Alam, Email: s.alam2@napier.ac.uk
