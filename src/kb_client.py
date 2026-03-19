import base64
import json
import os
import requests
import yaml
from datetime import datetime
from typing import Dict, Any

class KBClient:
    """A client for interacting with the Knowledge Base (KB) service.

    This static class provides methods to upload and download various types of data,
    including TOSCA templates, configuration files, and state files, to and from the KB.
    It handles serialization, base64 encoding, and HTTP requests to the KB API.

    Supported data types:
    - SAT (Swarmchestrate Application Template)
    - CB_STATE (ClusterBuilder State file)
    - CAPLIB_STATE (Capacity Lib State file)
    - CDT_STATE (Capacity Description Template)

    All methods return a dictionary with 'success' status and additional information.
    """

    @staticmethod
    def _KB_base_config():
        return {
            "base": os.environ.get("KB_BASE_URL", "http://optimusdb.swarmchestrate.sztaki.hu").rstrip("/"),
            "timeout": int(os.environ.get("KB_TIMEOUT", 10)),
            "context": os.environ.get("KB_CONTEXT", "swarmkb").strip("/")
        }

    @staticmethod
    def _upload_to_KB(id: str, data: Dict[str, Any], prefix: str, format="yaml") -> Dict[str, Any]:
        cfg = KBClient._KB_base_config()
        upload_url = f"{cfg['base']}/optimusdb1/{cfg['context']}/upload"
        command_url = f"{cfg['base']}/optimusdb1/{cfg['context']}/command"
        filename = f"{prefix}-{id}"

        try:
            if format == "yaml":
                serialized = yaml.safe_dump(data, sort_keys=False)
                b64 = base64.b64encode(serialized.encode("utf-8")).decode("utf-8")

                payload = {
                    "file": b64,
                    "filename": filename,
                    "store_full_structure": True,
                    "target_store": "dsswres"
                }

                response = requests.post(
                    upload_url,
                    json=payload,
                    timeout=cfg["timeout"],
                    headers={"Content-Type": "application/json"},
                )

            elif format == "json":
                return {
                    "success": False,
                    "error": "JSON not supported yet",
                }

            response.raise_for_status()

            try:
                body = response.json()
            # response JSON error handling
            except ValueError:
                return {
                    "success": False,
                    "error": "Invalid JSON response from KB",
                    "status_code": response.status_code,
                    "raw_response": response.text,
                }

            return {
                "success": True,
                "status_code": response.status_code,
                "response": body,
                "filename": filename,
            }

        # Handle the basic network related failures, HTTP errors, remote service problems
        # Timeout, ConnectionError, HTTPError, TooManyRedirects
        except requests.exceptions.RequestException as e:
            return {
                "success": False,
                "error": str(e),
                "type": type(e).__name__,
            }
        # JSON/YAML parsing failures, Missing keys, Type errors
        except Exception as e:
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "type": type(e).__name__,
            }

    @staticmethod
    def _download_from_KB(id: str, prefix: str) -> Dict[str, Any]:
        cfg = KBClient._KB_base_config()
        download_url = f"{cfg['base']}/optimusdb1/{cfg['context']}/command"
        filename = f"{prefix}-{id}"

        payload = {
            "method": {"cmd": "crudget", "argcnt": 1},
            "dstype": "dsswres",
            "criteria": [{"_filename": filename}],
        }

        try:
            response = requests.post(
                download_url,
                json=payload,
                timeout=cfg["timeout"],
            )
            response.raise_for_status()

            try:
                result = response.json()
            except ValueError:
                return {
                    "success": False,
                    "error": "Invalid JSON response from KB",
                    "status_code": response.status_code,
                    "raw_response": response.text,
                }

            data = result.get("data")
            if not isinstance(data, list) or not data:
                return {
                    "success": False,
                    "error": f"No file ({filename}) returned from KB",
                    "status_code": response.status_code,
                }

            doc = data[0]
            raw_yaml = doc.get("_original_yaml")
            if not raw_yaml:
                return {
                    "success": False,
                    "error": "_original_yaml not found in KB response",
                    "status_code": response.status_code,
                }

            try:
                parsed_yaml = yaml.safe_load(raw_yaml)
            except yaml.YAMLError as e:
                return {
                    "success": False,
                    "error": f"Invalid YAML content: {str(e)}",
                }

            return {
                "success": True,
                "status_code": response.status_code,
                "data": parsed_yaml,
                "filename": filename,
            }

        except requests.exceptions.RequestException as e:
            return {
                "success": False,
                "error": str(e),
                "type": type(e).__name__,
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "type": type(e).__name__,
            }

    '''
    datetime.now().strftime('%Y%m%d_%H%M%S.%f')[:-3]
    <DATE> -> 20240318_153045.123

    SWARMID = <RAID>_<DATE>

    1) Swarmchestrate Application Template (SAT): SAT_<SWARMID>
        Exptected format=yaml
    2) ClusterBuilder (CB) -> OpenTofu state file: CB_STATE_<SWARMID>
        Exptected format=json
    3) Capacity Lib State file: -> CAPLIB_STATE_<RAID>
        Exptected format=yaml
    4) Capacity Description Template (CDT): CDT_<RAID>
        Exptected format=yaml
    '''

    @staticmethod
    def upload_SAT_to_KB(swarm_id: str, SAT: Dict[str, Any]) -> Dict[str, Any]:
        return KBClient._upload_to_KB(swarm_id, SAT, prefix="SAT")

    @staticmethod
    def download_SAT_from_KB(swarm_id: str) -> Dict[str, Any]:
        return KBClient._download_from_KB(swarm_id, prefix="SAT")

    @staticmethod
    def upload_CB_STATE_to_KB(swarm_id: str, CB: Dict[str, Any]) -> Dict[str, Any]:
        # return KBClient._upload_to_KB(swarm_id, CB, prefix="CB_STATE", format="json")
        pass

    @staticmethod
    def download_CB_STATE_from_KB(swarm_id: str) -> Dict[str, Any]:
        # return KBClient._download_from_KB(swarm_id, prefix="CB_STATE")
        pass

    @staticmethod
    def upload_CAPLIB_STATE_to_KB(ra_id: str, CAPLIB_STATE: Dict[str, Any]) -> Dict[str, Any]:
        return KBClient._upload_to_KB(ra_id, CAPLIB_STATE, prefix="CAPLIB_STATE")

    @staticmethod
    def download_CAPLIB_STATE_from_KB(ra_id: str) -> Dict[str, Any]:
        return KBClient._download_from_KB(ra_id, prefix="CAPLIB_STATE")

    @staticmethod
    def upload_CDT_to_KB(ra_id: str, CDT_STATE: Dict[str, Any]) -> Dict[str, Any]:
        return KBClient._upload_to_KB(ra_id, CDT_STATE, prefix="CDT")

    @staticmethod
    def download_CDT_from_KB(ra_id: str) -> Dict[str, Any]:
        return KBClient._download_from_KB(ra_id, prefix="CDT")

