"""
Medical Sensor Simulator
========================
Simulator beban trafik medis sesuai skenario klinis di BAB 3 Metodologi
Mendukung berbagai jenis sensor: ECG, SpO2, tekanan darah, temperature, activity, alarm
"""

import asyncio
import json
import logging
import random
import time
import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Generator
from enum import Enum
import math

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SensorType(Enum):
    ECG = "ecg"
    SPO2 = "spo2"
    BLOOD_PRESSURE = "blood_pressure"
    TEMPERATURE = "temperature"
    ACTIVITY = "activity"
    ALARM = "alarm"


@dataclass
class SensorSpec:
    """Spesifikasi sensor sesuai metodologi"""
    sensor_type: SensorType
    message_interval_ms: int  # 0 untuk event-driven
    payload_size_bytes: int
    qos: int
    description: str


# Spesifikasi sensor sesuai BAB 3.3.1
SENSOR_SPECS = {
    SensorType.ECG: SensorSpec(
        sensor_type=SensorType.ECG,
        message_interval_ms=100,  # 10 Hz, 1 pesan per 100ms
        payload_size_bytes=256,   # Raw ECG samples
        qos=1,
        description="Electrocardiogram sensor - high frequency monitoring"
    ),
    SensorType.SPO2: SensorSpec(
        sensor_type=SensorType.SPO2,
        message_interval_ms=1000,  # 1 Hz, 1-2 pesan per detik
        payload_size_bytes=32,
        qos=1,
        description="Pulse oximetry sensor"
    ),
    SensorType.BLOOD_PRESSURE: SensorSpec(
        sensor_type=SensorType.BLOOD_PRESSURE,
        message_interval_ms=600000,  # 1 pesan per 10 menit
        payload_size_bytes=64,
        qos=1,
        description="Blood pressure monitor"
    ),
    SensorType.TEMPERATURE: SensorSpec(
        sensor_type=SensorType.TEMPERATURE,
        message_interval_ms=60000,  # 1 pesan per menit
        payload_size_bytes=16,
        qos=0,
        description="Body temperature sensor"
    ),
    SensorType.ACTIVITY: SensorSpec(
        sensor_type=SensorType.ACTIVITY,
        message_interval_ms=5000,  # setiap 5 detik
        payload_size_bytes=48,
        qos=0,
        description="Activity/accelerometer sensor"
    ),
    SensorType.ALARM: SensorSpec(
        sensor_type=SensorType.ALARM,
        message_interval_ms=0,  # Event-driven
        payload_size_bytes=128,
        qos=2,  # Highest priority
        description="Clinical alarm - event triggered"
    )
}


@dataclass
class ECGReading:
    """ECG data reading"""
    timestamp: float
    lead_values: List[float]  # Multi-lead ECG
    heart_rate: int
    rhythm: str = "normal_sinus"
    
    def to_bytes(self) -> bytes:
        """Serialize ke bytes"""
        data = {
            "ts": self.timestamp,
            "leads": self.lead_values[:12],  # Up to 12 leads
            "hr": self.heart_rate,
            "rhythm": self.rhythm
        }
        return json.dumps(data).encode('utf-8')


@dataclass
class SpO2Reading:
    """SpO2 data reading"""
    timestamp: float
    spo2_percent: float
    pulse_rate: int
    perfusion_index: float = 0.0
    
    def to_bytes(self) -> bytes:
        return json.dumps({
            "ts": self.timestamp,
            "spo2": self.spo2_percent,
            "pr": self.pulse_rate,
            "pi": self.perfusion_index
        }).encode('utf-8')


@dataclass
class BloodPressureReading:
    """Blood pressure reading"""
    timestamp: float
    systolic: int
    diastolic: int
    mean_arterial: int
    pulse: int
    
    def to_bytes(self) -> bytes:
        return json.dumps({
            "ts": self.timestamp,
            "sys": self.systolic,
            "dia": self.diastolic,
            "map": self.mean_arterial,
            "pulse": self.pulse
        }).encode('utf-8')


@dataclass
class TemperatureReading:
    """Temperature reading"""
    timestamp: float
    temperature_celsius: float
    location: str = "forehead"
    
    def to_bytes(self) -> bytes:
        return json.dumps({
            "ts": self.timestamp,
            "temp": self.temperature_celsius,
            "loc": self.location
        }).encode('utf-8')


@dataclass
class ActivityReading:
    """Activity/accelerometer reading"""
    timestamp: float
    steps: int
    activity_level: str  # "sedentary", "light", "moderate", "vigorous"
    accel_x: float
    accel_y: float
    accel_z: float
    
    def to_bytes(self) -> bytes:
        return json.dumps({
            "ts": self.timestamp,
            "steps": self.steps,
            "level": self.activity_level,
            "ax": self.accel_x,
            "ay": self.accel_y,
            "az": self.accel_z
        }).encode('utf-8')


