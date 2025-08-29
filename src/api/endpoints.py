"""
API endpoints for Swarmchestrate Resource Agent.
"""

from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Dict, Any, Optional
import logging
import time
import hashlib
from pathlib import Path
import yaml

logger = logging.getLogger(__name__)

class TOSCARequest(BaseModel):
    """JSON request model for TOSCA content."""
    tosca_content: str  # TOSCA YAML content as string

class SubmitResponse(BaseModel):
    """Response model for /submit endpoint."""
    ra_id: str
    status: str
    message: str
    resource_requirements: Optional[Dict[str, Any]] = None
    broadcast_info: Optional[Dict[str, Any]] = None

class CapacityRequest(BaseModel):
    """Capacity request model."""
    amount: int

class CapacityResponse(BaseModel):
    """Capacity response model."""
    success: bool
    message: str
    available_capacity: int = 0

def register_endpoints(app: FastAPI, ra):
    """Register API endpoints with the FastAPI app."""
    
    @app.post("/submit", response_model=SubmitResponse, tags=["Applications"])
    async def submit_application(tosca_file: UploadFile = File(...)):
        """Submit a TOSCA YAML file for resource allocation."""
        try:
            # Check if file is YAML
            if not tosca_file.filename.endswith(('.yaml', '.yml')):
                raise HTTPException(status_code=400, detail="File must be a YAML file (.yaml or .yml)")
            
            # Read file content
            tosca_content = await tosca_file.read()
            tosca_content_str = tosca_content.decode('utf-8')
            
            # Import and use our TOSCA validator (compares with ask.yaml)
            from utils.tosca_validator import TOSCAValidator
            
            # Validate TOSCA against ask.yaml and extract requirements
            validator = TOSCAValidator()
            validation_result = validator.get_requirements_for_p2p_broadcast(tosca_content_str)
            
            if validation_result["status"] != "ready_for_p2p":
                raise HTTPException(status_code=400, detail=f"TOSCA validation failed: {validation_result.get('message', 'Unknown error')}")
            
            # Use the requirements extracted from ask.yaml (not from submitted file)
            parsed_result = {
                "status": "success",
                "message": "TOSCA validated against ask.yaml",
                "resource_requirements": validation_result["vm_requirements"],
                "total_vms": validation_result["total_vms"],
                "source": "ask.yaml_validation"
            }
            
            # Use config ID instead of complex reservation ID
            ra_id = ra.config.id
            
            logger.info(f"Successfully parsed TOSCA file '{tosca_file.filename}' for RA: {ra_id}")
            
            # ACTUALLY SUBMIT THE APPLICATION TO TRIGGER BROADCASTING
            try:
                reservation_id = ra.submit_application(parsed_result)
                logger.info(f"Application submitted with reservation ID: {reservation_id}")
                
                # Get broadcast information if available
                broadcast_info = None
                if hasattr(ra, 'resource_request_broadcaster'):
                    broadcast_info = {
                        "status": "broadcasted_to_p2p_network",
                        "message": "Resource request automatically broadcasted to all peers",
                        "reservation_id": reservation_id
                    }
                
                return SubmitResponse(
                    ra_id=ra_id,
                    status="success",
                    message=f"TOSCA file '{tosca_file.filename}' submitted successfully",
                    resource_requirements=parsed_result,
                    broadcast_info=broadcast_info
                )
                
            except Exception as e:
                logger.error(f"Failed to submit application: {str(e)}")
                raise HTTPException(status_code=500, detail={"error": str(e), "message": "Failed to submit application"})
            
        except Exception as e:
            logger.error(f"Error submitting TOSCA file: {str(e)}")
            raise HTTPException(status_code=400, detail={"error": str(e), "message": "Failed to process TOSCA file"})

    @app.post("/submit/json", response_model=SubmitResponse, tags=["Applications"])
    async def submit_tosca_json(app_desc: TOSCARequest):
        """Submit TOSCA content as JSON for resource allocation."""
        try:
            # Import and use our TOSCA validator (compares with ask.yaml)
            from utils.tosca_validator import TOSCAValidator
            
            # Validate TOSCA against ask.yaml and extract requirements
            validator = TOSCAValidator()
            validation_result = validator.get_requirements_for_p2p_broadcast(app_desc.tosca_content)
            
            if validation_result["status"] != "ready_for_p2p":
                raise HTTPException(status_code=400, detail=f"TOSCA validation failed: {validation_result.get('message', 'Unknown error')}")
            
            # Use the requirements extracted from ask.yaml (not from submitted file)
            parsed_result = {
                "status": "success",
                "message": "TOSCA validated against ask.yaml",
                "resource_requirements": validation_result["vm_requirements"],
                "total_vms": validation_result["total_vms"],
                "source": "ask.yaml_rest"
            }
            
            # Use config ID instead of complex reservation ID
            ra_id = ra.config.id
            
            logger.info(f"Successfully parsed TOSCA JSON content for RA: {ra_id}")
            
            # ACTUALLY SUBMIT THE APPLICATION TO TRIGGER BROADCASTING
            try:
                reservation_id = ra.submit_application(parsed_result)
                logger.info(f"Application submitted with reservation ID: {reservation_id}")
                
                # Get broadcast information if available
                broadcast_info = None
                if hasattr(ra, 'resource_request_broadcaster'):
                    broadcast_info = {
                        "status": "broadcasted_to_p2p_network",
                        "message": "Resource request automatically broadcasted to all peers",
                        "reservation_id": reservation_id
                    }
                
                return SubmitResponse(
                    ra_id=ra_id,
                    status="success",
                    message="TOSCA content submitted successfully via JSON",
                    resource_requirements=parsed_result,
                    broadcast_info=broadcast_info
                )
                
            except Exception as e:
                logger.error(f"Failed to submit application: {str(e)}")
                raise HTTPException(status_code=500, detail={"error": str(e), "message": "Failed to submit application"})
            
        except Exception as e:
            logger.error(f"Error submitting TOSCA JSON content: {str(e)}")
            raise HTTPException(status_code=400, detail={"error": str(e), "message": "Failed to process TOSCA JSON content"})

    @app.post("/broadcast-ask", response_model=SubmitResponse, tags=["Applications"])
    async def broadcast_ask_requirements():
        """Directly broadcast ask.yaml requirements without TOSCA validation."""
        try:
            logger.info("📡 Direct ask.yaml broadcasting requested")
            
            # Load ask.yaml directly
            ask_yaml_path = Path(__file__).parent.parent.parent.parent / "tosca" / "outputs" / "ask.yaml"
            
            if not ask_yaml_path.exists():
                raise HTTPException(status_code=404, detail={"error": "ask.yaml not found", "message": "ask.yaml file not found at expected location"})
            
            # Load and parse ask.yaml
            with open(ask_yaml_path, 'r', encoding='utf-8') as file:
                ask_data = yaml.safe_load(file)
            
            # Extract requirements directly from ask.yaml
            vm_requirements = []
            total_vms = 0
            
            for vm_name, vm_config in ask_data.items():
                if 'capabilities' in vm_config:
                    vm_count = vm_config.get('count', 1)
                    total_vms += vm_count
                    
                    vm_requirement = {
                        'vm_name': vm_name,
                        'count': vm_count,
                        'metadata': vm_config.get('metadata', {}),
                        'requirements': vm_config['capabilities']
                    }
                    vm_requirements.append(vm_requirement)
            
            # Create the result structure
            parsed_result = {
                "status": "success",
                "message": "ask.yaml requirements loaded directly",
                "resource_requirements": vm_requirements,
                "total_vms": total_vms,
                "source": "direct_ask.yaml"
            }
            
            ra_id = ra.config.id
            logger.info(f"📋 Loaded {total_vms} VMs from ask.yaml for RA: {ra_id}")
            
            # Submit application to trigger broadcasting
            try:
                reservation_id = ra.submit_application(parsed_result)
                logger.info(f"Application submitted with reservation ID: {reservation_id}")
                
                # Get broadcast information
                broadcast_info = {
                    "status": "broadcasted_to_p2p_network",
                    "message": "ask.yaml requirements broadcasted to all peers",
                    "reservation_id": reservation_id
                }
                
                return SubmitResponse(
                    ra_id=ra_id,
                    status="success",
                    message="ask.yaml requirements broadcasted successfully",
                    resource_requirements=parsed_result,
                    broadcast_info=broadcast_info
                )
                
            except Exception as e:
                logger.error(f"Failed to submit application: {str(e)}")
                raise HTTPException(status_code=500, detail={"error": str(e), "message": "Failed to submit application"})
            
        except Exception as e:
            logger.error(f"Error broadcasting ask.yaml: {str(e)}")
            raise HTTPException(status_code=400, detail={"error": str(e), "message": "Failed to broadcast ask.yaml"})

    @app.put("/applications/{reservation_id}", tags=["Applications"])
    async def update_application(reservation_id: str, app_desc: Dict[str, Any]):
        """Update an existing application."""
        try:
            success = ra.update_application(reservation_id, app_desc)
            if success:
                logger.info(f"Updated application: {reservation_id}")
                return {"status": "updated", "reservation_id": reservation_id}
            else:
                raise HTTPException(status_code=404, detail="Reservation not found")
        except Exception as e:
            logger.error(f"Error updating application: {str(e)}")
            raise HTTPException(status_code=404, detail={"error": str(e), "message": "Reservation not found"})

    @app.delete("/applications/{reservation_id}", tags=["Applications"])
    async def delete_application(reservation_id: str):
        """Delete an application."""
        try:
            success = ra.delete_application(reservation_id)
            if success:
                logger.info(f"Deleted application: {reservation_id}")
                return {"status": "deleted", "reservation_id": reservation_id}
            else:
                raise HTTPException(status_code=404, detail="Reservation not found")
        except Exception as e:
            logger.error(f"Error deleting application: {str(e)}")
            raise HTTPException(status_code=404, detail={"error": str(e), "message": "Reservation not found"})

    @app.get("/applications/{reservation_id}", tags=["Applications"])
    async def get_application_status(reservation_id: str):
        """Get application status."""
        try:
            status = ra.get_status(reservation_id)
            if status:
                return status
            else:
                raise HTTPException(status_code=404, detail="Reservation not found")
        except Exception as e:
            logger.error(f"Error getting application status: {str(e)}")
            raise HTTPException(status_code=404, detail={"error": str(e), "message": "Reservation not found"})

    
    @app.get("/status", tags=["Status"])
    async def get_status():
        """Get RA status."""
        try:
            status = {
                "ra_id": ra.config.id,
                "capacity_id": ra.config.capacity_id,
                "universe_id": ra.config.universe_id,
                "api_url": ra.config.get_api_url(),
                "p2p_address": ra.config.get_p2p_address(),
                "status": "running",
                "p2p_available": ra.p2p_agent is not None
            }
            return status
        except Exception as e:
            logger.error(f"Error getting status: {str(e)}")
            raise HTTPException(status_code=500, detail={"error": str(e), "message": "Internal server error"})

    @app.get("/p2p/status", tags=["P2P Network"])
    async def get_p2p_status():
        """Get P2P network status and connected peers."""
        try:
            if hasattr(ra, 'p2p_agent') and ra.p2p_agent:
                # Use the correct SwchAgent methods
                peer_count = ra.p2p_agent.get_connection_count()
                connected_peers = ra.p2p_agent.getConnectedPeers()
                
                return {
                    "ra_id": ra.config.id,
                    "p2p_address": f"{ra.config.domain}:{ra.config.p2p_port}",
                    "status": "connected" if peer_count > 0 else "disconnected",
                    "connected_peers": connected_peers,
                    "peer_count": peer_count
                }
            else:
                return {
                    "ra_id": ra.config.id,
                    "p2p_address": f"{ra.config.domain}:{ra.config.p2p_port}",
                    "status": "not_available",
                    "connected_peers": [],
                    "peer_count": 0
                }
        except Exception as e:
            logger.error(f"Error getting P2P status: {str(e)}")
            raise HTTPException(status_code=500, detail={"error": str(e), "message": "Failed to get P2P status"})

    # Function registration complete - all endpoints are now registered with the app
