"""
Privacy and Performance Metrics Collection
==========================================
Implementasi metrik evaluasi sesuai BAB 3.4 Metodologi:
- Metrik Privasi (anonymity set, entropi, attack success rate)
- Metrik Unlinkability (linkability probability, traceable rate)
- Metrik Overhead (komputasi, komunikasi, latensi)
- Metrik QoS Klinis (alarm latency, packet loss)
"""

import json
import logging
import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from enum import Enum
import statistics

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MetricType(Enum):
    PRIVACY = "privacy"
    UNLINKABILITY = "unlinkability"
    OVERHEAD = "overhead"
    QOS = "qos"


@dataclass
class PrivacyMetrics:
    """
    Metrik Privasi sesuai BAB 3.4.1
    """
    # Anonymity set size: jumlah kandidat pasien yang konsisten dengan observasi
    anonymity_set_size: float = 0.0
    
    # Entropi anonimitas: ketidakpastian penyerang terhadap identitas
    anonymity_entropy: float = 0.0
    
    # Attack success rate: akurasi model penyerang
    attack_success_rate: float = 0.0
    
    # Topic diversity: berapa banyak pseudo-topic berbeda yang digunakan
    topic_diversity: int = 0
    
    # ClientID diversity: berapa banyak ClientID berbeda yang digunakan
    clientid_diversity: int = 0


@dataclass
class UnlinkabilityMetrics:
    """
    Metrik Unlinkability sesuai BAB 3.4.2
    """
    # Probabilitas linkability antar-epoch
    cross_epoch_linkability: float = 0.0
    
    # Traceable rate: fraksi pesan yang dapat ditelusuri
    traceable_rate: float = 0.0
    
    # Unlinkability score (1 = perfectly unlinkable, 0 = fully linkable)
    unlinkability_score: float = 0.0


@dataclass
class OverheadMetrics:
    """
    Metrik Overhead sesuai BAB 3.4.3
    """
    # Overhead komputasi (ms per pesan)
    computation_overhead_ms: float = 0.0
    
    # Overhead komunikasi
    message_size_overhead_bytes: float = 0.0
    bandwidth_overhead_percent: float = 0.0
    
    # Duplikasi pesan saat overlap
    overlap_duplication_rate: float = 0.0
    
    # Memory usage
    memory_usage_mb: float = 0.0


@dataclass
class QoSMetrics:
    """
    Metrik QoS Klinis sesuai BAB 3.4.4
    """
    # Latensi end-to-end
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    
    # Alarm latency
    alarm_avg_latency_ms: float = 0.0
    alarm_below_threshold_rate: float = 0.0  # % alarm di bawah batas klinis
    
    # Packet loss
    packet_loss_rate: float = 0.0
    
    # Jitter
    jitter_ms: float = 0.0
    
    # Throughput
    messages_per_second: float = 0.0


@dataclass
class ExperimentMetrics:
    """Kumpulan semua metrik untuk satu eksperimen"""
    experiment_id: str
    config_name: str  # "baseline", "namespace_privacy", etc.
    timestamp: float = field(default_factory=time.time)
    duration_seconds: float = 0.0
    
    privacy: PrivacyMetrics = field(default_factory=PrivacyMetrics)
    unlinkability: UnlinkabilityMetrics = field(default_factory=UnlinkabilityMetrics)
    overhead: OverheadMetrics = field(default_factory=OverheadMetrics)
    qos: QoSMetrics = field(default_factory=QoSMetrics)
    
    def to_dict(self) -> dict:
        return {
            "experiment_id": self.experiment_id,
            "config_name": self.config_name,
            "timestamp": self.timestamp,
            "duration_seconds": self.duration_seconds,
            "privacy": {
                "anonymity_set_size": self.privacy.anonymity_set_size,
                "anonymity_entropy": self.privacy.anonymity_entropy,
                "attack_success_rate": self.privacy.attack_success_rate,
                "topic_diversity": self.privacy.topic_diversity,
                "clientid_diversity": self.privacy.clientid_diversity
            },
            "unlinkability": {
                "cross_epoch_linkability": self.unlinkability.cross_epoch_linkability,
                "traceable_rate": self.unlinkability.traceable_rate,
                "unlinkability_score": self.unlinkability.unlinkability_score
            },
            "overhead": {
                "computation_overhead_ms": self.overhead.computation_overhead_ms,
                "message_size_overhead_bytes": self.overhead.message_size_overhead_bytes,
                "bandwidth_overhead_percent": self.overhead.bandwidth_overhead_percent,
                "overlap_duplication_rate": self.overhead.overlap_duplication_rate,
                "memory_usage_mb": self.overhead.memory_usage_mb
            },
            "qos": {
                "avg_latency_ms": self.qos.avg_latency_ms,
                "p95_latency_ms": self.qos.p95_latency_ms,
                "p99_latency_ms": self.qos.p99_latency_ms,
                "max_latency_ms": self.qos.max_latency_ms,
                "alarm_avg_latency_ms": self.qos.alarm_avg_latency_ms,
                "alarm_below_threshold_rate": self.qos.alarm_below_threshold_rate,
                "packet_loss_rate": self.qos.packet_loss_rate,
                "jitter_ms": self.qos.jitter_ms,
                "messages_per_second": self.qos.messages_per_second
            }
        }