@dataclass
class AlarmEvent:
    """Clinical alarm event"""
    timestamp: float
    alarm_type: str  # "critical", "warning", "advisory"
    parameter: str   # "spo2", "hr", "bp", etc.
    value: float
    threshold: float
    message: str
    
    def to_bytes(self) -> bytes:
        return json.dumps({
            "ts": self.timestamp,
            "type": self.alarm_type,
            "param": self.parameter,
            "value": self.value,
            "thresh": self.threshold,
            "msg": self.message
        }).encode('utf-8')


class PatientPhysiologyModel:
    """
    Model fisiologi pasien untuk menghasilkan data medis yang realistis
    Termasuk variabilitas normal dan kondisi abnormal
    """
    
    def __init__(self, patient_id: str, condition: str = "normal"):
        self.patient_id = patient_id
        self.condition = condition
        
        # Baseline vital signs
        self.baseline_hr = random.randint(60, 80)
        self.baseline_spo2 = random.uniform(96, 99)
        self.baseline_systolic = random.randint(110, 130)
        self.baseline_diastolic = random.randint(70, 85)
        self.baseline_temp = random.uniform(36.5, 37.2)
        
        # Variability parameters
        self.hr_variability = 5
        self.spo2_variability = 1.5
        self.bp_variability = 5
        
        # Time-based variation (circadian rhythm simulation)
        self.start_time = time.time()
        
        # Alarm thresholds
        self.alarm_thresholds = {
            "spo2_low": 90,
            "hr_high": 120,
            "hr_low": 50,
            "systolic_high": 180,
            "systolic_low": 90,
            "temp_high": 38.5
        }
        
        # Alarm probability (per check)
        self.alarm_probability = 0.001 if condition == "normal" else 0.01
    
    def get_time_factor(self) -> float:
        """Get circadian rhythm factor"""
        elapsed = time.time() - self.start_time
        hour_angle = (elapsed / 3600) * (2 * math.pi / 24)
        return math.sin(hour_angle) * 0.1  # ±10% variation
    
    def generate_ecg(self) -> ECGReading:
        """Generate ECG reading"""
        time_factor = self.get_time_factor()
        hr = int(self.baseline_hr + random.gauss(0, self.hr_variability) + time_factor * 10)
        hr = max(40, min(200, hr))  # Clamp to valid range
        
        # Generate synthetic ECG lead values (simplified)
        leads = []
        for _ in range(12):
            # Simulate ECG waveform amplitude
            leads.append(random.gauss(0, 0.5))
        
        rhythm = "normal_sinus"
        if hr > 100:
            rhythm = "sinus_tachycardia"
        elif hr < 60:
            rhythm = "sinus_bradycardia"
        
        return ECGReading(
            timestamp=time.time(),
            lead_values=leads,
            heart_rate=hr,
            rhythm=rhythm
        )
    
    def generate_spo2(self) -> SpO2Reading:
        """Generate SpO2 reading"""
        spo2 = self.baseline_spo2 + random.gauss(0, self.spo2_variability)
        spo2 = max(70, min(100, spo2))  # Clamp
        
        pulse = int(self.baseline_hr + random.gauss(0, 3))
        pi = random.uniform(0.5, 5.0)  # Perfusion index
        
        return SpO2Reading(
            timestamp=time.time(),
            spo2_percent=round(spo2, 1),
            pulse_rate=pulse,
            perfusion_index=round(pi, 2)
        )
    
    def generate_blood_pressure(self) -> BloodPressureReading:
        """Generate blood pressure reading"""
        time_factor = self.get_time_factor()
        
        systolic = int(self.baseline_systolic + random.gauss(0, self.bp_variability) + time_factor * 10)
        diastolic = int(self.baseline_diastolic + random.gauss(0, self.bp_variability * 0.7))
        
        # Ensure physiological relationship
        if diastolic >= systolic - 20:
            diastolic = systolic - 30
        
        map_value = int(diastolic + (systolic - diastolic) / 3)
        pulse = int(self.baseline_hr + random.gauss(0, 3))
        
        return BloodPressureReading(
            timestamp=time.time(),
            systolic=systolic,
            diastolic=diastolic,
            mean_arterial=map_value,
            pulse=pulse
        )
    
    def generate_temperature(self) -> TemperatureReading:
        """Generate temperature reading"""
        temp = self.baseline_temp + random.gauss(0, 0.2)
        temp = max(35.0, min(42.0, temp))
        
        return TemperatureReading(
            timestamp=time.time(),
            temperature_celsius=round(temp, 1)
        )
    
    def generate_activity(self) -> ActivityReading:
        """Generate activity reading"""
        # Simulate activity patterns
        activity_levels = ["sedentary", "light", "moderate", "vigorous"]
        weights = [0.6, 0.25, 0.1, 0.05]  # Most time sedentary
        
        level = random.choices(activity_levels, weights=weights)[0]
        
        # Steps based on activity level
        step_rates = {"sedentary": 0, "light": 30, "moderate": 80, "vigorous": 150}
        steps = int(step_rates[level] * random.uniform(0.8, 1.2))
        
        return ActivityReading(
            timestamp=time.time(),
            steps=steps,
            activity_level=level,
            accel_x=random.gauss(0, 0.5),
            accel_y=random.gauss(0, 0.5),
            accel_z=random.gauss(9.8, 0.5)  # Gravity
        )
    
    def check_alarm_conditions(self) -> Optional[AlarmEvent]:
        """Check if alarm should be triggered"""
        # Random chance of alarm
        if random.random() > self.alarm_probability:
            return None
        
        # Generate specific alarm
        alarm_types = [
            ("spo2_low", "spo2", self.baseline_spo2 - 10, self.alarm_thresholds["spo2_low"]),
            ("hr_high", "heart_rate", self.baseline_hr + 50, self.alarm_thresholds["hr_high"]),
            ("hr_low", "heart_rate", self.baseline_hr - 20, self.alarm_thresholds["hr_low"]),
            ("bp_high", "systolic", self.baseline_systolic + 60, self.alarm_thresholds["systolic_high"]),
        ]
        
        alarm_type, param, value, threshold = random.choice(alarm_types)
        
        severity = "critical" if "low" in alarm_type or value > threshold * 1.2 else "warning"
        
        return AlarmEvent(
            timestamp=time.time(),
            alarm_type=severity,
            parameter=param,
            value=value,
            threshold=threshold,
            message=f"ALARM: {param} = {value} (threshold: {threshold})"
        )


