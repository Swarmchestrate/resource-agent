from pydantic import BaseModel, Field
import yaml
from pathlib import Path
from typing import Dict, Optional, List
import logging

logger = logging.getLogger(__name__)

class Credentials(BaseModel):
    """Cloud provider credentials."""
    provider: str
    access_key: str
    secret_key: str

class RAConfig(BaseModel):
    """Resource Agent configuration."""
    id: str = Field(..., description="Unique RA identifier")
    capacity_id: str = Field(..., description="Capacity this RA represents")
    universe_id: str = Field(..., description="Swarmchestrate universe ID")
    credentials: Credentials
    api_port: int = Field(8000, ge=1024, le=65535, description="Port for API")
    p2p_port: int = Field(5000, ge=1024, le=65535, description="Port for P2P")
    domain: str = Field("localhost", description="Domain or IP")
    bootstrap_peers: List[str] = Field(default=[], description="List of bootstrap peers")

    @classmethod
    def from_yaml(cls, file_path: str = "config/config.yaml"):
        """Load configuration from YAML file."""
        try:
            config_file = Path(file_path)
            if config_file.exists():
                with open(config_file, "r") as f:
                    data = yaml.safe_load(f)
                logger.info(f"Configuration loaded from {file_path}")
                return cls(**data)
            else:
                logger.warning(f"Config file {file_path} not found")
                raise FileNotFoundError(f"Config file {file_path} not found")
        except Exception as e:
            logger.error(f"Error loading config file: {e}")
            raise

    def get_api_url(self) -> str:
        """Get the API URL."""
        return f"http://{self.domain}:{self.api_port}"

    def get_p2p_address(self) -> str:
        """Get the P2P address."""
        return f"{self.domain}:{self.p2p_port}"