class BrokerObservationLog:
    """
    Simulasi log observasi dari sudut pandang broker/penyerang
    Digunakan untuk menghitung metrik privasi
    """
    
    def __init__(self):
        # Observasi yang bisa dilihat broker
        self.topic_observations: List[dict] = []  # topic, timestamp, size
        self.clientid_observations: Set[str] = set()
        self.connection_events: List[dict] = []
        
        # Topic -> observation count
        self.topic_counts: Dict[str, int] = defaultdict(int)
        
        # ClientID -> topics used
        self.clientid_topics: Dict[str, Set[str]] = defaultdict(set)
        
        # Temporal patterns
        self.topic_timestamps: Dict[str, List[float]] = defaultdict(list)
    
    def record_publish(self, client_id: str, topic: str, payload_size: int, timestamp: float):
        """Record observasi publish dari broker"""
        self.topic_observations.append({
            "topic": topic,
            "timestamp": timestamp,
            "size": payload_size,
            "client_id": client_id
        })
        
        self.topic_counts[topic] += 1
        self.clientid_observations.add(client_id)
        self.clientid_topics[client_id].add(topic)
        self.topic_timestamps[topic].append(timestamp)
    
    def record_connection(self, client_id: str, event: str, timestamp: float):
        """Record connection event"""
        self.connection_events.append({
            "client_id": client_id,
            "event": event,  # "connect", "disconnect"
            "timestamp": timestamp
        })


class AttackerModel:
    """
    Model penyerang untuk evaluasi privasi
    Mencoba menghubungkan observasi ke identitas pasien
    """
    
    def __init__(self):
        # Ground truth (untuk evaluasi)
        self.true_mapping: Dict[str, str] = {}  # topic -> patient_id
        
        # Attacker's inference
        self.inferred_mapping: Dict[str, str] = {}
    
    def set_ground_truth(self, topic: str, patient_id: str):
        """Set ground truth mapping (untuk evaluasi)"""
        self.true_mapping[topic] = patient_id
    
    def attack_traffic_analysis(self, observation_log: BrokerObservationLog) -> Dict[str, str]:
        """
        Serangan analisis trafik sederhana
        Mencoba mengelompokkan topics berdasarkan pola temporal
        """
        # Simplified attack: cluster topics by temporal patterns
        clusters: Dict[int, List[str]] = defaultdict(list)
        cluster_id = 0
        
        for topic, timestamps in observation_log.topic_timestamps.items():
            if len(timestamps) < 2:
                clusters[cluster_id].append(topic)
                cluster_id += 1
                continue
            
            # Calculate inter-arrival time pattern
            intervals = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
            avg_interval = sum(intervals) / len(intervals) if intervals else 0
            
            # Crude clustering by interval similarity
            assigned = False
            for cid, topics in clusters.items():
                if topics:
                    # Compare with first topic in cluster
                    ref_topic = topics[0]
                    ref_timestamps = observation_log.topic_timestamps[ref_topic]
                    if len(ref_timestamps) >= 2:
                        ref_intervals = [ref_timestamps[i+1] - ref_timestamps[i] for i in range(len(ref_timestamps)-1)]
                        ref_avg = sum(ref_intervals) / len(ref_intervals)
                        
                        if abs(avg_interval - ref_avg) < 0.5:  # Similar pattern
                            clusters[cid].append(topic)
                            assigned = True
                            break
            
            if not assigned:
                clusters[cluster_id].append(topic)
                cluster_id += 1
        
        # Each cluster is inferred as one patient
        self.inferred_mapping = {}
        for cid, topics in clusters.items():
            inferred_patient = f"inferred_patient_{cid}"
            for topic in topics:
                self.inferred_mapping[topic] = inferred_patient
        
        return self.inferred_mapping
    
    def evaluate_attack_success(self) -> float:
        """
        Evaluasi keberhasilan serangan
        Returns: fraction of correct linkages
        """
        if not self.true_mapping or not self.inferred_mapping:
            return 0.0
        
        # Build true patient -> topics mapping
        true_patient_topics: Dict[str, Set[str]] = defaultdict(set)
        for topic, patient in self.true_mapping.items():
            true_patient_topics[patient].add(topic)
        
        # Build inferred patient -> topics mapping
        inferred_patient_topics: Dict[str, Set[str]] = defaultdict(set)
        for topic, patient in self.inferred_mapping.items():
            inferred_patient_topics[patient].add(topic)
        
        # Count correct linkages
        correct_links = 0
        total_links = 0
        
        for true_patient, true_topics in true_patient_topics.items():
            for inferred_patient, inferred_topics in inferred_patient_topics.items():
                overlap = true_topics & inferred_topics
                if len(overlap) >= 2:
                    # Check if these topics are correctly linked
                    correct_links += len(overlap) * (len(overlap) - 1) // 2
            
            total_links += len(true_topics) * (len(true_topics) - 1) // 2 if len(true_topics) > 1 else 0
        
        return correct_links / total_links if total_links > 0 else 0.0


