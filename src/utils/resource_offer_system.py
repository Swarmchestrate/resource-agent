"""
Resource Request Broadcasting System for P2P Resource Agents

This module implements ONLY the resource request broadcasting functionality:
1. Create resource request from TOSCA requirements
2. Broadcast to P2P network
3. Track broadcast status

Future phases will add offer collection and ranking.
"""

import logging
import uuid
from typing import Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class ResourceRequestBroadcaster:
    """
    Simple Resource Request Broadcaster that creates and tracks resource requests.
    """
    
    def __init__(self, ra_id: str):
        """
        Initialize the Resource Request Broadcaster.
        
        Args:
            ra_id: The ID of this Resource Agent
        """
        self.ra_id = ra_id
        self.broadcasted_requests: Dict[str, Dict[str, Any]] = {}
        
    def create_and_broadcast_request(self, resource_requirements: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a resource request message and prepare it for broadcasting.
        
        Args:
            resource_requirements: Parsed TOSCA requirements
            
        Returns:
            Resource request message ready for P2P broadcast
        """
        # Generate unique request ID
        request_id = f"req_{self.ra_id}_{uuid.uuid4().hex[:8]}_{int(datetime.now().timestamp())}"
        
        # Create the broadcast message
        request_message = {
            "message_type": "resource_request",
            "request_id": request_id,
            "source_ra": self.ra_id,
            "timestamp": datetime.now().isoformat(),
            "resource_requirements": resource_requirements,
            "status": "broadcasted"
        }
        
        # Store the broadcasted request for tracking
        self.broadcasted_requests[request_id] = {
            "message": request_message,
            "broadcasted_at": datetime.now(),
            "status": "broadcasted",
            "target_peers": "all_peers_in_p2p_network"
        }
        
        logger.info(f"📡 Created resource request {request_id}")
        logger.info(f"📋 Broadcasting to P2P network with {len(resource_requirements.get('resource_requirements', []))} nodes")
        
        return request_message
    
    def get_broadcast_status(self, request_id: str) -> Dict[str, Any]:
        """
        Get the status of a broadcasted resource request.
        
        Args:
            request_id: ID of the resource request
            
        Returns:
            Broadcast status information
        """
        if request_id not in self.broadcasted_requests:
            return {"status": "not_found", "message": f"Request {request_id} not found"}
        
        request_info = self.broadcasted_requests[request_id]
        
        return {
            "request_id": request_id,
            "status": request_info["status"],
            "broadcasted_at": request_info["broadcasted_at"].isoformat(),
            "source_ra": request_info["message"]["source_ra"],
            "target_peers": request_info["target_peers"],
            "resource_nodes": len(request_info["message"]["resource_requirements"].get("resource_requirements", [])),
            "message": f"Resource request {request_id} was broadcasted to P2P network"
        }
    
    def list_broadcasted_requests(self) -> Dict[str, Any]:
        """
        List all broadcasted resource requests.
        
        Returns:
            Summary of all broadcasted requests
        """
        requests_summary = []
        
        for req_id, req_info in self.broadcasted_requests.items():
            requests_summary.append({
                "request_id": req_id,
                "status": req_info["status"],
                "broadcasted_at": req_info["broadcasted_at"].isoformat(),
                "resource_nodes": len(req_info["message"]["resource_requirements"].get("resource_requirements", [])),
                "source_ra": req_info["message"]["source_ra"]
            })
        
        return {
            "ra_id": self.ra_id,
            "broadcasted_requests": requests_summary,
            "total_requests": len(requests_summary),
            "message": f"Found {len(requests_summary)} broadcasted resource requests"
        }
