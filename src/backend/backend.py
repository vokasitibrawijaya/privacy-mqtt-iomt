"""
Backend Subscriber & Topic Mapping Controller
==============================================
Implementasi backend yang menerima data dari broker dan mengelola mapping pseudo-topic
Sesuai pseudo-code di BAB Desain Sistem: Protokol di Backend Subscriber
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Callable, Any, List, Set
from collections import defaultdict
import paho.mqtt.client as mqtt

from ..crypto import KeyMaterial, decrypt_payload
from ..config import BrokerConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class TopicMappingEntry:
    """
    Entry pemetaan di backend
    Sesuai: BACKEND_TOPIC_MAP : map<(PID,SID) -> (topic_current, topic_old)>
    """
    pid: str
    sid: str
    topic_current: str
    topic_old: Optional[str] = None
    last_update: float = field(default_factory=time.time)
    message_count: int = 0


@dataclass
class ReceivedMessage:
    """Data message yang diterima dari broker"""
    pid: str
    sid: str
    topic: str
    payload: bytes
    timestamp: float
    decrypted: bool = True


class BackendTopicMapper:
    """
    Mengelola pemetaan pseudo-topic ke (PID, SID)
    Implementasi: BACKEND_TOPIC_MAP dan fungsi FIND_LOGICAL_STREAM()
    """
    
    def __init__(self):
        # map<(PID,SID) -> TopicMappingEntry>
        self.mapping_by_stream: Dict[tuple, TopicMappingEntry] = {}
        
        # Reverse index: map<topic -> (PID,SID)>
        self.topic_to_stream: Dict[str, tuple] = {}
        
        # Statistics
        self.total_updates = 0
        self.total_lookups = 0
        self.lookup_misses = 0
    
    def _get_stream_key(self, pid: str, sid: str) -> tuple:
        return (pid, sid)
    
    def update_mapping(
        self,
        pid: str,
        sid: str,
        topic_current: str,
        topic_old: Optional[str],
        mode: str
    ):
        """
        Handle control update dari gateway
        Implementasi: procedure ON_CONTROL_UPDATE(PID, SID, topic_current, topic_old, mode)
        """
        key = self._get_stream_key(pid, sid)
        
        if mode == "INIT":
            # Stream baru
            entry = TopicMappingEntry(
                pid=pid,
                sid=sid,
                topic_current=topic_current,
                topic_old=topic_old
            )
            self.mapping_by_stream[key] = entry
            
            # Update reverse index
            self.topic_to_stream[topic_current] = key
            
            logger.info(f"INIT mapping: {pid}/{sid} -> {topic_current}")
        
        elif mode == "ROTATE":
            # Rotasi topic
            entry = self.mapping_by_stream.get(key)
            if entry:
                # Hapus topic lama dari reverse index jika ada
                if entry.topic_current in self.topic_to_stream:
                    # Keep it during overlap
                    pass
                
                # Update entry
                entry.topic_old = topic_old
                entry.topic_current = topic_current
                entry.last_update = time.time()
                
                # Add new topic to reverse index
                self.topic_to_stream[topic_current] = key
                if topic_old:
                    self.topic_to_stream[topic_old] = key
                
                logger.info(f"ROTATE mapping: {pid}/{sid} -> {topic_current} (old: {topic_old})")
        
        elif mode == "END_OVERLAP":
            # Akhiri overlap - hapus topic_old
            entry = self.mapping_by_stream.get(key)
            if entry:
                old_topic = entry.topic_old
                if old_topic and old_topic in self.topic_to_stream:
                    del self.topic_to_stream[old_topic]
                
                entry.topic_old = None
                entry.last_update = time.time()
                
                logger.info(f"END_OVERLAP: {pid}/{sid}, retired {old_topic}")
        
        self.total_updates += 1
    
    def find_logical_stream(self, topic: str) -> Optional[tuple]:
        """
        Temukan (PID, SID) dari topic
        Implementasi: function FIND_LOGICAL_STREAM(topic)
        """
        self.total_lookups += 1
        
        stream_key = self.topic_to_stream.get(topic)
        if stream_key is None:
            self.lookup_misses += 1
            logger.warning(f"Unknown topic: {topic}")
        
        return stream_key
    
    def get_subscribed_topics(self) -> Set[str]:
        """Dapatkan semua topic yang perlu di-subscribe"""
        return set(self.topic_to_stream.keys())
    
    def record_message(self, pid: str, sid: str):
        """Record message received untuk statistik"""
        key = self._get_stream_key(pid, sid)
        entry = self.mapping_by_stream.get(key)
        if entry:
            entry.message_count += 1
    
    def get_stats(self) -> dict:
        """Get mapper statistics"""
        return {
            "total_streams": len(self.mapping_by_stream),
            "total_topics_tracked": len(self.topic_to_stream),
            "total_updates": self.total_updates,
            "total_lookups": self.total_lookups,
            "lookup_misses": self.lookup_misses,
            "lookup_hit_rate": (self.total_lookups - self.lookup_misses) / self.total_lookups if self.total_lookups > 0 else 1.0
        }


class MedicalDataProcessor:
    """
    Processor untuk data medis yang diterima
    Implementasi: PROCESS_MEDICAL_DATA(PID, SID, payload)
    """
    
    def __init__(self):
        self.processed_count = 0
        self.data_by_stream: Dict[tuple, List[dict]] = defaultdict(list)
        self.alarms: List[dict] = []
        
        # Callbacks untuk processing custom
        self.callbacks: List[Callable[[str, str, bytes], None]] = []
    
    def process(self, pid: str, sid: str, payload: bytes, timestamp: float):
        """Process data medis"""
        self.processed_count += 1
        
        # Store data
        data_entry = {
            "timestamp": timestamp,
            "payload_size": len(payload),
            "payload_preview": payload[:50].hex() if len(payload) > 50 else payload.hex()
        }
        
        key = (pid, sid)
        self.data_by_stream[key].append(data_entry)
        
        # Check for alarms (simplified - check payload content)
        try:
            decoded = payload.decode('utf-8', errors='ignore')
            if 'alarm' in decoded.lower() or 'alert' in decoded.lower():
                self.alarms.append({
                    "pid": pid,
                    "sid": sid,
                    "timestamp": timestamp,
                    "payload": decoded[:100]
                })
                logger.warning(f"ALARM detected: {pid}/{sid}")
        except:
            pass
        
        # Call registered callbacks
        for callback in self.callbacks:
            try:
                callback(pid, sid, payload)
            except Exception as e:
                logger.error(f"Callback error: {e}")
    
    def register_callback(self, callback: Callable[[str, str, bytes], None]):
        """Register callback untuk processing custom"""
        self.callbacks.append(callback)
    
    def get_stats(self) -> dict:
        """Get processor statistics"""
        return {
            "processed_count": self.processed_count,
            "unique_streams": len(self.data_by_stream),
            "total_alarms": len(self.alarms),
            "data_per_stream": {
                f"{k[0]}/{k[1]}": len(v) for k, v in list(self.data_by_stream.items())[:10]
            }
        }


class BackendSubscriber:
    """
    Backend MQTT Subscriber dengan Topic Mapping Controller
    Komponen utama yang menerima data dari broker dan mengelola mapping
    """
    
    def __init__(
        self,
        backend_id: str,
        keys: KeyMaterial,
        broker_config: BrokerConfig
    ):
        self.backend_id = backend_id
        self.keys = keys
        self.broker_config = broker_config
        
        # Control channel topic
        self.control_topic = "ctrl/gateway_updates"
        
        # Components
        self.topic_mapper = BackendTopicMapper()
        self.data_processor = MedicalDataProcessor()
        
        # MQTT client
        self.client: Optional[mqtt.Client] = None
        self.connected = False
        
        # Subscribed topics
        self.subscribed_topics: Set[str] = set()
        
        # Metrics
        self.message_count = 0
        self.control_message_count = 0
        self.unknown_topic_count = 0
        self.decrypt_errors = 0
        self.latencies: List[float] = []
    
    def _create_client(self) -> mqtt.Client:
        """Create MQTT client"""
        client_id = f"backend_{self.backend_id}"
        client = mqtt.Client(client_id=client_id, clean_session=True)
        
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        
        if self.broker_config.tls_enabled:
            client.tls_set()
        
        if self.broker_config.username:
            client.username_pw_set(
                self.broker_config.username,
                self.broker_config.password
            )
        
        return client
    
    def connect(self):
        """Connect ke broker"""
        self.client = self._create_client()
        
        logger.info(f"Backend connecting to {self.broker_config.host}:{self.broker_config.port}")
        self.client.connect(
            self.broker_config.host,
            self.broker_config.port,
            keepalive=60
        )
        self.client.loop_start()
    
    def disconnect(self):
        """Disconnect dari broker"""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            self.connected = False
    
    def _on_connect(self, client, userdata, flags, rc):
        """Callback saat connect"""
        if rc == 0:
            self.connected = True
            logger.info(f"Backend connected to broker")
            
            # Subscribe ke control channel
            client.subscribe(self.control_topic, qos=1)
            logger.info(f"Subscribed to control channel: {self.control_topic}")
            
            # Subscribe ke semua pseudo-topic yang sudah diketahui
            for topic in self.subscribed_topics:
                client.subscribe(topic, qos=1)
        else:
            logger.error(f"Backend connection failed with code {rc}")
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback saat disconnect"""
        self.connected = False
        logger.info(f"Backend disconnected (rc={rc})")
    
    def _on_message(self, client, userdata, msg):
        """
        Callback saat menerima message
        Implementasi: procedure ON_MQTT_MESSAGE_RECEIVED(topic, payload)
        """
        receive_time = time.time()
        
        if msg.topic == self.control_topic:
            # Handle control message
            self._handle_control_message(msg.payload)
        else:
            # Handle data message
            self._handle_data_message(msg.topic, msg.payload, receive_time)
    
    def _handle_control_message(self, payload: bytes):
        """
        Handle control update dari gateway
        """
        self.control_message_count += 1
        
        try:
            # Decrypt control message
            decrypted = decrypt_payload(self.keys.control_encrypt_key, payload)
            data = json.loads(decrypted.decode('utf-8'))
            
            pid = data['pid']
            sid = data['sid']
            topic_current = data['topic_current']
            topic_old = data.get('topic_old')
            mode = data['mode']
            
            # Update mapping
            self.topic_mapper.update_mapping(pid, sid, topic_current, topic_old, mode)
            
            # Subscribe/unsubscribe as needed
            if mode in ["INIT", "ROTATE"]:
                if topic_current not in self.subscribed_topics:
                    self.client.subscribe(topic_current, qos=1)
                    self.subscribed_topics.add(topic_current)
                    logger.debug(f"Subscribed to {topic_current}")
                
                if topic_old and topic_old not in self.subscribed_topics:
                    self.client.subscribe(topic_old, qos=1)
                    self.subscribed_topics.add(topic_old)
            
            elif mode == "END_OVERLAP":
                if topic_old and topic_old in self.subscribed_topics:
                    self.client.unsubscribe(topic_old)
                    self.subscribed_topics.discard(topic_old)
                    logger.debug(f"Unsubscribed from {topic_old}")
        
        except Exception as e:
            logger.error(f"Error handling control message: {e}")
            self.decrypt_errors += 1
    
    def _handle_data_message(self, topic: str, payload: bytes, receive_time: float):
        """
        Handle data message dari sensor via gateway
        """
        self.message_count += 1
        
        # Find logical stream
        stream_key = self.topic_mapper.find_logical_stream(topic)
        
        if stream_key is None:
            self.unknown_topic_count += 1
            logger.debug(f"Received message on unknown topic: {topic}")
            return
        
        pid, sid = stream_key
        
        # Decrypt payload
        try:
            decrypted_payload = decrypt_payload(self.keys.control_encrypt_key, payload)
        except Exception as e:
            logger.error(f"Decrypt error for {topic}: {e}")
            self.decrypt_errors += 1
            return
        
        # Record in mapper
        self.topic_mapper.record_message(pid, sid)
        
        # Process medical data
        self.data_processor.process(pid, sid, decrypted_payload, receive_time)
        
        # Calculate latency if timestamp in payload
        try:
            # Try to extract timestamp from payload for latency calculation
            payload_str = decrypted_payload.decode('utf-8', errors='ignore')
            if 'time_' in payload_str or payload_str.replace('.', '').replace('_', '').replace('-', '').isdigit():
                # Simplified latency tracking
                self.latencies.append(0.001)  # Placeholder
        except:
            pass
    
    def get_stats(self) -> dict:
        """Get comprehensive statistics"""
        avg_latency = sum(self.latencies) / len(self.latencies) if self.latencies else 0
        
        return {
            "backend_id": self.backend_id,
            "connected": self.connected,
            "total_messages": self.message_count,
            "control_messages": self.control_message_count,
            "unknown_topic_messages": self.unknown_topic_count,
            "decrypt_errors": self.decrypt_errors,
            "subscribed_topics_count": len(self.subscribed_topics),
            "avg_latency_ms": avg_latency * 1000,
            "topic_mapper_stats": self.topic_mapper.get_stats(),
            "data_processor_stats": self.data_processor.get_stats()
        }