class MetricsCollector:
    """
    Collector utama untuk semua metrik eksperimen
    """
    
    def __init__(self, experiment_id: str, config_name: str):
        self.experiment_id = experiment_id
        self.config_name = config_name
        self.start_time = time.time()
        
        # Raw data collections
        self.latencies: List[float] = []
        self.alarm_latencies: List[float] = []
        self.message_sizes: List[int] = []
        self.baseline_message_sizes: List[int] = []  # Untuk perbandingan
        self.computation_times: List[float] = []
        
        # Counters
        self.total_messages_sent = 0
        self.total_messages_received = 0
        self.total_alarms = 0
        self.alarms_below_threshold = 0
        self.overlap_duplicates = 0
        
        # Topic and ClientID tracking
        self.unique_topics: Set[str] = set()
        self.unique_client_ids: Set[str] = set()
        self.topic_to_patient: Dict[str, str] = {}  # Ground truth
        
        # Epoch tracking for unlinkability
        self.epoch_topic_mapping: Dict[int, Dict[str, str]] = defaultdict(dict)  # epoch -> topic -> patient
        
        # Broker observation log
        self.broker_log = BrokerObservationLog()
        self.attacker = AttackerModel()
        
        # QoS threshold (ms) for clinical alarms
        self.alarm_latency_threshold_ms = 100.0
    
    def record_message_sent(
        self,
        patient_id: str,
        sensor_id: str,
        topic: str,
        client_id: str,
        payload_size: int,
        computation_time: float,
        is_alarm: bool = False,
        is_duplicate: bool = False,
        epoch: int = 0
    ):
        """Record pesan yang dikirim"""
        self.total_messages_sent += 1
        self.message_sizes.append(payload_size)
        self.computation_times.append(computation_time)
        
        self.unique_topics.add(topic)
        self.unique_client_ids.add(client_id)
        
        # Ground truth mapping
        self.topic_to_patient[topic] = patient_id
        self.attacker.set_ground_truth(topic, patient_id)
        
        # Epoch mapping
        self.epoch_topic_mapping[epoch][topic] = patient_id
        
        # Broker observation
        self.broker_log.record_publish(client_id, topic, payload_size, time.time())
        
        if is_alarm:
            self.total_alarms += 1
        
        if is_duplicate:
            self.overlap_duplicates += 1
    
    def record_message_received(
        self,
        latency_ms: float,
        is_alarm: bool = False
    ):
        """Record pesan yang diterima di backend"""
        self.total_messages_received += 1
        self.latencies.append(latency_ms)
        
        if is_alarm:
            self.alarm_latencies.append(latency_ms)
            if latency_ms < self.alarm_latency_threshold_ms:
                self.alarms_below_threshold += 1
    
    def record_baseline_message_size(self, size: int):
        """Record ukuran pesan baseline (tanpa privacy enhancement)"""
        self.baseline_message_sizes.append(size)
    
    def compute_privacy_metrics(self) -> PrivacyMetrics:
        """Hitung metrik privasi"""
        metrics = PrivacyMetrics()
        
        # Topic diversity
        metrics.topic_diversity = len(self.unique_topics)
        
        # ClientID diversity
        metrics.clientid_diversity = len(self.unique_client_ids)
        
        # Anonymity set size (jumlah pasien unik)
        unique_patients = set(self.topic_to_patient.values())
        metrics.anonymity_set_size = len(unique_patients)
        
        # Anonymity entropy
        if len(unique_patients) > 0:
            # Hitung distribusi observasi per patient
            patient_obs_counts = defaultdict(int)
            for topic, count in self.broker_log.topic_counts.items():
                patient = self.topic_to_patient.get(topic, "unknown")
                patient_obs_counts[patient] += count
            
            total_obs = sum(patient_obs_counts.values())
            if total_obs > 0:
                entropy = 0.0
                for count in patient_obs_counts.values():
                    p = count / total_obs
                    if p > 0:
                        entropy -= p * math.log2(p)
                metrics.anonymity_entropy = entropy
        
        # Attack success rate
        self.attacker.attack_traffic_analysis(self.broker_log)
        metrics.attack_success_rate = self.attacker.evaluate_attack_success()
        
        return metrics
    
    def compute_unlinkability_metrics(self) -> UnlinkabilityMetrics:
        """Hitung metrik unlinkability"""
        metrics = UnlinkabilityMetrics()
        
        # Cross-epoch linkability
        if len(self.epoch_topic_mapping) >= 2:
            epochs = sorted(self.epoch_topic_mapping.keys())
            linkable_pairs = 0
            total_pairs = 0
            
            for i in range(len(epochs) - 1):
                epoch1 = epochs[i]
                epoch2 = epochs[i + 1]
                
                patients1 = set(self.epoch_topic_mapping[epoch1].values())
                patients2 = set(self.epoch_topic_mapping[epoch2].values())
                
                # Check if same patient appears in both epochs
                common = patients1 & patients2
                linkable_pairs += len(common)
                total_pairs += max(len(patients1), len(patients2))
            
            metrics.cross_epoch_linkability = linkable_pairs / total_pairs if total_pairs > 0 else 0.0
        
        # Traceable rate (based on attack success)
        metrics.traceable_rate = self.attacker.evaluate_attack_success()
        
        # Unlinkability score (inverse of traceable rate)
        metrics.unlinkability_score = 1.0 - metrics.traceable_rate
        
        return metrics
    
    def compute_overhead_metrics(self) -> OverheadMetrics:
        """Hitung metrik overhead"""
        metrics = OverheadMetrics()
        
        # Computation overhead
        if self.computation_times:
            metrics.computation_overhead_ms = statistics.mean(self.computation_times) * 1000
        
        # Message size overhead
        if self.message_sizes and self.baseline_message_sizes:
            avg_enhanced = statistics.mean(self.message_sizes)
            avg_baseline = statistics.mean(self.baseline_message_sizes)
            metrics.message_size_overhead_bytes = avg_enhanced - avg_baseline
            metrics.bandwidth_overhead_percent = (avg_enhanced - avg_baseline) / avg_baseline * 100 if avg_baseline > 0 else 0
        
        # Overlap duplication rate
        if self.total_messages_sent > 0:
            metrics.overlap_duplication_rate = self.overlap_duplicates / self.total_messages_sent
        
        return metrics
    
    def compute_qos_metrics(self) -> QoSMetrics:
        """Hitung metrik QoS"""
        metrics = QoSMetrics()
        
        if self.latencies:
            sorted_latencies = sorted(self.latencies)
            metrics.avg_latency_ms = statistics.mean(self.latencies)
            metrics.max_latency_ms = max(self.latencies)
            
            # Percentiles
            p95_idx = int(len(sorted_latencies) * 0.95)
            p99_idx = int(len(sorted_latencies) * 0.99)
            metrics.p95_latency_ms = sorted_latencies[min(p95_idx, len(sorted_latencies)-1)]
            metrics.p99_latency_ms = sorted_latencies[min(p99_idx, len(sorted_latencies)-1)]
            
            # Jitter (standard deviation of latencies)
            if len(self.latencies) > 1:
                metrics.jitter_ms = statistics.stdev(self.latencies)
        
        # Alarm metrics
        if self.alarm_latencies:
            metrics.alarm_avg_latency_ms = statistics.mean(self.alarm_latencies)
        
        if self.total_alarms > 0:
            metrics.alarm_below_threshold_rate = self.alarms_below_threshold / self.total_alarms
        
        # Packet loss
        if self.total_messages_sent > 0:
            metrics.packet_loss_rate = 1.0 - (self.total_messages_received / self.total_messages_sent)
        
        # Throughput
        elapsed = time.time() - self.start_time
        if elapsed > 0:
            metrics.messages_per_second = self.total_messages_received / elapsed
        
        return metrics
    
    def collect_all_metrics(self) -> ExperimentMetrics:
        """Kumpulkan semua metrik"""
        metrics = ExperimentMetrics(
            experiment_id=self.experiment_id,
            config_name=self.config_name,
            duration_seconds=time.time() - self.start_time
        )
        
        metrics.privacy = self.compute_privacy_metrics()
        metrics.unlinkability = self.compute_unlinkability_metrics()
        metrics.overhead = self.compute_overhead_metrics()
        metrics.qos = self.compute_qos_metrics()
        
        return metrics
    
    def save_results(self, filepath: str):
        """Simpan hasil ke file JSON"""
        metrics = self.collect_all_metrics()
        
        with open(filepath, 'w') as f:
            json.dump(metrics.to_dict(), f, indent=2)
        
        logger.info(f"Metrics saved to {filepath}")
        return metrics


