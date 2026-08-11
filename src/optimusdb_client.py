#!/usr/bin/env python3
"""
OptimusDB Python Client
A comprehensive client for interacting with OptimusDB distributed catalog system.

Features:
- Full CRUD operations (Create, Read, Update, Delete)
- TOSCA file upload support (with target_store selection)
- Query with filters, regex, operators
- Extended Metadata (48-field) operations: query, edit, SQL
- Logging and debugging
- CLI interface
"""

import requests
import json
import logging
import argparse
import os
import sys
import base64
from typing import Dict, List, Any, Optional
from pathlib import Path
import yaml
from datetime import datetime
import time



## Update Feb 28.02.26






class OptimusDBClient:
    """Main client class for OptimusDB operations."""

    # Available datastores
    STORES = [
        "dsswres", "dsswresaloc", "kbmetadata", "kbdata",
        "tosca_imported", "tosca_adt", "tosca_capacities",
        "tosca_deploymentplan", "tosca_eventhistory", "whoiswho",
    ]

    def __init__(self,
                 base_url: str = "http://193.225.250.240/optimusdb1",
                 context: str = "swarmkb",
                 timeout: int = 30,
                 log_level: str = "INFO"):
        """
        Initialize OptimusDB client.

        Args:
            base_url: Base URL of OptimusDB server (e.g. http://193.225.250.240/optimusdb1)
            context: API context path (default: optimusdb)
            timeout: Request timeout in seconds
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        """
        self.base_url = base_url.rstrip('/')
        self.context = context
        self.timeout = timeout
        self.command_url = f"{self.base_url}/{self.context}/command"
        self.upload_url = f"{self.base_url}/{self.context}/upload"
        self.sql_url = f"{self.base_url}/{self.context}/ems/sql"

        # Setup logging
        self.setup_logging(log_level)

        self.logger.info(f"OptimusDB Client initialized")
        self.logger.info(f"Server: {self.base_url}")
        self.logger.info(f"Context: {self.context}")

    def setup_logging(self, log_level: str):
        """Configure logging with colors and formatting."""
        self.logger = logging.getLogger('OptimusDB')
        self.logger.setLevel(getattr(logging, log_level.upper()))
        self.logger.handlers.clear()

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, log_level.upper()))
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

    def _execute_command(self, method: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        Execute a command against OptimusDB.

        Args:
            method: Method dictionary with 'cmd' and optionally 'argcnt'
            **kwargs: Additional parameters (criteria, dstype, args, etc.)

        Returns:
            Response dictionary
        """
        payload = {
            "method": method,
            **kwargs
        }

        self.logger.debug(f"Request payload: {json.dumps(payload, indent=2)}")

        try:
            response = requests.post(
                self.command_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=self.timeout
            )

            self.logger.debug(f"Response status: {response.status_code}")
            self.logger.debug(f"Response body: {response.text[:500]}")

            response.raise_for_status()
            result = response.json()

            self.logger.info(f"Command '{method['cmd']}' executed successfully")
            return result

        except requests.exceptions.Timeout:
            self.logger.error(f"Request timeout after {self.timeout} seconds")
            raise
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request failed: {str(e)}")
            raise
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse response JSON: {str(e)}")
            raise

    # ============================================================================
    # CRUD OPERATIONS
    # ============================================================================

    def get(self,
            criteria: Optional[List[Dict[str, Any]]] = None,
            dstype: str = "dsswres") -> Dict[str, Any]:
        """
        Get documents from OptimusDB.

        Args:
            criteria: Query criteria (empty for all documents)
            dstype: Datastore type (dsswres, dsswresaloc, kbmetadata, etc.)

        Returns:
            Response with matching documents
        """
        if criteria is None:
            criteria = []

        self.logger.info(f"Getting documents from {dstype}")

        result = self._execute_command(
            method={"cmd": "crudget", "argcnt": 1},
            dstype=dstype,
            criteria=criteria
        )

        count = len(result.get('data', [])) if isinstance(result.get('data'), list) else 0
        self.logger.info(f"Retrieved {count} document(s)")
        return result

    def create(self,
               documents: List[Dict[str, Any]],
               dstype: str = "dsswres") -> Dict[str, Any]:
        """Create (insert) documents into OptimusDB."""
        self.logger.info(f"Creating {len(documents)} document(s) in {dstype}")
        result = self._execute_command(
            method={"cmd": "crudput", "argcnt": 1},
            dstype=dstype,
            criteria=documents
        )
        self.logger.info("Documents created successfully")
        return result

    def update(self,
               criteria: List[Dict[str, Any]],
               update_data: List[Dict[str, Any]],
               dstype: str = "dsswres") -> Dict[str, Any]:
        """Update documents matching criteria."""
        self.logger.info(f"Updating documents in {dstype}")
        result = self._execute_command(
            method={"cmd": "crudupdate", "argcnt": 1},
            dstype=dstype,
            criteria=criteria,
            UpdateData=update_data
        )
        self.logger.info("Update completed")
        return result

    def delete(self,
               criteria: List[Dict[str, Any]],
               dstype: str = "dsswres") -> Dict[str, Any]:
        """Delete documents matching criteria."""
        self.logger.info(f"Deleting documents from {dstype}")
        result = self._execute_command(
            method={"cmd": "cruddelete", "argcnt": 1},
            dstype=dstype,
            criteria=criteria
        )
        self.logger.info("Delete completed")
        return result

    def delete_all(self, dstype: str = "dsswres") -> Dict[str, Any]:
        """Delete ALL documents from a datastore. Use with caution!"""
        self.logger.warning(f"Deleting ALL documents from {dstype}")
        return self.delete(criteria=[{"_id": {"$regex": ".*"}}], dstype=dstype)

    # ============================================================================
    # QUERY OPERATIONS
    # ============================================================================

    def query(self,
              criteria: Optional[List[Dict[str, Any]]] = None,
              dstype: str = "dsswres",
              options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Advanced query with strategy options.

        Args:
            criteria: Query criteria (list of dicts with field/operator/value)
            dstype: Datastore to query (dsswres, kbmetadata, etc.)
            options: Query options (strategy, time_budget_ms, etc.)

        Returns:
            Response with matching documents
        """
        if criteria is None:
            criteria = []

        self.logger.info(f"Executing query on {dstype} with {len(criteria)} criteria")

        payload = {
            "method": {"cmd": "query", "argcnt": 0},
            "dstype": dstype,
            "criteria": criteria,
        }
        if options:
            payload["options"] = options

        result = self._execute_command(**payload)
        return result

    # ============================================================================
    # TOSCA OPERATIONS
    # ============================================================================

    def upload_tosca(self,
                     file_path: str,
                     store_full_structure: bool = True,
                     target_store: str = "dsswres") -> Dict[str, Any]:
        """
        Upload a TOSCA YAML file to OptimusDB.

        Args:
            file_path: Path to TOSCA YAML file
            store_full_structure: If True, creates queryable structured documents.
            target_store: Target OrbitDB store (dsswres, dsswresaloc, etc.)

        Returns:
            Response with upload result including template_id
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        self.logger.info(f"Uploading TOSCA file: {file_path}")
        self.logger.info(f"Full structure: {store_full_structure}, Target store: {target_store}")

        with open(file_path, 'rb') as f:
            file_content = f.read()

        # Validate YAML
        try:
            yaml.safe_load(file_content)
        except yaml.YAMLError as e:
            self.logger.error(f"Invalid YAML: {str(e)}")
            raise

        file_b64 = base64.b64encode(file_content).decode('utf-8')

        payload = {
            "file": file_b64,
            "filename": file_path.name,
            "store_full_structure": store_full_structure,
            "target_store": target_store,
        }

        self.logger.debug(f"File size: {len(file_content)} bytes")

        response = requests.post(
            self.upload_url,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=self.timeout
        )
        response.raise_for_status()

        result = response.json()

        template_id = (
                result.get('data', {}).get('template_id') or
                result.get('template_id')
        )
        if template_id:
            self.logger.info(f"Template ID: {template_id}")
            result['template_id'] = template_id

        storage_info = result.get('data', {})
        if storage_info.get('queryable'):
            self.logger.info("✓ Uploaded with full structure (queryable)")
        else:
            self.logger.warning("⚠️ Uploaded in LEGACY MODE (not queryable)")

        return result

    # ============================================================================
    # EXTENDED METADATA OPERATIONS  (48-field system)
    # ============================================================================

    def get_metadata(self,
                     associated_id: Optional[str] = None,
                     metadata_id: Optional[str] = None,
                     criteria: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Query metadata entries from OrbitDB KBMetadata store.

        Args:
            associated_id: Filter by associated TOSCA template ID
            metadata_id: Filter by metadata entry _id
            criteria: Raw criteria list (overrides the above)

        Returns:
            Response with matching metadata entries
        """
        if criteria is not None:
            q = criteria
        elif metadata_id:
            q = [{"_id": metadata_id}]
        elif associated_id:
            q = [{"associated_id": associated_id}]
        else:
            q = []

        self.logger.info(f"Querying metadata (KBMetadata) with {len(q)} criteria")
        return self.query(criteria=q, dstype="kbmetadata")

    def wait_for_metadata(self,
                          associated_id: str,
                          timeout_seconds: int = 20,
                          poll_interval: float = 1.0) -> Optional[Dict[str, Any]]:
        """
        Wait for async metadata generation after TOSCA upload.

        Args:
            associated_id: The template_id returned from upload
            timeout_seconds: Maximum time to wait
            poll_interval: Seconds between polls

        Returns:
            The metadata entry dict, or None if not found within timeout
        """
        self.logger.info(f"Waiting for metadata generation (associated_id={associated_id})...")

        start = time.time()
        while (time.time() - start) < timeout_seconds:
            res = self.get_metadata(associated_id=associated_id)
            data = res.get('data', [])
            entries = data if isinstance(data, list) else [data] if data else []

            if entries and entries[0]:
                meta_id = entries[0].get('_id', '?')
                elapsed = time.time() - start
                self.logger.info(f"✓ Metadata found in {elapsed:.1f}s — _id={meta_id}")
                return entries[0]

            time.sleep(poll_interval)

        self.logger.warning(f"Metadata not found after {timeout_seconds}s")
        return None

    def update_metadata_fields(self,
                               metadata_id: str,
                               updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update specific fields of a metadata entry (OrbitDB + SQLite).

        Fetches the current doc, merges updates, and PUTs back.
        Also updates SQLite metadata_catalog via /ems/sql.

        Args:
            metadata_id: The _id of the metadata entry
            updates: Dict of field→value to change

        Returns:
            The updated document
        """
        self.logger.info(f"Updating metadata {metadata_id}: {list(updates.keys())}")

        # 1) Fetch current document
        res = self.get_metadata(metadata_id=metadata_id)
        data = res.get('data', [])
        entries = data if isinstance(data, list) else [data] if data else []

        if not entries or not entries[0]:
            raise ValueError(f"Metadata entry not found: {metadata_id}")

        doc = entries[0]

        # 2) Merge updates
        doc.update(updates)
        doc['updated_at'] = datetime.utcnow().isoformat() + 'Z'

        # 3) PUT back to OrbitDB
        self._execute_command(
            method={"cmd": "crudput", "argcnt": 1},
            dstype="kbmetadata",
            criteria=[doc]
        )
        self.logger.info(f"✓ OrbitDB KBMetadata updated")

        # 4) Also update SQLite
        try:
            set_clauses = []
            for field, value in updates.items():
                safe_val = str(value).replace("'", "''")
                set_clauses.append(f"{field} = '{safe_val}'")
            set_clauses.append(f"updated_at = '{doc['updated_at']}'")

            sql = f"UPDATE metadata_catalog SET {', '.join(set_clauses)} WHERE id = '{metadata_id}'"
            self.execute_sql(sql)
            self.logger.info(f"✓ SQLite metadata_catalog updated")
        except Exception as e:
            self.logger.warning(f"SQLite update failed (non-fatal): {e}")

        return doc

    def add_metadata_field(self,
                           metadata_id: str,
                           field_name: str,
                           field_value: Any) -> Dict[str, Any]:
        """Convenience: add or set a single field on a metadata entry."""
        return self.update_metadata_fields(metadata_id, {field_name: field_value})

    # ============================================================================
    # SQL OPERATIONS (SQLite via /ems/sql)
    # ============================================================================

    def execute_sql(self, sql: str) -> Dict[str, Any]:
        """
        Execute a SQL query against the agent's SQLite database.

        Tables: metadata_catalog, tosca_metadata, optimusLogger, ems_events.

        Args:
            sql: SQL query string

        Returns:
            Response dict with 'records' key
        """
        self.logger.info(f"SQL: {sql[:120]}...")

        response = requests.post(
            self.sql_url,
            json={"sql": sql},
            headers={'Content-Type': 'application/json'},
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def get_metadata_sql(self,
                         associated_id: Optional[str] = None,
                         limit: int = 20) -> List[Dict[str, Any]]:
        """Query metadata_catalog via SQLite for fast local lookups."""
        if associated_id:
            sql = f"SELECT * FROM metadata_catalog WHERE associated_id = '{associated_id}' LIMIT {limit}"
        else:
            sql = f"SELECT * FROM metadata_catalog ORDER BY created_at DESC LIMIT {limit}"

        result = self.execute_sql(sql)
        return result.get('records', [])

    def get_schema_info(self) -> Dict[str, Any]:
        """Get metadata_catalog table schema (PRAGMA table_info)."""
        result = self.execute_sql("PRAGMA table_info(metadata_catalog)")
        columns = result.get('records', [])
        return {
            'columns': columns,
            'count': len(columns),
            'column_names': [c.get('name', '') for c in columns]
        }

    def verify_48_columns(self) -> Dict[str, Any]:
        """Verify the metadata_catalog table has all 48 expected columns."""
        expected = [
            "id", "author", "metadata_type", "component", "behaviour",
            "relationships", "associated_id", "name", "description", "tags",
            "status", "created_by", "created_at", "updated_at", "related_ids",
            "priority", "scheduling_info", "sla_constraints", "ownership_details",
            "audit_trail", "data_domain", "data_classification", "geo_location",
            "temporal_coverage", "data_quality_score", "schema_version",
            "content_hash", "file_format", "file_size_bytes", "record_count",
            "update_frequency", "retention_policy", "access_control",
            "compliance_tags", "provenance_chain", "processing_status",
            "api_endpoint", "version", "parent_id", "expiry_date",
            "language", "license_type", "contact_info", "node_count",
            "ipfs_cid", "source_agent", "source_pod", "source_ip",
        ]

        schema = self.get_schema_info()
        actual = schema['column_names']

        present = [c for c in expected if c in actual]
        missing = [c for c in expected if c not in actual]

        return {
            'ok': len(missing) == 0,
            'total': len(actual),
            'expected': 48,
            'present': present,
            'missing': missing,
        }

    # ============================================================================
    # UTILITY OPERATIONS
    # ============================================================================

    def get_agent_status(self) -> Dict[str, Any]:
        """Get OptimusDB agent status including cluster information."""
        response = requests.get(
            f"{self.base_url}/{self.context}/agent/status",
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def get_peers(self) -> Dict[str, Any]:
        """Get list of discovered peers."""
        response = requests.get(
            f"{self.base_url}/{self.context}/peers",
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def get_mesh_status(self) -> Dict[str, Any]:
        """Get OrbitDB mesh connectivity and replication status."""
        response = requests.get(
            f"{self.base_url}/{self.context}/debug/optimusdb/mesh",
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def health_check(self) -> bool:
        """Check if OptimusDB server is reachable."""
        try:
            response = requests.get(
                f"{self.base_url}/{self.context}/agent/status",
                timeout=5
            )
            healthy = response.status_code == 200
            if healthy:
                self.logger.info("✓ Server is healthy")
            else:
                self.logger.warning(f"✗ Server returned status {response.status_code}")
            return healthy
        except Exception as e:
            self.logger.error(f"✗ Server unreachable: {str(e)}")
            return False

    # ============================================================================
    # PRETTY PRINTING
    # ============================================================================

    def print_result(self, result: Dict[str, Any], title: str = "Result"):
        """Pretty print operation result."""
        print(f"\n{'='*80}")
        print(f"  {title}")
        print(f"{'='*80}")
        status = result.get('status', 'unknown')
        print(f"  Status: {status}")
        data = result.get('data')
        if data is not None:
            if isinstance(data, str):
                print(f"\n  {data}")
            elif isinstance(data, list):
                print(f"\n  Documents: {len(data)}")
                if data:
                    print(json.dumps(data, indent=2))
            else:
                print(json.dumps(data, indent=2))
        print(f"{'='*80}\n")

    def print_documents(self, documents: List[Dict[str, Any]], max_display: int = 10):
        """Pretty print documents list."""
        count = len(documents)
        print(f"\n{'='*80}")
        print(f"  Retrieved {count} document(s)")
        print(f"{'='*80}")
        if count == 0:
            print("  No documents found"); return
        print("\n  Document IDs:")
        for i, doc in enumerate(documents, 1):
            doc_id = doc.get('_id', 'unknown')
            doc_type = doc.get('document_type', doc.get('type', 'N/A'))
            print(f"    {i}. {doc_id} ({doc_type})")
        if count <= max_display:
            print(json.dumps(documents, indent=2))
        else:
            print(json.dumps(documents[:max_display], indent=2))
            print(f"\n  ... and {count - max_display} more")
        print(f"{'='*80}\n")

    def print_metadata_summary(self, entry: Dict[str, Any]):
        """Pretty print a metadata entry showing key fields grouped."""
        print(f"\n{'─'*70}")
        print(f"  Metadata Entry: {entry.get('_id', entry.get('id', '?'))}")
        print(f"{'─'*70}")

        groups = {
            "Core":           ["name", "author", "metadata_type", "status", "version", "description"],
            "Relations":      ["associated_id", "parent_id", "component", "behaviour"],
            "Classification": ["data_domain", "data_classification", "language", "license_type"],
            "Quality":        ["data_quality_score", "priority", "node_count", "file_size_bytes", "record_count"],
            "Temporal":       ["created_at", "updated_at", "update_frequency", "expiry_date"],
            "Provenance":     ["source_agent", "source_pod", "source_ip", "ipfs_cid", "processing_status"],
        }
        for group_name, fields in groups.items():
            vals = {f: entry.get(f) for f in fields if entry.get(f)}
            if vals:
                print(f"\n  {group_name}:")
                for f, v in vals.items():
                    print(f"    {f:30s} = {v}")

        print(f"{'─'*70}\n")


# ============================================================================
# CLI INTERFACE
# ============================================================================

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='OptimusDB Python Client',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python optimusdb_client.py get
  python optimusdb_client.py upload toscaSamples/webapp_adt.yaml
  python optimusdb_client.py upload toscaSamples/webapp_adt.yaml --target-store dsswresaloc
  python optimusdb_client.py metadata --associated-id <template_id>
  python optimusdb_client.py sql "SELECT * FROM metadata_catalog LIMIT 5"
  python optimusdb_client.py verify-schema
  python optimusdb_client.py mesh
        """
    )

    parser.add_argument('--url', default='http://193.225.250.240/optimusdb1',
                        help='OptimusDB base URL (default: http://193.225.250.240/optimusdb1)')
    parser.add_argument('--context', default='swarmkb',
                        help='API context (default: swarmkb)')
    parser.add_argument('--log-level', default='INFO',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'])

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # GET
    get_p = subparsers.add_parser('get', help='Get documents')
    get_p.add_argument('--criteria', nargs='+')
    get_p.add_argument('--dstype', default='dsswres')

    # CREATE
    create_p = subparsers.add_parser('create', help='Create documents')
    create_p.add_argument('--json', required=True)
    create_p.add_argument('--dstype', default='dsswres')

    # UPDATE
    update_p = subparsers.add_parser('update', help='Update documents')
    update_p.add_argument('--criteria', nargs='+', required=True)
    update_p.add_argument('--data', required=True)
    update_p.add_argument('--dstype', default='dsswres')

    # DELETE
    del_p = subparsers.add_parser('delete', help='Delete documents')
    del_p.add_argument('--criteria', nargs='+', required=True)
    del_p.add_argument('--dstype', default='dsswres')

    # DELETE ALL
    delall_p = subparsers.add_parser('delete-all', help='Delete ALL documents')
    delall_p.add_argument('--dstype', default='dsswres')
    delall_p.add_argument('--confirm', action='store_true')

    # UPLOAD
    upload_p = subparsers.add_parser('upload', help='Upload TOSCA file')
    upload_p.add_argument('file', help='Path to TOSCA YAML file')
    upload_p.add_argument('--target-store', default='dsswres')
    upload_p.add_argument('--legacy-mode', action='store_true')

    # METADATA
    meta_p = subparsers.add_parser('metadata', help='Query metadata entries')
    meta_p.add_argument('--associated-id', help='Filter by associated template ID')
    meta_p.add_argument('--id', help='Filter by metadata _id')

    # SQL
    sql_p = subparsers.add_parser('sql', help='Execute SQL query')
    sql_p.add_argument('query', help='SQL query string')

    # VERIFY SCHEMA
    subparsers.add_parser('verify-schema', help='Verify 48-column metadata schema')

    # STATUS / PEERS / HEALTH / MESH
    subparsers.add_parser('status', help='Get agent status')
    subparsers.add_parser('peers', help='Get peer list')
    subparsers.add_parser('health', help='Check server health')
    subparsers.add_parser('mesh', help='Get mesh connectivity status')

    args = parser.parse_args()

    if not args.command:
        parser.print_help(); sys.exit(1)

    client = OptimusDBClient(
        base_url=args.url, context=args.context, log_level=args.log_level
    )

    try:
        if args.command == 'get':
            criteria = parse_criteria(args.criteria) if args.criteria else []
            result = client.get(criteria=criteria, dstype=args.dstype)
            if isinstance(result.get('data'), list):
                client.print_documents(result['data'])
            else:
                client.print_result(result, "GET Result")

        elif args.command == 'create':
            documents = parse_json_arg(args.json)
            if not isinstance(documents, list): documents = [documents]
            result = client.create(documents=documents, dstype=args.dstype)
            client.print_result(result, "CREATE Result")

        elif args.command == 'update':
            criteria = parse_criteria(args.criteria)
            update_data = parse_json_arg(args.data)
            if not isinstance(update_data, list): update_data = [update_data]
            result = client.update(criteria=criteria, update_data=update_data, dstype=args.dstype)
            client.print_result(result, "UPDATE Result")

        elif args.command == 'delete':
            criteria = parse_criteria(args.criteria)
            result = client.delete(criteria=criteria, dstype=args.dstype)
            client.print_result(result, "DELETE Result")

        elif args.command == 'delete-all':
            if not args.confirm:
                resp = input(f"⚠️  Delete ALL from {args.dstype}? Type 'yes': ")
                if resp.lower() != 'yes': print("Cancelled"); sys.exit(0)
            result = client.delete_all(dstype=args.dstype)
            client.print_result(result, "DELETE ALL Result")

        elif args.command == 'upload':
            result = client.upload_tosca(args.file,
                                         store_full_structure=not args.legacy_mode,
                                         target_store=args.target_store)
            client.print_result(result, "UPLOAD Result")

        elif args.command == 'metadata':
            result = client.get_metadata(
                associated_id=getattr(args, 'associated_id', None),
                metadata_id=getattr(args, 'id', None))
            data = result.get('data', [])
            entries = data if isinstance(data, list) else [data] if data else []
            for entry in entries:
                client.print_metadata_summary(entry)

        elif args.command == 'sql':
            result = client.execute_sql(args.query)
            records = result.get('records', [])
            print(f"\n  {len(records)} row(s)")
            print(json.dumps(records, indent=2))

        elif args.command == 'verify-schema':
            result = client.verify_48_columns()
            if result['ok']:
                print(f"\n  ✓ All 48 columns present (total: {result['total']})")
            else:
                print(f"\n  ✗ Missing {len(result['missing'])} columns:")
                for c in result['missing']: print(f"    - {c}")

        elif args.command == 'status':
            client.print_result(client.get_agent_status(), "Agent Status")
        elif args.command == 'peers':
            client.print_result(client.get_peers(), "Peer List")
        elif args.command == 'health':
            sys.exit(0 if client.health_check() else 1)
        elif args.command == 'mesh':
            client.print_result(client.get_mesh_status(), "Mesh Status")

    except Exception as e:
        client.logger.error(f"Command failed: {str(e)}")
        sys.exit(1)


def parse_criteria(criteria_list: List[str]) -> List[Dict[str, Any]]:
    """Parse criteria from CLI: field:value or field:value:operator"""
    criteria = {}
    for item in criteria_list:
        parts = item.split(':', 2)
        if len(parts) == 2:
            criteria[parts[0]] = parts[1]
        elif len(parts) == 3:
            field, value, operator = parts
            try: value = int(value)
            except ValueError:
                try: value = float(value)
                except ValueError: pass
            criteria[field] = {f"${operator}": value}
        else:
            raise ValueError(f"Invalid criteria: {item}")
    return [criteria] if criteria else []


def parse_json_arg(json_arg: str) -> Any:
    """Parse JSON argument (string or file path)."""
    if os.path.exists(json_arg):
        with open(json_arg, 'r') as f: return json.load(f)
    return json.loads(json_arg)


if __name__ == '__main__':
    main()