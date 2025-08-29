"""
Helper utility functions for Swarmchestrate RA.
"""

import time
import hashlib
from typing import Dict, Any, Optional


def generate_reservation_id(ra_id: str, app_desc: Dict[str, Any] = None) -> str:
    """
    Generate a unique reservation ID.
    
    Args:
        ra_id: The RA identifier
        app_desc: Application description (optional, for additional uniqueness)
    
    Returns:
        A unique reservation ID in format: res_{ra_id}_{timestamp}
    """
    timestamp = int(time.time())
    
    if app_desc:
        # Add hash of app_desc for additional uniqueness
        app_hash = hashlib.md5(str(app_desc).encode()).hexdigest()[:8]
        return f"res_{ra_id}_{app_hash}_{timestamp}"
    else:
        return f"res_{ra_id}_{timestamp}"


def validate_app_description(app_desc: Dict[str, Any]) -> bool:
    """
    Validate application description.
    
    Args:
        app_desc: Application description dictionary
    
    Returns:
        True if valid, False otherwise
    """
    if not isinstance(app_desc, dict):
        return False
    
    # Check for required 'flavor' field
    if 'flavor' not in app_desc:
        return False
    
    # Validate flavor structure
    flavor = app_desc.get('flavor')
    if not isinstance(flavor, dict):
        return False
    
    # Check that flavor values are positive integers
    for flavor_name, count in flavor.items():
        if not isinstance(count, int) or count <= 0:
            return False
    
    return True


def format_app_description(app_desc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format and clean application description.
    
    Args:
        app_desc: Raw application description
    
    Returns:
        Formatted application description
    """
    formatted = {
        'flavor': app_desc.get('flavor', {})
    }
    
    # Only add requirements if it's not None
    requirements = app_desc.get('requirements')
    if requirements is not None:
        formatted['requirements'] = requirements
    
    return formatted


def get_app_summary(app_desc: Dict[str, Any]) -> str:
    """
    Get a human-readable summary of the application description.
    
    Args:
        app_desc: Application description (TOSCA structure)
    
    Returns:
        Summary string
    """
    # Handle TOSCA structure: {"resource_requirements": [...], "total_nodes": N, ...}
    if 'resource_requirements' in app_desc:
        total_nodes = app_desc.get('total_nodes', 0)
        requirements = app_desc.get('resource_requirements', [])
        
        summary = f"TOSCA Application: {total_nodes} nodes"
        
        if requirements and isinstance(requirements, list):
            node_summaries = []
            for node in requirements:
                node_name = node.get('node_name', 'unknown')
                node_type = node.get('node_type', 'unknown')
                resources = node.get('resources', {})
                
                # Extract resource info
                cpu = resources.get('cpu', {})
                memory = resources.get('memory', {})
                storage = resources.get('storage', {})
                
                node_summary = f"{node_name}({node_type})"
                if cpu:
                    node_summary += f" CPU:{cpu.get('value', '?')}{cpu.get('unit', '')}"
                if memory:
                    node_summary += f" RAM:{memory.get('value', '?')}{memory.get('unit', '')}"
                if storage:
                    node_summary += f" Storage:{storage.get('value', '?')}{storage.get('unit', '')}"
                
                node_summaries.append(node_summary)
            
            if node_summaries:
                summary += f" - {', '.join(node_summaries)}"
        
        return summary
    
    # Fallback for old flavor-based structure
    flavor = app_desc.get('flavor', {})
    requirements = app_desc.get('requirements')
    
    flavor_summary = ", ".join([f"{name}: {count}" for name, count in flavor.items()])
    
    summary = f"Flavors: {flavor_summary}"
    if requirements and isinstance(requirements, dict):
        req_summary = ", ".join([f"{k}: {v}" for k, v in requirements.items()])
        if req_summary:
            summary += f" | Requirements: {req_summary}"
    
    return summary 