"""
Experiment Runner
=================
Script utama untuk menjalankan eksperimen sesuai BAB 3 Metodologi:
- Baseline: MQTT standar + TLS + enkripsi payload
- Namespace-Privacy: TPM, rotasi pseudo-topic, pooling ClientID
- (Optional) Namespace-Privacy + Overlay Anonim
"""

import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.crypto import KeyMaterial, gen_pseudo_topic, encrypt_payload
from src.config import (
    ExperimentConfig, BrokerConfig, PrivacyConfig, 
    ExperimentMode, SENSOR_PROFILES, EXPERIMENT_SCENARIOS
)
from src.simulator import MultiPatientSimulator, SensorType
from src.metrics import MetricsCollector, MetricsComparator, ExperimentMetrics

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class ExperimentResult:
    """Hasil eksperimen"""
    experiment_id: str
    config_name: str
    metrics: ExperimentMetrics
    raw_data: dict
    duration_seconds: float


class BaselineExperiment:
    """
    Eksperimen Baseline: MQTT standar + TLS + enkripsi payload
    Topic dan ClientID STABIL (tidak dirotasi)
    """
    
    def __init__(
        self,
        experiment_id: str,
        num_patients: int,
        sensor_types: List[str],
        duration_seconds: int,
        keys: KeyMaterial
    ):
        self.experiment_id = experiment_id
        self.num_patients = num_patients
        self.sensor_types = sensor_types
        self.duration_seconds = duration_seconds
        self.keys = keys
        
        # Generate patient IDs
        self.patient_ids = [f"patient_{i:05d}" for i in range(num_patients)]
        
        # Static topic mapping (baseline - tidak dirotasi)
        self.topic_mapping: Dict[tuple, str] = {}
        for pid in self.patient_ids:
            for sid in sensor_types:
                # Baseline: topic semantik yang stabil
                topic = f"hospital/ward1/{pid}/{sid}"
                self.topic_mapping[(pid, sid)] = topic
        
        # Static ClientID (satu per gateway/simulasi)
        self.client_id = f"gateway_baseline_{experiment_id}"
        
        # Metrics collector
        self.metrics = MetricsCollector(experiment_id, "baseline")
        
        # Message counter
        self.message_count = 0
    
    def _publish_callback(self, pid: str, sid: str, payload: bytes, qos: int):
        """Callback untuk setiap pesan yang dipublish"""
        start_time = time.time()
        
        # Get stable topic
        topic = self.topic_mapping[(pid, sid)]
        
        # Encrypt payload (baseline juga encrypt payload)
        encrypted = encrypt_payload(self.keys.control_encrypt_key, payload)
        
        computation_time = time.time() - start_time
        
        # Record metrics
        self.metrics.record_message_sent(
            patient_id=pid,
            sensor_id=sid,
            topic=topic,
            client_id=self.client_id,
            payload_size=len(encrypted),
            computation_time=computation_time,
            is_alarm=(sid == "alarm"),
            is_duplicate=False,
            epoch=0  # Baseline: always epoch 0
        )
        
        # Record baseline message size (original payload + encryption overhead)
        self.metrics.record_baseline_message_size(len(encrypted))
        
        # Simulate message received (dalam simulasi, asumsi selalu diterima)
        latency = computation_time * 1000 + 5  # Add simulated network latency
        self.metrics.record_message_received(
            latency_ms=latency,
            is_alarm=(sid == "alarm")
        )
        
        self.message_count += 1
    
    async def run(self) -> ExperimentResult:
        """Jalankan eksperimen baseline"""
        logger.info(f"Starting BASELINE experiment: {self.experiment_id}")
        logger.info(f"  Patients: {self.num_patients}")
        logger.info(f"  Sensors: {self.sensor_types}")
        logger.info(f"  Duration: {self.duration_seconds}s")
        
        start_time = time.time()
        
        # Create simulator
        simulator = MultiPatientSimulator(
            patient_ids=self.patient_ids,
            sensor_types=self.sensor_types,
            publish_callback=self._publish_callback
        )
        
        # Run simulation
        await simulator.start()
        await asyncio.sleep(self.duration_seconds)
        await simulator.stop()
        
        duration = time.time() - start_time
        
        # Collect metrics
        metrics = self.metrics.collect_all_metrics()
        
        logger.info(f"BASELINE experiment completed: {self.message_count} messages in {duration:.1f}s")
        
        return ExperimentResult(
            experiment_id=self.experiment_id,
            config_name="baseline",
            metrics=metrics,
            raw_data=simulator.get_stats(),
            duration_seconds=duration
        )


