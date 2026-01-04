"""
Gateway Container Entrypoint
============================
Entry point untuk gateway container di Docker
"""

import os
import sys
import asyncio
import json
import logging

# Add src to path
sys.path.insert(0, '/app')

from src.crypto import KeyMaterial
from src.config import BrokerConfig, PrivacyConfig, SENSOR_PROFILES
from src.gateway import run_gateway

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


def get_patient_ids(start: int, count: int) -> list:
    """Generate patient IDs untuk gateway ini"""
    return [f"patient_{i:05d}" for i in range(start, start + count)]


def get_sensor_types(scenario: str) -> list:
    """Get sensor types berdasarkan skenario"""
    if scenario == "icu_monitoring":
        return ["ecg", "spo2", "blood_pressure", "temperature"]
    else:  # home_monitoring
        return ["spo2", "blood_pressure", "activity"]


async def main():
    """Main entrypoint"""
    # Load configuration from environment
    gateway_id = os.getenv('GATEWAY_ID', 'gateway_default')
    patient_start = int(os.getenv('PATIENT_START', '0'))
    patient_count = int(os.getenv('PATIENT_COUNT', '10'))
    scenario = os.getenv('SCENARIO', 'home_monitoring')
    duration = int(os.getenv('SIM_DURATION', '3600'))
    
    logger.info(f"Starting gateway: {gateway_id}")
    logger.info(f"Patients: {patient_start} to {patient_start + patient_count - 1}")
    logger.info(f"Scenario: {scenario}")
    
    # Load keys
    keys = load_or_generate_keys()
    
    # Create configs
    broker_config = BrokerConfig(
        host=os.getenv('BROKER_HOST', 'localhost'),
        port=int(os.getenv('BROKER_PORT', '1883'))
    )
    
    privacy_config = PrivacyConfig(
        topic_key=keys.topic_key,
        clientid_key=keys.clientid_key,
        epoch_length_seconds=int(os.getenv('EPOCH_LENGTH', '1800')),
        overlap_time_seconds=int(os.getenv('OVERLAP_TIME', '60')),
        rotation_trigger=os.getenv('ROTATION_TRIGGER', 'time'),
        rotate_client_id=os.getenv('ROTATE_CLIENT_ID', 'true').lower() == 'true'
    )
    
    # Get patients and sensors
    patient_ids = get_patient_ids(patient_start, patient_count)
    sensor_types = get_sensor_types(scenario)
    
    logger.info(f"Sensors per patient: {sensor_types}")
    
    # Run gateway
    stats = await run_gateway(
        gateway_id=gateway_id,
        patient_ids=patient_ids,
        sensor_types=sensor_types,
        keys=keys,
        broker_config=broker_config,
        privacy_config=privacy_config,
        duration_seconds=duration
    )
    
    # Save results
    results_file = f'/data/results/{gateway_id}_results.json'
    os.makedirs(os.path.dirname(results_file), exist_ok=True)
    with open(results_file, 'w') as f:
        json.dump(stats, f, indent=2)
    
    logger.info(f"Results saved to {results_file}")


if __name__ == "__main__":
    asyncio.run(main())
