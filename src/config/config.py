"""
Configuration for Privacy-Aware MQTT IoMT Experiment
=====================================================
Konfigurasi parameter eksperimen sesuai BAB 3 Metodologi
"""

import os
from dataclasses import dataclass, field
from typing import List, Dict
from enum import Enum

class ExperimentMode(Enum):
    BASELINE = "baseline"  # MQTT standar + TLS + enkripsi payload
    NAMESPACE_PRIVACY = "namespace_privacy"  # TPM, rotasi pseudo-topic, pooling ClientID
    NAMESPACE_PRIVACY_OVERLAY = "namespace_privacy_overlay"  # + overlay broker anonim

@dataclass
class BrokerConfig:
    """Konfigurasi MQTT Broker"""
    host: str = os.getenv("BROKER_HOST", "localhost")
    port: int = int(os.getenv("BROKER_PORT", "1883"))
    tls_enabled: bool = os.getenv("BROKER_TLS", "false").lower() == "true"
    username: str = os.getenv("BROKER_USER", "")
    password: str = os.getenv("BROKER_PASS", "")

@dataclass
class PrivacyConfig:
    """Konfigurasi Privacy Manager (TPM)"""
    # Kunci untuk PRF (Pseudorandom Function)
    topic_key: bytes = field(default_factory=lambda: os.urandom(32))
    clientid_key: bytes = field(default_factory=lambda: os.urandom(32))
    
    # Parameter rotasi epoch
    epoch_length_seconds: int = int(os.getenv("EPOCH_LENGTH", "1800"))  # 30 menit default
    epoch_length_messages: int = int(os.getenv("EPOCH_MSGS", "10000"))  # atau 10k pesan
    rotation_trigger: str = os.getenv("ROTATION_TRIGGER", "time")  # "time" atau "messages"
    
    # Parameter overlap untuk mencegah kehilangan pesan
    overlap_time_seconds: int = int(os.getenv("OVERLAP_TIME", "60"))  # 1 menit overlap
    overlap_messages: int = int(os.getenv("OVERLAP_MSGS", "100"))
    
    # Rotasi ClientID
    rotate_client_id: bool = os.getenv("ROTATE_CLIENT_ID", "true").lower() == "true"
    client_id_rotation_interval: int = int(os.getenv("CLIENTID_ROTATION", "3600"))  # 1 jam

@dataclass 
class SensorProfile:
    """Profil sensor medis"""
    sensor_type: str
    message_interval_ms: int  # interval antar pesan dalam milliseconds
    payload_size_bytes: int
    qos: int = 1

# Profil sensor sesuai skenario klinis di metodologi
SENSOR_PROFILES = {
    "ecg": SensorProfile("ecg", 100, 256, qos=1),  # 10 Hz, data ECG
    "spo2": SensorProfile("spo2", 1000, 32, qos=1),  # 1 Hz
    "blood_pressure": SensorProfile("blood_pressure", 600000, 64, qos=1),  # setiap 10 menit
    "temperature": SensorProfile("temperature", 60000, 16, qos=0),  # setiap 1 menit
    "activity": SensorProfile("activity", 5000, 48, qos=0),  # setiap 5 detik
    "alarm": SensorProfile("alarm", 0, 128, qos=2),  # event-driven, prioritas tinggi
}

@dataclass
class PatientConfig:
    """Konfigurasi per pasien"""
    patient_id: str
    sensors: List[str] = field(default_factory=lambda: ["spo2", "blood_pressure", "temperature"])

@dataclass
class ExperimentConfig:
    """Konfigurasi eksperimen utama"""
    mode: ExperimentMode = ExperimentMode.NAMESPACE_PRIVACY
    
    # Skala eksperimen
    num_patients: int = int(os.getenv("NUM_PATIENTS", "100"))
    num_gateways: int = int(os.getenv("NUM_GATEWAYS", "10"))
    patients_per_gateway: int = 10  # akan dihitung otomatis
    
    # Durasi eksperimen
    simulation_duration_seconds: int = int(os.getenv("SIM_DURATION", "3600"))  # 1 jam
    
    # Skenario klinis
    scenario: str = os.getenv("SCENARIO", "home_monitoring")  # atau "icu_monitoring"
    
    # Konfigurasi komponen
    broker: BrokerConfig = field(default_factory=BrokerConfig)
    privacy: PrivacyConfig = field(default_factory=PrivacyConfig)
    
    # Logging dan metrics
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    metrics_interval_seconds: int = int(os.getenv("METRICS_INTERVAL", "10"))
    output_dir: str = os.getenv("OUTPUT_DIR", "/data/results")
    
    def __post_init__(self):
        self.patients_per_gateway = self.num_patients // self.num_gateways
        if self.num_patients % self.num_gateways != 0:
            self.patients_per_gateway += 1

# Skenario eksperimen sesuai metodologi
EXPERIMENT_SCENARIOS = {
    "home_monitoring": {
        "description": "Monitoring rumah untuk pasien kronis",
        "num_patients_range": (10, 1000),
        "sensors_per_patient": ["spo2", "blood_pressure", "activity"],
        "typical_message_rate": "low-medium"
    },
    "icu_monitoring": {
        "description": "Monitoring ruangan perawatan intensif",
        "num_patients_range": (10, 100),
        "sensors_per_patient": ["ecg", "spo2", "blood_pressure", "temperature"],
        "typical_message_rate": "high"
    }
}

# Parameter untuk variasi eksperimen
EPOCH_VARIATIONS = [300, 1800, 7200, 86400]  # 5 menit, 30 menit, 2 jam, 24 jam
PATIENT_SCALE_VARIATIONS = [10, 100, 1000, 10000]
