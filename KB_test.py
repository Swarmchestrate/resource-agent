from datetime import datetime
from src.kb_client import KBClient

if __name__ == "__main__":
    """
    datetime.now().strftime('%Y%m%d_%H%M%S.%f')[:-3]
    <DATE> -> 20240318_153045.123

    SWARM_ID = <RA_ID>_<DATE>

    1) Swarmchestrate Application Template (SAT): SAT_<SWARM_ID>
        Exptected format=yaml
    2) ClusterBuilder (CB) -> OpenTofu state file: CB_STATE_<SWARM_ID> (NOT IMPLEMENTED YET)
        Exptected format=json; 
    3) Capacity Lib State file: -> CAPLIB_STATE_<RA_ID>
        Exptected format=yaml
    4) Capacity Description Template (CDT): CDT_<RA_ID>
        Exptected format=yaml
    """
    RA_ID = "test-ra"
    DATE = datetime.now().strftime("%Y%m%d_%H%M%S.%f")[:-3]
    SWARM_ID = f"{RA_ID}_{DATE}"

    SAT = {
        "tosca_definitions_version": "tosca_simple_yaml_1_3",
        "topology_template": {
            "node_templates": {
                "example_node": {
                    "type": "tosca.nodes.Compute",
                    "properties": {"num_cpus": 4, "mem_size": "16GB"},
                }
            }
        },
    }

    CAPLIB = {
        "_id": "capacity-001",
        "name": "compute-node-capacity",
        "description": "Capacity profile for edge compute node in cluster A",
        "node_id": "node-A-01",
        "cluster": "cluster-A",
        "cpu_cores": 16,
        "cpu_architecture": "x86_64",
        "memory_gb": 64,
        "storage_gb": 1024,
        "storage_type": "ssd",
        "gpu_available": False,
        "network_bandwidth_mbps": 1000,
        "status": "active",
        "utilization": {"cpu_percent": 35, "memory_percent": 60, "storage_percent": 50},
        "tags": ["edge", "compute", "production"],
        "created_at": "2026-03-19T12:00:00Z",
    }

    CDT = {
        "tosca_definitions_version": "tosca_2_0",
        "description": "SZTAKI OpenStack Capacity Def",
        "metadata": {
            "name": "cap-os-sztaki",
            "author": "University of Westminster",
            "date": "2026-03-04",
            "version": "0.1",
            "tags": [{"provider": "sztaki"}],
        },
        "imports": [
            {
                "namespace": "swch",
                "url": "https://raw.githubusercontent.com/Swarmchestrate/tosca/refs/heads/main/profiles/eu.swarmchestrate/profile.yaml",
            }
        ],
        "node_types": {
            "OpenStackBase": {
                "derived_from": "swch:Capacity",
                "description": "An base compute node from the SZTAKI provision",
                "properties": {
                    "image_id": {
                        "type": "string",
                        "required": True,
                        "default": "4271ec99-6cda-458f-8fe5-38205ea2d3b3",
                    },
                    "project_id": {"type": "string", "required": False},
                    "network_id": {
                        "type": "string",
                        "required": True,
                        "default": "bbe042e4-91a1-4601-962f-14a31e5e2787",
                    },
                    "flavor_name": {"type": "string", "required": True},
                    "key_name": {"type": "string", "required": False, "default": "g"},
                    "security_groups": {
                        "type": "list",
                        "required": False,
                        "entry_schema": "string",
                    },
                    "volume_size": {"type": "integer", "required": True, "default": 10},
                    "use_block_device": {
                        "type": "boolean",
                        "required": True,
                        "default": True,
                    },
                },
                "capabilities": {
                    "host": {
                        "properties": {
                            "disk-size": {"default": 10},
                            "bandwidth": {"default": 1000},
                        }
                    },
                    "os": {
                        "properties": {
                            "type": {"default": "linux"},
                            "version": {"default": "24.04"},
                            "distribution": {"default": "ubuntu"},
                        }
                    },
                    "resource": {
                        "properties": {
                            "provider": {"default": "SZTAKI"},
                            "capacity-provider": {"default": "SZTAKI"},
                            "type": {"default": "cloud"},
                        }
                    },
                    "network": {
                        "properties": {
                            "ipv4_enabled": {"default": True},
                            "ipv6_enabled": {"default": False},
                            "type": {"default": "ethernet"},
                        }
                    },
                    "pricing": {"properties": {"cost": {"default": 0.00}}},
                    "locality": {
                        "properties": {
                            "continent": {"default": "Europe"},
                            "country": {"default": "Hungary"},
                            "city": {"default": "Budapest"},
                        }
                    },
                    "energy": {
                        "properties": {
                            "powered-type": {"default": "mains-powered"},
                            "energy-type": {"default": "non-green"},
                        }
                    },
                },
            }
        },
        "service_template": {
            "node_templates": {
                "sztaki-capacity": {
                    "type": "swch:OverallCapacity",
                    "capabilities": {
                        "capacity": {"properties": {"num-cpus": 40, "mem-size": 1000}}
                    },
                },
                "m2-medium": {
                    "type": "OpenStackBase",
                    "properties": {"flavor_name": "m2.medium", "key_name": "fuelics"},
                    "capabilities": {
                        "capacity": {"properties": {"instances": 4}},
                        "host": {"properties": {"num-cpus": 4, "mem-size": 8}},
                        "energy": {"properties": {"consumption": 0.10}},
                    },
                },
                "m2-small": {
                    "type": "OpenStackBase",
                    "properties": {"flavor_name": "m2.small", "key_name": "fuelics"},
                    "capabilities": {
                        "host": {"properties": {"num-cpus": 2, "mem-size": 4}},
                        "energy": {"properties": {"consumption": 0.10}},
                    },
                },
                "specific-small-sztaki": {
                    "type": "OpenStackBase",
                    "properties": {"flavor_name": "m2.small", "key_name": "fuelics"},
                    "capabilities": {
                        "capacity": {"properties": {"instances": 1}},
                        "host": {"properties": {"num-cpus": 2, "mem-size": 4}},
                        "resource": {
                            "properties": {
                                "labels": {"key_name": "my_specific_resource"}
                            }
                        },
                        "energy": {"properties": {"consumption": 0.10}},
                    },
                },
            }
        },
    }

    """
    1) Swarmchestrate Application Template (SAT): SAT_<SWARMID>
    2) ClusterBuilder (CB) -> OpenTofu state file: CB_STATE_<SWARMID> (NOT IMPLEMENTED YET)
    3) Capacity Lib State file: -> CAPLIB_STATE_<RAID>
    4) Capacity Description Template (CDT): CDT_<RAID>
    """

    print(f"RA_ID: {RA_ID}")
    print(f"DATE: {DATE}")
    print(f"SWARM_ID: {SWARM_ID}")

    ########
    # SAT
    ########
    upload = KBClient.upload_SAT_to_KB(SWARM_ID, SAT)
    if upload["success"]:
        # Should be a info log
        print(f"{upload['filename']} uploaded successfuly to KB")
    else:
        # Should be an error log
        print(f"Upload to KB failed: {upload['error']}")

    download = KBClient.download_SAT_from_KB(SWARM_ID)
    if download["success"]:
        # Should be an info log
        print(f"{download['filename']} downloaded successfuly from KB")
        print(download["data"])
    else:
        # Should be an error log
        print(f"Download from KB failed: {download['error']}")

    ########
    # CAPLIB
    ########
    upload = KBClient.upload_CAPLIB_STATE_to_KB(RA_ID, CAPLIB)
    if upload["success"]:
        # Should be a info log
        print(f"{upload['filename']} uploaded successfuly to KB")
    else:
        # Should be an error log
        print(f"Upload to KB failed: {upload['error']}")

    download = KBClient.download_CAPLIB_STATE_from_KB(RA_ID)
    if download["success"]:
        # Should be an info log
        print(f"{download['filename']} downloaded successfuly from KB")
        print(download["data"])
    else:
        # Should be an error log
        print(f"Download from KB failed: {download['error']}")
    ########
    # CDT
    ########
    upload = KBClient.upload_CDT_to_KB(RA_ID, CDT)
    if upload["success"]:
        # Should be a info log
        print(f"{upload['filename']} uploaded successfuly to KB")
    else:
        # Should be an error log
        print(f"Upload to KB failed: {upload['error']}")

    download = KBClient.download_CDT_from_KB(RA_ID)
    if download["success"]:
        # Should be an info log
        print(f"{download['filename']} downloaded successfuly from KB")
        print(download["data"])
    else:
        # Should be an error log
        print(f"Download from KB failed: {download['error']}")