class NamespacePrivacyExperiment:
    """
    Eksperimen Namespace-Privacy: TPM, rotasi pseudo-topic, pooling/rotasi ClientID
    """
    
    def __init__(
        self,
        experiment_id: str,
        num_patients: int,
        sensor_types: List[str],
        duration_seconds: int,
        keys: KeyMaterial,
        epoch_length_seconds: int = 1800,  # 30 menit default
        overlap_time_seconds: int = 60
    ):
        self.experiment_id = experiment_id
        self.num_patients = num_patients
        self.sensor_types = sensor_types
        self.duration_seconds = duration_seconds
        self.keys = keys
        self.epoch_length_seconds = epoch_length_seconds
        self.overlap_time_seconds = overlap_time_seconds
        
        # Generate patient IDs
        self.patient_ids = [f"patient_{i:05d}" for i in range(num_patients)]
        
        # Dynamic pseudo-topic mapping
        self.current_epoch: Dict[tuple, int] = {}
        self.epoch_start_time: Dict[tuple, float] = {}
        self.current_topic: Dict[tuple, str] = {}
        self.previous_topic: Dict[tuple, Optional[str]] = {}
        self.overlap_active: Dict[tuple, bool] = {}
        
        # Initialize mappings
        for pid in self.patient_ids:
            for sid in sensor_types:
                key = (pid, sid)
                self.current_epoch[key] = 0
                self.epoch_start_time[key] = time.time()
                self.current_topic[key] = gen_pseudo_topic(keys.topic_key, pid, sid, 0)
                self.previous_topic[key] = None
                self.overlap_active[key] = False
        
        # Dynamic ClientID
        self.client_epoch = 0
        self.client_id = self._generate_client_id(0)
        self.client_epoch_start = time.time()
        self.client_rotation_interval = 3600  # 1 jam
        
        # Metrics collector
        self.metrics = MetricsCollector(experiment_id, "namespace_privacy")
        
        # Message counter
        self.message_count = 0
    
    def _generate_client_id(self, epoch: int) -> str:
        """Generate pseudo ClientID"""
        from src.crypto import gen_pseudo_client_id
        return gen_pseudo_client_id(self.keys.clientid_key, f"gw_{self.experiment_id}", epoch)
    
    def _check_and_rotate_topic(self, pid: str, sid: str):
        """Check dan lakukan rotasi topic jika diperlukan"""
        key = (pid, sid)
        elapsed = time.time() - self.epoch_start_time[key]
        
        if elapsed >= self.epoch_length_seconds:
            # Rotasi epoch
            new_epoch = self.current_epoch[key] + 1
            new_topic = gen_pseudo_topic(self.keys.topic_key, pid, sid, new_epoch)
            
            # Simpan topic lama untuk overlap
            self.previous_topic[key] = self.current_topic[key]
            self.current_topic[key] = new_topic
            self.current_epoch[key] = new_epoch
            self.epoch_start_time[key] = time.time()
            self.overlap_active[key] = True
            
            logger.debug(f"Rotated topic for {pid}/{sid} to epoch {new_epoch}")
    
    def _check_and_end_overlap(self, pid: str, sid: str):
        """Check dan akhiri overlap jika waktunya"""
        key = (pid, sid)
        if self.overlap_active[key]:
            overlap_elapsed = time.time() - self.epoch_start_time[key]
            if overlap_elapsed >= self.overlap_time_seconds:
                self.previous_topic[key] = None
                self.overlap_active[key] = False
                logger.debug(f"Ended overlap for {pid}/{sid}")
    
    def _check_and_rotate_client_id(self):
        """Check dan rotasi ClientID"""
        elapsed = time.time() - self.client_epoch_start
        if elapsed >= self.client_rotation_interval:
            self.client_epoch += 1
            self.client_id = self._generate_client_id(self.client_epoch)
            self.client_epoch_start = time.time()
            logger.debug(f"Rotated ClientID to epoch {self.client_epoch}")
    
    def _publish_callback(self, pid: str, sid: str, payload: bytes, qos: int):
        """Callback untuk setiap pesan yang dipublish"""
        start_time = time.time()
        key = (pid, sid)
        
        # Check rotasi topic
        self._check_and_rotate_topic(pid, sid)
        self._check_and_end_overlap(pid, sid)
        self._check_and_rotate_client_id()
        
        # Encrypt payload
        encrypted = encrypt_payload(self.keys.control_encrypt_key, payload)
        
        computation_time = time.time() - start_time
        
        # Publish ke topic current
        self.metrics.record_message_sent(
            patient_id=pid,
            sensor_id=sid,
            topic=self.current_topic[key],
            client_id=self.client_id,
            payload_size=len(encrypted),
            computation_time=computation_time,
            is_alarm=(sid == "alarm"),
            is_duplicate=False,
            epoch=self.current_epoch[key]
        )
        
        # Jika overlap aktif, publish juga ke topic lama
        if self.overlap_active[key] and self.previous_topic[key]:
            self.metrics.record_message_sent(
                patient_id=pid,
                sensor_id=sid,
                topic=self.previous_topic[key],
                client_id=self.client_id,
                payload_size=len(encrypted),
                computation_time=computation_time,
                is_alarm=(sid == "alarm"),
                is_duplicate=True,
                epoch=self.current_epoch[key] - 1
            )
        
        # Record baseline size untuk perbandingan overhead
        baseline_size = len(payload) + 28  # Simulated encryption overhead only
        self.metrics.record_baseline_message_size(baseline_size)
        
        # Simulate message received
        latency = computation_time * 1000 + 5
        self.metrics.record_message_received(
            latency_ms=latency,
            is_alarm=(sid == "alarm")
        )
        
        self.message_count += 1
    
    async def run(self) -> ExperimentResult:
        """Jalankan eksperimen namespace-privacy"""
        logger.info(f"Starting NAMESPACE-PRIVACY experiment: {self.experiment_id}")
        logger.info(f"  Patients: {self.num_patients}")
        logger.info(f"  Sensors: {self.sensor_types}")
        logger.info(f"  Duration: {self.duration_seconds}s")
        logger.info(f"  Epoch length: {self.epoch_length_seconds}s")
        logger.info(f"  Overlap time: {self.overlap_time_seconds}s")
        
        start_time = time.time()
        
        # Create simulator
        simulator = MultiPatientSimulator(
            patient_ids=self.patient_ids,
            sensor_types=self.sensor_types,
            publish_callback=self._publish_callback
        )
        
        # Run simulation
        await simulator.start()
        await asyncio.sleep(self.duration_seconds)
        await simulator.stop()
        
        duration = time.time() - start_time
        
        # Collect metrics
        metrics = self.metrics.collect_all_metrics()
        
        logger.info(f"NAMESPACE-PRIVACY experiment completed: {self.message_count} messages in {duration:.1f}s")
        
        return ExperimentResult(
            experiment_id=self.experiment_id,
            config_name="namespace_privacy",
            metrics=metrics,
            raw_data=simulator.get_stats(),
            duration_seconds=duration
        )


