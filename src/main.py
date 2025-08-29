"""
FastAPI application entry point for Swarmchestrate Resource Agent.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import logging
import sys
import threading
import argparse
from pathlib import Path

# Add the src directory to the path for imports
sys.path.append(str(Path(__file__).parent))

from config import RAConfig
from ra_core import ResourceAgent
from api.endpoints import register_endpoints

# Configure logging
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def load_config(config_path: str = "config/config.yaml"):
    """Load configuration from specified path."""
    try:
        config = RAConfig.from_yaml(config_path)
        logger.info(f"Loaded configuration for RA: {config.id}")
        return config
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        raise

def create_app(config: RAConfig):
    """Create FastAPI application with configuration."""
    # Initialize Resource Agent
    ra = ResourceAgent(config)
    
    # Create FastAPI app
    app = FastAPI(
        title="Swarmchestrate Resource Agent",
        description="P2P-based resource agent for distributed computing",
        version="0.1.0"
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Make RA accessible in endpoints
    app.state.ra = ra
    
    # Register API endpoints
    register_endpoints(app, ra)
    
    @app.get("/")
    async def root():
        """Root endpoint."""
        return {
            "message": "Swarmchestrate Resource Agent", 
            "version": "0.1.0",
            "ra_id": config.id
        }
    
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy", "ra_id": config.id}
    
    return app, ra

def start_api_server(app: FastAPI, config: RAConfig):
    """Start the FastAPI server."""
    uvicorn.run(
        app,
        host=config.domain,
        port=config.api_port,
        reload=False
    )

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Swarmchestrate Resource Agent")
    parser.add_argument('--config', default='config/config.yaml', 
                       help='Path to configuration file')
    args = parser.parse_args()
    
    # Load configuration
    config = load_config(args.config)
    
    # Create application
    app, ra = create_app(config)
    
    # Start API server in a separate thread
    api_thread = threading.Thread(target=start_api_server, args=(app, config), daemon=True)
    api_thread.start()
    
    logger.info(f"API server started on {config.domain}:{config.api_port}")
    
    # Start P2P reactor in the main thread
    try:
        ra.start()
    except KeyboardInterrupt:
        logger.info("Shutting down RA...")
    except Exception as e:
        logger.error(f"Error in P2P reactor: {e}")