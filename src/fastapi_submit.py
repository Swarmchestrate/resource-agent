#!/usr/bin/env python3

import sys
import yaml
import time
import tempfile
import os
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, HTTPException
import uvicorn

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.job_submission_client import JobSubmissionClient

# Initialize FastAPI app
app = FastAPI(
    title="Swarmchestrate Job Submission API",
    description="Simple REST API for submitting ask.yaml files",
    version="1.0.0"
)


@app.post("/submit")
async def submit_job(
    ask_file: UploadFile = File(..., description="ask.yaml file containing resource requirements"),
    hub_host: str = "127.0.0.1",
    hub_port: int = 5000,
    gw_ra_id: str = "hub-ra"
):

    # Validate file type
    if not ask_file.filename.endswith(('.yaml', '.yml')):
        raise HTTPException(
            status_code=400,
            detail="File must be a YAML file (.yaml or .yml extension)"
        )
    
    try:
        # Read and validate YAML content
        content = await ask_file.read()
        yaml_data = yaml.safe_load(content.decode('utf-8'))
        
        if not yaml_data:
            raise HTTPException(
                status_code=400,
                detail="YAML file is empty or invalid"
            )
        
        # Generate unique client ID
        client_id = f"fastapi_client_{int(time.time())}"
        
        # Save YAML to temporary file (required by JobSubmissionClient)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as temp_file:
            yaml.dump(yaml_data, temp_file, default_flow_style=False)
            temp_file_path = temp_file.name
        
        try:
            # Create and use JobSubmissionClient (same as command-line version)
            client = JobSubmissionClient(client_id=client_id)
            
            # Submit job using existing client
            success = client.submit_job(temp_file_path, hub_host, hub_port, gw_ra_id)
            
            # Prepare response
            resource_names = list(yaml_data.keys())
            
            if success:
                return {
                    "status": "success",
                    "message": f"Job submitted successfully to {gw_ra_id} at {hub_host}:{hub_port}",
                    "client_id": client_id,
                    "resources_requested": resource_names,
                    "resource_count": len(resource_names),
                    "gateway_ra": gw_ra_id,
                    "timestamp": time.time()
                }
            else:
                return {
                    "status": "failed",
                    "message": "Failed to submit job to RA network",
                    "client_id": client_id,
                    "error": "Job submission unsuccessful"
                }
                
        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_file_path)
            except OSError:
                pass
        
    except yaml.YAMLError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid YAML format: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "service": "Swarmchestrate Job Submission API",
        "description": "Submit ask.yaml files instead of using command line",
        "usage": "POST /submit with ask.yaml file",
        "equivalent_to": "python job_submission_client.py [ask.yaml] [hub_host] [hub_port] [gw_ra_id]"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": time.time()}


def main():
    """Run the FastAPI server"""
    print("=" * 60)
    print("Swarmchestrate FastAPI Job Submission Service")
    print("=" * 60)
    print("Starting server on http://127.0.0.1:8000")
    print("API Documentation: http://127.0.0.1:8000/docs")
    print("Submit endpoint: POST http://127.0.0.1:8000/submit")
    print("=" * 60)
    
    uvicorn.run(
        "fastapi_submit:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info"
    )


if __name__ == "__main__":
    main()