class ExperimentRunner:
    """
    Runner utama untuk menjalankan dan membandingkan eksperimen
    """
    
    def __init__(self, output_dir: str = "./results"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        self.keys = KeyMaterial.generate()
        self.results: List[ExperimentResult] = []
        self.comparator = MetricsComparator()
    
    async def run_baseline(
        self,
        num_patients: int = 10,
        sensor_types: List[str] = None,
        duration_seconds: int = 60
    ) -> ExperimentResult:
        """Jalankan eksperimen baseline"""
        if sensor_types is None:
            sensor_types = ["spo2", "blood_pressure", "temperature"]
        
        experiment_id = f"baseline_{int(time.time())}"
        
        experiment = BaselineExperiment(
            experiment_id=experiment_id,
            num_patients=num_patients,
            sensor_types=sensor_types,
            duration_seconds=duration_seconds,
            keys=self.keys
        )
        
        result = await experiment.run()
        self.results.append(result)
        self.comparator.add_experiment(result.metrics)
        
        # Save result
        result_file = os.path.join(self.output_dir, f"{experiment_id}_results.json")
        with open(result_file, 'w') as f:
            json.dump(result.metrics.to_dict(), f, indent=2)
        
        return result
    
    async def run_namespace_privacy(
        self,
        num_patients: int = 10,
        sensor_types: List[str] = None,
        duration_seconds: int = 60,
        epoch_length_seconds: int = 30,  # Shorter for testing
        overlap_time_seconds: int = 5
    ) -> ExperimentResult:
        """Jalankan eksperimen namespace-privacy"""
        if sensor_types is None:
            sensor_types = ["spo2", "blood_pressure", "temperature"]
        
        experiment_id = f"namespace_privacy_{int(time.time())}"
        
        experiment = NamespacePrivacyExperiment(
            experiment_id=experiment_id,
            num_patients=num_patients,
            sensor_types=sensor_types,
            duration_seconds=duration_seconds,
            keys=self.keys,
            epoch_length_seconds=epoch_length_seconds,
            overlap_time_seconds=overlap_time_seconds
        )
        
        result = await experiment.run()
        self.results.append(result)
        self.comparator.add_experiment(result.metrics)
        
        # Save result
        result_file = os.path.join(self.output_dir, f"{experiment_id}_results.json")
        with open(result_file, 'w') as f:
            json.dump(result.metrics.to_dict(), f, indent=2)
        
        return result
    
    async def run_comparison(
        self,
        num_patients: int = 10,
        sensor_types: List[str] = None,
        duration_seconds: int = 60
    ):
        """Jalankan perbandingan baseline vs namespace-privacy"""
        logger.info("=" * 60)
        logger.info("STARTING EXPERIMENT COMPARISON")
        logger.info("=" * 60)
        
        # Run baseline
        logger.info("\n--- Running Baseline Experiment ---")
        baseline_result = await self.run_baseline(
            num_patients=num_patients,
            sensor_types=sensor_types,
            duration_seconds=duration_seconds
        )
        
        # Run namespace-privacy
        logger.info("\n--- Running Namespace-Privacy Experiment ---")
        privacy_result = await self.run_namespace_privacy(
            num_patients=num_patients,
            sensor_types=sensor_types,
            duration_seconds=duration_seconds,
            epoch_length_seconds=15,  # 15 seconds for demo
            overlap_time_seconds=3
        )
        
        # Generate comparison report
        report = self.comparator.generate_report()
        logger.info("\n" + report)
        
        # Save comparison report
        report_file = os.path.join(self.output_dir, f"comparison_{int(time.time())}.txt")
        with open(report_file, 'w') as f:
            f.write(report)
        
        # Save all results summary
        summary = {
            "baseline": baseline_result.metrics.to_dict(),
            "namespace_privacy": privacy_result.metrics.to_dict()
        }
        summary_file = os.path.join(self.output_dir, f"summary_{int(time.time())}.json")
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        logger.info(f"\nResults saved to: {self.output_dir}")
        
        return baseline_result, privacy_result


async def main():
    """Main entry point untuk eksperimen"""
    # Create runner
    runner = ExperimentRunner(output_dir="./data/results")
    
    # Run comparison with default parameters
    await runner.run_comparison(
        num_patients=5,
        sensor_types=["spo2", "blood_pressure", "temperature"],
        duration_seconds=30  # 30 seconds for demo
    )


if __name__ == "__main__":
    asyncio.run(main())