class SensorSimulator:
    """
    Simulator untuk satu sensor
    Menghasilkan data sesuai interval dan spec
    """
    
    def __init__(
        self,
        patient_id: str,
        sensor_type: SensorType,
        physiology: PatientPhysiologyModel,
        publish_callback: Callable[[str, str, bytes, int], None]
    ):
        self.patient_id = patient_id
        self.sensor_type = sensor_type
        self.physiology = physiology
        self.publish_callback = publish_callback
        self.spec = SENSOR_SPECS[sensor_type]
        
        self.running = False
        self.message_count = 0
        self.last_message_time = 0
    
    def _generate_reading(self) -> bytes:
        """Generate reading berdasarkan sensor type"""
        if self.sensor_type == SensorType.ECG:
            return self.physiology.generate_ecg().to_bytes()
        elif self.sensor_type == SensorType.SPO2:
            return self.physiology.generate_spo2().to_bytes()
        elif self.sensor_type == SensorType.BLOOD_PRESSURE:
            return self.physiology.generate_blood_pressure().to_bytes()
        elif self.sensor_type == SensorType.TEMPERATURE:
            return self.physiology.generate_temperature().to_bytes()
        elif self.sensor_type == SensorType.ACTIVITY:
            return self.physiology.generate_activity().to_bytes()
        elif self.sensor_type == SensorType.ALARM:
            alarm = self.physiology.check_alarm_conditions()
            if alarm:
                return alarm.to_bytes()
            return None
        
        return b""
    
    async def run(self):
        """Run sensor simulation loop"""
        self.running = True
        interval_sec = self.spec.message_interval_ms / 1000.0
        
        logger.debug(f"Starting sensor {self.patient_id}/{self.sensor_type.value}, interval={interval_sec}s")
        
        while self.running:
            # Generate and publish reading
            payload = self._generate_reading()
            
            if payload:
                self.publish_callback(
                    self.patient_id,
                    self.sensor_type.value,
                    payload,
                    self.spec.qos
                )
                self.message_count += 1
                self.last_message_time = time.time()
            
            # Wait for next interval
            if interval_sec > 0:
                await asyncio.sleep(interval_sec)
            else:
                # Event-driven (alarm) - check periodically
                await asyncio.sleep(1.0)
    
    def stop(self):
        """Stop simulator"""
        self.running = False


