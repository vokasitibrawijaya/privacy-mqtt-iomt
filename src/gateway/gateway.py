"""
Gateway / Topic & ID Privacy Manager (TPM)
==========================================
Implementasi lengkap sesuai pseudo-code di BAB Desain Sistem

Komponen utama:
1. StreamState - State per stream (PID,SID)
2. TopicPrivacyManager - Mengelola rotasi pseudo-topic
3. ClientIDManager - Mengelola rotasi ClientID
4. GatewayMQTTClient - MQTT client dengan privacy features
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Callable, Any, List
from enum import Enum
import paho.mqtt.client as mqtt

from ..crypto import gen_pseudo_topic, gen_pseudo_client_id, KeyMaterial, encrypt_payload
from ..config import PrivacyConfig, BrokerConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RotationTrigger(Enum):
    TIME = "time"
    MESSAGES = "messages"


@dataclass
class StreamState:
    """
    Struktur data di Gateway/TPM per stream (pasien + sensor)
    Sesuai pseudo-code: struct StreamState
    """
    pid: str  # Patient internal ID
    sid: str  # Stream/Sensor ID (ecg, spo2, dll)
    epoch_current: int = 0
    topic_old: Optional[str] = None
    topic_current: Optional[str] = None
    epoch_start_ts: float = field(default_factory=time.time)
    overlap_active: bool = False
    message_count: int = 0  # Counter untuk rotasi berbasis volume


@dataclass
class ControlUpdate:
    """
    Pesan kontrol untuk dikirim ke backend
    Berisi informasi mapping pseudo-topic
    """
    pid: str
    sid: str
    topic_current: str
    topic_old: Optional[str]
    mode: str  # "INIT", "ROTATE", "END_OVERLAP"
    timestamp: float = field(default_factory=time.time)
    epoch: int = 0
    
    def to_json(self) -> str:
        return json.dumps({
            "pid": self.pid,
            "sid": self.sid,
            "topic_current": self.topic_current,
            "topic_old": self.topic_old,
            "mode": self.mode,
            "timestamp": self.timestamp,
            "epoch": self.epoch
        })
    
    @classmethod
    def from_json(cls, data: str) -> 'ControlUpdate':
        d = json.loads(data)
        return cls(**d)


class TopicPrivacyManager:
    """
    Topic & ID Privacy Manager (TPM)
    Mengelola pemetaan dan rotasi pseudo-topic untuk semua stream
    """
    
    def __init__(
        self,
        gateway_id: str,
        keys: KeyMaterial,
        config: PrivacyConfig,
        control_callback: Optional[Callable[[ControlUpdate], None]] = None
    ):
        self.gateway_id = gateway_id
        self.keys = keys
        self.config = config
        self.control_callback = control_callback
        
        # STREAM_TABLE: map<(PID,SID) -> StreamState>
        self.stream_table: Dict[tuple, StreamState] = {}
        
        # Metrics
        self.total_rotations = 0
        self.total_messages_published = 0
    
    def _get_stream_key(self, pid: str, sid: str) -> tuple:
        """Generate key untuk stream table"""
        return (pid, sid)
    
    def init_stream(self, pid: str, sid: str, start_epoch: int = 0) -> StreamState:
        """
        Inisialisasi stream baru
        Implementasi: procedure INIT_STREAM(PID, SID, start_epoch)
        """
        key = self._get_stream_key(pid, sid)
        
        # Generate pseudo-topic pertama
        topic_current = gen_pseudo_topic(
            self.keys.topic_key, pid, sid, start_epoch
        )
        
        state = StreamState(
            pid=pid,
            sid=sid,
            epoch_current=start_epoch,
            topic_current=topic_current,
            topic_old=None,
            epoch_start_ts=time.time(),
            overlap_active=False,
            message_count=0
        )
        
        self.stream_table[key] = state
        
        # Kirim CONTROL_UPDATE ke backend
        self._send_control_update(state, mode="INIT")
        
        logger.info(f"Initialized stream {pid}/{sid} with topic {topic_current}")
        return state
    
    def get_stream(self, pid: str, sid: str) -> Optional[StreamState]:
        """Get stream state, auto-init jika belum ada"""
        key = self._get_stream_key(pid, sid)
        state = self.stream_table.get(key)
        
        if state is None:
            state = self.init_stream(pid, sid)
        
        return state
    
    def get_publish_topics(self, pid: str, sid: str) -> List[str]:
        """
        Dapatkan daftar topic untuk publish
        Saat overlap, return [topic_current, topic_old]
        """
        state = self.get_stream(pid, sid)
        topics = [state.topic_current]
        
        if state.overlap_active and state.topic_old:
            topics.append(state.topic_old)
        
        return topics
    
    def record_message(self, pid: str, sid: str) -> bool:
        """
        Record pesan yang dikirim, cek apakah perlu rotasi
        Returns: True jika perlu rotasi
        """
        key = self._get_stream_key(pid, sid)
        state = self.stream_table.get(key)
        
        if state:
            state.message_count += 1
            self.total_messages_published += 1
            
            # Cek rotasi berbasis volume
            if self.config.rotation_trigger == "messages":
                if state.message_count >= self.config.epoch_length_messages:
                    return True
        
        return False
    
    def check_rotation_needed(self, pid: str, sid: str) -> bool:
        """
        Cek apakah stream perlu rotasi berdasarkan waktu
        """
        key = self._get_stream_key(pid, sid)
        state = self.stream_table.get(key)
        
        if state and self.config.rotation_trigger == "time":
            elapsed = time.time() - state.epoch_start_ts
            return elapsed >= self.config.epoch_length_seconds
        
        return False
    
    def rotate_epoch(self, pid: str, sid: str) -> StreamState:
        """
        Rotasi pseudo-topic ke epoch baru
        Implementasi: procedure ROTATE_EPOCH(PID, SID)
        """
        key = self._get_stream_key(pid, sid)
        state = self.stream_table[key]
        
        # 1. Hitung epoch baru dan pseudo-topic baru
        new_epoch = state.epoch_current + 1
        new_topic = gen_pseudo_topic(
            self.keys.topic_key, pid, sid, new_epoch
        )
        
        # 2. Pindahkan topic_current menjadi topic_old
        state.topic_old = state.topic_current
        state.topic_current = new_topic
        state.epoch_current = new_epoch
        state.epoch_start_ts = time.time()
        state.overlap_active = True
        state.message_count = 0
        
        self.stream_table[key] = state
        self.total_rotations += 1
        
        # 3. Kirim update ke backend
        self._send_control_update(state, mode="ROTATE")
        
        logger.info(f"Rotated stream {pid}/{sid} to epoch {new_epoch}, topic {new_topic}")
        
        return state
    
    def end_overlap(self, pid: str, sid: str):
        """
        Akhiri fase overlap
        Implementasi: procedure END_OVERLAP(PID, SID)
        """
        key = self._get_stream_key(pid, sid)
        state = self.stream_table.get(key)
        
        if state:
            old_topic = state.topic_old
            state.overlap_active = False
            state.topic_old = None
            self.stream_table[key] = state
            
            # Informasikan ke backend
            self._send_control_update(state, mode="END_OVERLAP")
            
            logger.info(f"Ended overlap for {pid}/{sid}, retired topic {old_topic}")
    
    def _send_control_update(self, state: StreamState, mode: str):
        """Kirim control update ke backend via callback"""
        update = ControlUpdate(
            pid=state.pid,
            sid=state.sid,
            topic_current=state.topic_current,
            topic_old=state.topic_old,
            mode=mode,
            epoch=state.epoch_current
        )
        
        if self.control_callback:
            self.control_callback(update)
    
    def get_all_active_topics(self) -> List[str]:
        """Dapatkan semua pseudo-topic yang aktif"""
        topics = set()
        for state in self.stream_table.values():
            topics.add(state.topic_current)
            if state.overlap_active and state.topic_old:
                topics.add(state.topic_old)
        return list(topics)
    
    def get_stats(self) -> dict:
        """Dapatkan statistik TPM"""
        return {
            "total_streams": len(self.stream_table),
            "total_rotations": self.total_rotations,
            "total_messages": self.total_messages_published,
            "active_overlaps": sum(1 for s in self.stream_table.values() if s.overlap_active)
        }


class ClientIDManager:
    """
    Mengelola rotasi ClientID untuk gateway
    Implementasi: procedure ROTATE_CLIENT_ID()
    """
    
    def __init__(
        self,
        gateway_id: str,
        keys: KeyMaterial,
        config: PrivacyConfig
    ):
        self.gateway_id = gateway_id
        self.keys = keys
        self.config = config
        
        self.current_epoch = 0
        self.current_client_id = self._generate_client_id(0)
        self.last_rotation_ts = time.time()
        self.rotation_count = 0
    
    def _generate_client_id(self, epoch: int) -> str:
        """Generate pseudo-ClientID untuk epoch"""
        return gen_pseudo_client_id(self.keys.clientid_key, self.gateway_id, epoch)
    
    def get_current_client_id(self) -> str:
        """Dapatkan ClientID saat ini"""
        return self.current_client_id
    
    def should_rotate(self) -> bool:
        """Cek apakah perlu rotasi ClientID"""
        if not self.config.rotate_client_id:
            return False
        
        elapsed = time.time() - self.last_rotation_ts
        return elapsed >= self.config.client_id_rotation_interval
    
    def rotate(self) -> str:
        """
        Rotasi ke ClientID baru
        Returns: ClientID baru
        """
        self.current_epoch += 1
        self.current_client_id = self._generate_client_id(self.current_epoch)
        self.last_rotation_ts = time.time()
        self.rotation_count += 1
        
        logger.info(f"Rotated ClientID to {self.current_client_id} (epoch {self.current_epoch})")
        return self.current_client_id


class GatewayMQTTClient:
    """
    MQTT Client untuk Gateway dengan privacy features
    Menggabungkan TopicPrivacyManager dan ClientIDManager
    """
    
    def __init__(
        self,
        gateway_id: str,
        keys: KeyMaterial,
        broker_config: BrokerConfig,
        privacy_config: PrivacyConfig
    ):
        self.gateway_id = gateway_id
        self.keys = keys
        self.broker_config = broker_config
        self.privacy_config = privacy_config
        
        # Control channel topic (encrypted)
        self.control_topic = "ctrl/gateway_updates"
        
        # Initialize managers
        self.topic_manager = TopicPrivacyManager(
            gateway_id, keys, privacy_config,
            control_callback=self._on_control_update
        )
        self.clientid_manager = ClientIDManager(
            gateway_id, keys, privacy_config
        )
        
        # MQTT client
        self.client: Optional[mqtt.Client] = None
        self.connected = False
        
        # Pending overlap ends (scheduled)
        self._pending_overlap_ends: Dict[tuple, asyncio.Task] = {}
        
        # Metrics
        self.publish_count = 0
        self.publish_latencies: List[float] = []
    
    def _create_client(self) -> mqtt.Client:
        """Create MQTT client dengan ClientID saat ini"""
        client_id = self.clientid_manager.get_current_client_id()
        client = mqtt.Client(client_id=client_id, clean_session=True)
        
        # Setup callbacks
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_publish = self._on_publish
        
        # TLS jika diaktifkan
        if self.broker_config.tls_enabled:
            client.tls_set()
        
        # Auth jika ada
        if self.broker_config.username:
            client.username_pw_set(
                self.broker_config.username,
                self.broker_config.password
            )
        
        return client
    
    def connect(self):
        """Connect ke MQTT broker"""
        self.client = self._create_client()
        
        logger.info(f"Connecting to broker {self.broker_config.host}:{self.broker_config.port}")
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
            logger.info(f"Connected to broker with ClientID {self.clientid_manager.get_current_client_id()}")
        else:
            logger.error(f"Connection failed with code {rc}")
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback saat disconnect"""
        self.connected = False
        logger.info(f"Disconnected from broker (rc={rc})")
    
    def _on_publish(self, client, userdata, mid):
        """Callback saat publish berhasil"""
        pass
    
    def _on_control_update(self, update: ControlUpdate):
        """
        Callback untuk mengirim control update ke backend
        Dikirim via MQTT dengan enkripsi
        """
        if self.client and self.connected:
            # Encrypt control message
            payload = update.to_json().encode('utf-8')
            encrypted = encrypt_payload(self.keys.control_encrypt_key, payload)
            
            # Publish ke control topic
            self.client.publish(
                self.control_topic,
                encrypted,
                qos=1
            )
            logger.debug(f"Sent control update: {update.mode} for {update.pid}/{update.sid}")
    
    async def publish_sensor_data(
        self,
        patient_id: str,
        sensor_id: str,
        payload: bytes,
        qos: int = 1
    ) -> bool:
        """
        Publish data sensor ke broker dengan privacy protection
        Implementasi: procedure PUBLISH_FROM_SENSOR(PID, SID, payload)
        """
        if not self.client or not self.connected:
            logger.warning("Not connected to broker")
            return False
        
        start_time = time.time()
        
        # Cek apakah perlu rotasi
        if self.topic_manager.check_rotation_needed(patient_id, sensor_id):
            await self._perform_rotation(patient_id, sensor_id)
        
        # Dapatkan topic(s) untuk publish
        topics = self.topic_manager.get_publish_topics(patient_id, sensor_id)
        
        # Encrypt payload
        encrypted_payload = encrypt_payload(self.keys.control_encrypt_key, payload)
        
        # Publish ke semua topic (overlap jika aktif)
        for topic in topics:
            result = self.client.publish(topic, encrypted_payload, qos=qos)
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                logger.error(f"Publish failed to {topic}")
                return False
        
        # Record metrics
        self.publish_count += 1
        latency = time.time() - start_time
        self.publish_latencies.append(latency)
        
        # Record message untuk rotasi berbasis volume
        needs_rotation = self.topic_manager.record_message(patient_id, sensor_id)
        if needs_rotation:
            await self._perform_rotation(patient_id, sensor_id)
        
        return True
    
    async def _perform_rotation(self, patient_id: str, sensor_id: str):
        """Perform rotation dan schedule end overlap"""
        state = self.topic_manager.rotate_epoch(patient_id, sensor_id)
        
        # Schedule end overlap
        key = (patient_id, sensor_id)
        if key in self._pending_overlap_ends:
            self._pending_overlap_ends[key].cancel()
        
        task = asyncio.create_task(
            self._schedule_end_overlap(patient_id, sensor_id)
        )
        self._pending_overlap_ends[key] = task
    
    async def _schedule_end_overlap(self, patient_id: str, sensor_id: str):
        """Schedule end overlap setelah OVERLAP_TIME"""
        await asyncio.sleep(self.privacy_config.overlap_time_seconds)
        self.topic_manager.end_overlap(patient_id, sensor_id)
        
        key = (patient_id, sensor_id)
        if key in self._pending_overlap_ends:
            del self._pending_overlap_ends[key]
    
    async def check_client_id_rotation(self):
        """Cek dan lakukan rotasi ClientID jika diperlukan"""
        if self.clientid_manager.should_rotate():
            await self._rotate_client_id()
    
    async def _rotate_client_id(self):
        """
        Rotasi ClientID - reconnect dengan ID baru
        Implementasi: procedure ROTATE_CLIENT_ID()
        """
        logger.info("Starting ClientID rotation...")
        
        # Generate new ClientID
        new_client_id = self.clientid_manager.rotate()
        
        # Wait for inflight messages (simplified)
        await asyncio.sleep(1)
        
        # Disconnect old connection
        old_client = self.client
        if old_client:
            old_client.loop_stop()
            old_client.disconnect()
        
        # Create new connection
        self.client = self._create_client()
        self.client.connect(
            self.broker_config.host,
            self.broker_config.port,
            keepalive=60
        )
        self.client.loop_start()
        
        # Wait for connection
        await asyncio.sleep(0.5)
        
        logger.info(f"ClientID rotation complete: {new_client_id}")
    
    def get_stats(self) -> dict:
        """Get comprehensive stats"""
        avg_latency = sum(self.publish_latencies) / len(self.publish_latencies) if self.publish_latencies else 0
        
        return {
            "gateway_id": self.gateway_id,
            "current_client_id": self.clientid_manager.get_current_client_id(),
            "client_id_rotations": self.clientid_manager.rotation_count,
            "connected": self.connected,
            "publish_count": self.publish_count,
            "avg_publish_latency_ms": avg_latency * 1000,
            "topic_manager_stats": self.topic_manager.get_stats()
        }