class MetricsComparator:
    """
    Membandingkan metrik antara konfigurasi eksperimen
    """
    
    def __init__(self):
        self.experiments: Dict[str, ExperimentMetrics] = {}
    
    def add_experiment(self, metrics: ExperimentMetrics):
        """Tambah hasil eksperimen"""
        self.experiments[metrics.config_name] = metrics
    
    def compare_privacy(self) -> dict:
        """Bandingkan metrik privasi"""
        comparison = {}
        for name, metrics in self.experiments.items():
            comparison[name] = {
                "anonymity_set_size": metrics.privacy.anonymity_set_size,
                "anonymity_entropy": metrics.privacy.anonymity_entropy,
                "attack_success_rate": metrics.privacy.attack_success_rate,
                "topic_diversity": metrics.privacy.topic_diversity
            }
        return comparison
    
    def compare_overhead(self) -> dict:
        """Bandingkan metrik overhead"""
        comparison = {}
        for name, metrics in self.experiments.items():
            comparison[name] = {
                "computation_overhead_ms": metrics.overhead.computation_overhead_ms,
                "bandwidth_overhead_percent": metrics.overhead.bandwidth_overhead_percent,
                "overlap_duplication_rate": metrics.overhead.overlap_duplication_rate
            }
        return comparison
    
    def compare_qos(self) -> dict:
        """Bandingkan metrik QoS"""
        comparison = {}
        for name, metrics in self.experiments.items():
            comparison[name] = {
                "avg_latency_ms": metrics.qos.avg_latency_ms,
                "p99_latency_ms": metrics.qos.p99_latency_ms,
                "alarm_below_threshold_rate": metrics.qos.alarm_below_threshold_rate,
                "packet_loss_rate": metrics.qos.packet_loss_rate
            }
        return comparison
    
    def generate_report(self) -> str:
        """Generate report perbandingan"""
        report = ["=" * 60]
        report.append("EXPERIMENT COMPARISON REPORT")
        report.append("=" * 60)
        
        report.append("\n--- Privacy Metrics ---")
        for name, data in self.compare_privacy().items():
            report.append(f"\n{name}:")
            for metric, value in data.items():
                report.append(f"  {metric}: {value:.4f}")
        
        report.append("\n--- Overhead Metrics ---")
        for name, data in self.compare_overhead().items():
            report.append(f"\n{name}:")
            for metric, value in data.items():
                report.append(f"  {metric}: {value:.4f}")
        
        report.append("\n--- QoS Metrics ---")
        for name, data in self.compare_qos().items():
            report.append(f"\n{name}:")
            for metric, value in data.items():
                report.append(f"  {metric}: {value:.4f}")
        
        report.append("\n" + "=" * 60)
        
        return "\n".join(report)


if __name__ == "__main__":
    # Test metrics collection
    collector = MetricsCollector("test_001", "namespace_privacy")
    
    # Simulate some data
    import random
    
    for i in range(100):
        patient_id = f"patient_{i % 10}"
        topic = f"t/topic_{i % 20}"
        client_id = f"gw_{i % 3}"
        
        collector.record_message_sent(
            patient_id=patient_id,
            sensor_id="spo2",
            topic=topic,
            client_id=client_id,
            payload_size=random.randint(50, 200),
            computation_time=random.uniform(0.001, 0.01),
            is_alarm=(i % 50 == 0),
            is_duplicate=(i % 30 == 0),
            epoch=i // 50
        )
        
        collector.record_message_received(
            latency_ms=random.uniform(5, 50),
            is_alarm=(i % 50 == 0)
        )
        
        collector.record_baseline_message_size(random.randint(40, 150))
    
    # Collect and print metrics
    metrics = collector.collect_all_metrics()
    print(json.dumps(metrics.to_dict(), indent=2))