class PatientSensorSuite:
    """
    Suite of sensors untuk satu pasien
    Mengelola multiple sensor simulators
    """
    
    def __init__(
        self,
        patient_id: str,
        sensor_types: List[SensorType],
        publish_callback: Callable[[str, str, bytes, int], None],
        condition: str = "normal"
    ):
        self.patient_id = patient_id
        self.physiology = PatientPhysiologyModel(patient_id, condition)
        
        self.simulators: Dict[SensorType, SensorSimulator] = {}
        for sensor_type in sensor_types:
            self.simulators[sensor_type] = SensorSimulator(
                patient_id, sensor_type, self.physiology, publish_callback
            )
        
        self.tasks: List[asyncio.Task] = []
    
    async def start(self):
        """Start all sensors"""
        for sim in self.simulators.values():
            task = asyncio.create_task(sim.run())
            self.tasks.append(task)
        
        logger.info(f"Started {len(self.simulators)} sensors for patient {self.patient_id}")
    
    async def stop(self):
        """Stop all sensors"""
        for sim in self.simulators.values():
            sim.stop()
        
        for task in self.tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        self.tasks.clear()
    
    def get_stats(self) -> dict:
        """Get statistics for all sensors"""
        return {
            self.patient_id: {
                sensor_type.value: {
                    "message_count": sim.message_count,
                    "last_message": sim.last_message_time
                }
                for sensor_type, sim in self.simulators.items()
            }
        }


class MultiPatientSimulator:
    """
    Simulator untuk multiple patients
    Digunakan di dalam gateway container
    """
    
    def __init__(
        self,
        patient_ids: List[str],
        sensor_types: List[str],
        publish_callback: Callable[[str, str, bytes, int], None]
    ):
        self.patient_ids = patient_ids
        self.sensor_type_enums = [SensorType(s) for s in sensor_types]
        self.publish_callback = publish_callback
        
        self.patient_suites: Dict[str, PatientSensorSuite] = {}
        
        # Create patient suites
        for pid in patient_ids:
            condition = random.choice(["normal"] * 9 + ["abnormal"])  # 10% abnormal
            self.patient_suites[pid] = PatientSensorSuite(
                pid, self.sensor_type_enums, publish_callback, condition
            )
        
        self.running = False
        self.start_time = 0
        self.total_messages = 0
    
    async def start(self):
        """Start simulation for all patients"""
        self.running = True
        self.start_time = time.time()
        
        logger.info(f"Starting simulation for {len(self.patient_ids)} patients")
        
        for suite in self.patient_suites.values():
            await suite.start()
    
    async def stop(self):
        """Stop all simulations"""
        self.running = False
        
        for suite in self.patient_suites.values():
            await suite.stop()
        
        logger.info("All patient simulations stopped")
    
    def get_stats(self) -> dict:
        """Get comprehensive statistics"""
        stats_by_patient = {}
        total_msgs = 0
        
        for pid, suite in self.patient_suites.items():
            patient_stats = suite.get_stats()[pid]
            stats_by_patient[pid] = patient_stats
            total_msgs += sum(s["message_count"] for s in patient_stats.values())
        
        elapsed = time.time() - self.start_time if self.start_time else 0
        
        return {
            "total_patients": len(self.patient_ids),
            "total_messages": total_msgs,
            "elapsed_seconds": elapsed,
            "messages_per_second": total_msgs / elapsed if elapsed > 0 else 0,
            "patients": stats_by_patient
        }


# Convenience function untuk testing
async def run_simulation_test(
    num_patients: int = 5,
    sensor_types: List[str] = None,
    duration_seconds: int = 30
):
    """Run a test simulation"""
    if sensor_types is None:
        sensor_types = ["spo2", "blood_pressure", "temperature"]
    
    messages = []
    
    def callback(pid: str, sid: str, payload: bytes, qos: int):
        messages.append({
            "pid": pid,
            "sid": sid,
            "payload_size": len(payload),
            "qos": qos,
            "timestamp": time.time()
        })
    
    patient_ids = [f"patient_{i:03d}" for i in range(num_patients)]
    simulator = MultiPatientSimulator(patient_ids, sensor_types, callback)
    
    await simulator.start()
    await asyncio.sleep(duration_seconds)
    await simulator.stop()
    
    stats = simulator.get_stats()
    print(f"\nSimulation Results:")
    print(f"  Total patients: {stats['total_patients']}")
    print(f"  Total messages: {stats['total_messages']}")
    print(f"  Messages/sec: {stats['messages_per_second']:.2f}")
    print(f"  Duration: {stats['elapsed_seconds']:.1f}s")
    
    return stats, messages


if __name__ == "__main__":
    # Test simulation
    asyncio.run(run_simulation_test(
        num_patients=3,
        sensor_types=["ecg", "spo2", "blood_pressure"],
        duration_seconds=10
    ))