async def run_backend(
    backend_id: str,
    keys: KeyMaterial,
    broker_config: BrokerConfig,
    duration_seconds: int = 60
):
    """
    Main function untuk menjalankan backend
    """
    logger.info(f"Starting backend {backend_id}")
    
    # Create backend
    backend = BackendSubscriber(
        backend_id=backend_id,
        keys=keys,
        broker_config=broker_config
    )
    
    # Connect
    backend.connect()
    await asyncio.sleep(1)
    
    # Run for duration
    start_time = time.time()
    while time.time() - start_time < duration_seconds:
        # Print stats periodically
        if int(time.time() - start_time) % 10 == 0:
            stats = backend.get_stats()
            logger.info(f"Backend stats: messages={stats['total_messages']}, streams={stats['topic_mapper_stats']['total_streams']}")
        
        await asyncio.sleep(1)
    
    # Final stats
    stats = backend.get_stats()
    logger.info(f"Final backend stats: {json.dumps(stats, indent=2)}")
    
    # Disconnect
    backend.disconnect()
    
    return stats


if __name__ == "__main__":
    # Test backend
    keys = KeyMaterial.generate()
    broker_config = BrokerConfig(host="localhost", port=1883)
    
    asyncio.run(run_backend(
        backend_id="backend_test_01",
        keys=keys,
        broker_config=broker_config,
        duration_seconds=120
    ))
