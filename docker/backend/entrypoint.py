"""
Backend Container Entrypoint
============================
Entry point untuk backend container di Docker
"""

import os
import sys
import asyncio
import json
import logging

# Add src to path
sys.path.insert(0, '/app')

from src.crypto import KeyMaterial
from src.config import BrokerConfig
from src.backend import run_backend

logging.basicConfig(
    level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO')),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_or_generate_keys() -> KeyMaterial:
    """Load keys dari file atau generate baru"""
    keys_file = '/data/keys/shared_keys.json'
    
    if os.path.exists(keys_file):
        logger.info(f"Loading keys from {keys_file}")
        with open(keys_file, 'r') as f:
            data = json.load(f)
        return KeyMaterial.from_hex_dict(data)
    else:
        logger.info("Generating new keys")
        keys = KeyMaterial.generate()
        
        # Save keys
        os.makedirs(os.path.dirname(keys_file), exist_ok=True)
        with open(keys_file, 'w') as f:
            json.dump(keys.to_hex_dict(), f, indent=2)
        
        return keys


async def main():
    """Main entrypoint"""
    # Load configuration from environment
    backend_id = os.getenv('BACKEND_ID', 'backend_main')
    duration = int(os.getenv('SIM_DURATION', '3600'))
    
    logger.info(f"Starting backend: {backend_id}")
    
    # Load keys
    keys = load_or_generate_keys()
    
    # Create broker config
    broker_config = BrokerConfig(
        host=os.getenv('BROKER_HOST', 'localhost'),
        port=int(os.getenv('BROKER_PORT', '1883'))
    )
    
    # Run backend
    stats = await run_backend(
        backend_id=backend_id,
        keys=keys,
        broker_config=broker_config,
        duration_seconds=duration
    )
    
    # Save results
    results_file = f'/data/results/{backend_id}_results.json'
    os.makedirs(os.path.dirname(results_file), exist_ok=True)
    with open(results_file, 'w') as f:
        json.dump(stats, f, indent=2)
    
    logger.info(f"Results saved to {results_file}")


if __name__ == "__main__":
    asyncio.run(main())