async def run_gateway(
    gateway_id: str,
    patient_ids: List[str],
    sensor_types: List[str],
    keys: KeyMaterial,
    broker_config: BrokerConfig,
    privacy_config: PrivacyConfig,
    duration_seconds: int = 60
):
    """
    Main function untuk menjalankan gateway
    Implementasi: procedure GATEWAY_MAIN()
    """
    logger.info(f"Starting gateway {gateway_id} with {len(patient_ids)} patients")
    
    # Create gateway client
    gateway = GatewayMQTTClient(
        gateway_id=gateway_id,
        keys=keys,
        broker_config=broker_config,
        privacy_config=privacy_config
    )
    
    # Connect to broker
    gateway.connect()
    await asyncio.sleep(1)  # Wait for connection
    
    # Initialize all streams
    for pid in patient_ids:
        for sid in sensor_types:
            gateway.topic_manager.init_stream(pid, sid)
    
    logger.info(f"Initialized {len(patient_ids) * len(sensor_types)} streams")
    
    # Run simulation (akan diganti dengan simulator sensor)
    start_time = time.time()
    while time.time() - start_time < duration_seconds:
        # Check ClientID rotation
        await gateway.check_client_id_rotation()
        
        # Simulate sensor data (placeholder)
        for pid in patient_ids:
            for sid in sensor_types:
                payload = f"data_{pid}_{sid}_{time.time()}".encode()
                await gateway.publish_sensor_data(pid, sid, payload)
        
        await asyncio.sleep(1)  # 1 Hz for now
    
    # Print final stats
    stats = gateway.get_stats()
    logger.info(f"Gateway stats: {json.dumps(stats, indent=2)}")
    
    # Disconnect
    gateway.disconnect()
    
    return stats


if __name__ == "__main__":
    # Test gateway
    import asyncio
    
    keys = KeyMaterial.generate()
    broker_config = BrokerConfig(host="localhost", port=1883)
    privacy_config = PrivacyConfig(
        epoch_length_seconds=30,  # 30 detik untuk testing
        overlap_time_seconds=5,
        rotation_trigger="time"
    )
    
    asyncio.run(run_gateway(
        gateway_id="gw_test_01",
        patient_ids=["patient_001", "patient_002"],
        sensor_types=["ecg", "spo2"],
        keys=keys,
        broker_config=broker_config,
        privacy_config=privacy_config,
        duration_seconds=120
    ))
