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

## Quick Start

### Prerequisites
- Python 3.12+
- Virtual environment
- puccini (For tosca library)
- opentofu (For cluster-builder library)
  

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


## Usage

### RA
Run the following command to instantiate an RA

```bash
python src/ra.py [arg1] [arg2]
```
### Arguments
- `arg1` (Optional): Path to the RA configuration file. 
- `arg2` (Optional): Path to the Capacity configuration file.

The templates of these config files are available in the config/ directory, arg1 template is ra-config.yaml and arg2 template is capacity-config.yaml.

### Client
Run the Job submission client script to submit a request to the main ra:

```bash
python job_submission_client.py [arg1] 
```
### Arguments
- `arg1` (Mandatory): Path to the YAML-based submission file. One could submit/query/delete an application. An example template can be found in client/template.yaml.

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

## Contact
For any questions or feedback, feel free to reach out:

- Amjad Ullah, Email: a.ullah@napier.ac.uk
- Ze Wang, Email: z.wang3@napier.ac.uk
- Sajid Alam, Email: s.alam2@napier.ac.uk
