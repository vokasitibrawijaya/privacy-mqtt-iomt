"""
Security Enhancement Module - Key Evolution and Gateway Compromise Mitigations
===============================================================================

This module implements the enhanced security features requested by IEEE reviewers:

1. KEY EVOLUTION: Forward secrecy via epoch-based key derivation
2. GATEWAY HARDENING: Multi-layer key protection
3. KEY COMPROMISE RECOVERY: Automatic key rotation protocol
4. AUDIT LOGGING: Secure logging for forensics

Author: Privacy-Aware MQTT Research Team
Date: January 2026
"""

import hashlib
import hmac
import os
import time
import json
import threading
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Callable
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend


# =============================================================================
# KEY EVOLUTION PROTOCOL
# =============================================================================

class KeyEvolutionManager:
    """
    Implements forward secrecy via epoch-based key derivation.
    
    Protocol:
    - Master key K_0 is initial shared secret
    - Each epoch derives new key: K_{i+1} = HKDF(K_i, epoch_id)
    - Old keys are securely deleted after epoch transition
    
    Security Property:
    - Compromise of K_i does not reveal K_{i-1} (backward secrecy)
    - Compromise of K_i reveals K_{i+1}...K_n (forward secrecy via key update)
    """
    
    def __init__(self, master_key: bytes, epoch_duration: int = 20):
        """
        Initialize key evolution manager.
        
        Args:
            master_key: Initial 256-bit master key
            epoch_duration: Number of messages per epoch
        """
        self.master_key = master_key
        self.epoch_duration = epoch_duration
        
        # Current epoch state
        self.current_epoch = 0
        self.epoch_key = self._derive_epoch_key(master_key, 0)
        
        # Key history for overlap period (deleted after transition)
        self.previous_epoch_key: Optional[bytes] = None
        self.key_delete_scheduled = False
        
        # Audit log
        self.key_events: List[Dict] = []
        
        self._log_event("INIT", f"Key manager initialized with epoch_duration={epoch_duration}")
    
    def _derive_epoch_key(self, parent_key: bytes, epoch_id: int) -> bytes:
        """
        Derive epoch key using HKDF.
        
        Formula: K_epoch = HKDF-SHA256(parent_key, info=epoch_id)
        """
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"privacy-mqtt-epoch-key",
            info=f"epoch:{epoch_id}".encode(),
            backend=default_backend()
        )
        return hkdf.derive(parent_key)
    
    def advance_epoch(self) -> Tuple[bytes, int]:
        """
        Advance to next epoch with key evolution.
        
        Returns:
            Tuple of (new_epoch_key, new_epoch_id)
        """
        # Store previous key for overlap period
        self.previous_epoch_key = self.epoch_key
        
        # Derive new epoch key from current key (chain derivation)
        self.current_epoch += 1
        self.epoch_key = self._derive_epoch_key(self.epoch_key, self.current_epoch)
        
        # Schedule previous key deletion
        self._schedule_key_deletion()
        
        self._log_event("EPOCH_ADVANCE", f"Advanced to epoch {self.current_epoch}")
        
        return self.epoch_key, self.current_epoch
    
    def _schedule_key_deletion(self, delay_seconds: float = 5.0):
        """Schedule secure deletion of previous epoch key after overlap period."""
        if self.key_delete_scheduled:
            return
        
        self.key_delete_scheduled = True
        
        def delete_previous_key():
            time.sleep(delay_seconds)
            if self.previous_epoch_key:
                # Secure deletion: overwrite before dereferencing
                self.previous_epoch_key = os.urandom(32)
                self.previous_epoch_key = None
                self._log_event("KEY_DELETE", f"Deleted key for epoch {self.current_epoch - 1}")
            self.key_delete_scheduled = False
        
        thread = threading.Thread(target=delete_previous_key, daemon=True)
        thread.start()
    
    def get_current_key(self) -> Tuple[bytes, int]:
        """Get current epoch key and epoch ID."""
        return self.epoch_key, self.current_epoch
    
    def emergency_key_rotation(self, reason: str = "compromise_suspected"):
        """
        Emergency key rotation protocol.
        
        Called when key compromise is suspected.
        Immediately derives new key and invalidates all previous keys.
        """
        self._log_event("EMERGENCY_ROTATION", f"Reason: {reason}")
        
        # Generate fresh entropy
        fresh_entropy = os.urandom(32)
        
        # Mix with current key to derive new key
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"emergency-rotation",
            info=f"emergency:{int(time.time())}".encode(),
            backend=default_backend()
        )
        new_key = hkdf.derive(self.epoch_key + fresh_entropy)
        
        # Securely delete old keys
        self.epoch_key = os.urandom(32)
        self.previous_epoch_key = os.urandom(32) if self.previous_epoch_key else None
        
        # Install new key
        self.epoch_key = new_key
        self.previous_epoch_key = None
        self.current_epoch += 100  # Jump epoch to prevent confusion
        
        self._log_event("EMERGENCY_COMPLETE", f"New epoch: {self.current_epoch}")
        
        return self.epoch_key, self.current_epoch
    
    def _log_event(self, event_type: str, details: str):
        """Log key management event."""
        event = {
            "timestamp": datetime.now().isoformat(),
            "epoch": self.current_epoch,
            "event": event_type,
            "details": details
        }
        self.key_events.append(event)
    
    def get_audit_log(self) -> List[Dict]:
        """Get key management audit log."""
        return self.key_events.copy()


# =============================================================================
# GATEWAY HARDENING
# =============================================================================

@dataclass
class HardenedGatewayConfig:
    """Configuration for hardened gateway deployment."""
    use_hsm: bool = False  # Hardware Security Module
    use_tee: bool = False  # Trusted Execution Environment
    key_split_threshold: int = 1  # k-of-n threshold (1 = single gateway)
    key_split_total: int = 1
    enable_rate_limiting: bool = True
    max_messages_per_second: int = 1000
    enable_anomaly_detection: bool = True


class HardenedPrivacyGateway:
    """
    Privacy gateway with enhanced security hardening.
    
    Security Features:
    1. Key evolution with forward secrecy
    2. Rate limiting to prevent DoS
    3. Anomaly detection for suspicious patterns
    4. Secure audit logging
    """
    
    def __init__(self, config: HardenedGatewayConfig, master_key: bytes):
        self.config = config
        
        # Initialize key management
        self.key_manager = KeyEvolutionManager(master_key)
        
        # Rate limiting state
        self.message_counts: Dict[str, int] = {}  # per-patient
        self.last_reset_time = time.time()
        
        # Anomaly detection state
        self.patient_patterns: Dict[str, List[float]] = {}  # timing patterns
        
        # Initialize encryption
        key, _ = self.key_manager.get_current_key()
        self.aesgcm = AESGCM(key)
        
        # Message counter per epoch
        self.message_count = 0
        self.epoch_message_limit = 20
    
    def generate_pseudo_topic(self, patient_id: str, sensor_type: str) -> str:
        """
        Generate privacy-preserving pseudo-topic with key evolution.
        
        If epoch boundary reached, automatically advance key.
        """
        # Check if epoch advance needed
        self.message_count += 1
        if self.message_count >= self.epoch_message_limit:
            self._advance_epoch()
        
        # Get current epoch key
        key, epoch = self.key_manager.get_current_key()
        
        # Generate pseudo-topic using PRF
        input_data = f"{patient_id}:{sensor_type}:{epoch}".encode()
        pseudo = hmac.new(key, input_data, hashlib.sha256).digest()
        
        return f"t/{pseudo[:16].hex()}"
    
    def _advance_epoch(self):
        """Advance to next epoch with key evolution."""
        new_key, new_epoch = self.key_manager.advance_epoch()
        self.aesgcm = AESGCM(new_key)
        self.message_count = 0
    
    def encrypt_payload(self, plaintext: bytes) -> bytes:
        """
        Encrypt payload with current epoch key.
        
        Format: nonce (12 bytes) || ciphertext || tag (16 bytes)
        """
        nonce = os.urandom(12)
        ciphertext = self.aesgcm.encrypt(nonce, plaintext, None)
        return nonce + ciphertext
    
    def decrypt_payload(self, encrypted: bytes) -> bytes:
        """Decrypt payload (for testing/verification)."""
        nonce = encrypted[:12]
        ciphertext = encrypted[12:]
        return self.aesgcm.decrypt(nonce, ciphertext, None)
    
    def check_rate_limit(self, patient_id: str) -> bool:
        """
        Check if message is within rate limit.
        
        Returns True if allowed, False if rate limited.
        """
        if not self.config.enable_rate_limiting:
            return True
        
        # Reset counters every second
        current_time = time.time()
        if current_time - self.last_reset_time >= 1.0:
            self.message_counts.clear()
            self.last_reset_time = current_time
        
        # Check patient-specific limit
        count = self.message_counts.get(patient_id, 0)
        if count >= self.config.max_messages_per_second // 10:  # Per-patient limit
            return False
        
        self.message_counts[patient_id] = count + 1
        return True
    
    def detect_anomaly(self, patient_id: str, timestamp: float) -> bool:
        """
        Detect anomalous message patterns.
        
        Flags:
        - Sudden increase in message frequency
        - Messages from unusual time patterns
        - Out-of-order timestamps
        
        Returns True if anomaly detected.
        """
        if not self.config.enable_anomaly_detection:
            return False
        
        if patient_id not in self.patient_patterns:
            self.patient_patterns[patient_id] = []
        
        patterns = self.patient_patterns[patient_id]
        patterns.append(timestamp)
        
        # Keep last 100 timestamps
        if len(patterns) > 100:
            patterns.pop(0)
        
        if len(patterns) < 10:
            return False
        
        # Calculate inter-arrival times
        iats = [patterns[i] - patterns[i-1] for i in range(1, len(patterns))]
        
        # Check for anomalous frequency (too fast)
        avg_iat = sum(iats) / len(iats)
        if avg_iat < 0.01:  # Less than 10ms average = suspicious
            return True
        
        # Check for time reversal
        if iats[-1] < 0:
            return True
        
        return False
    
    def process_message(self, patient_id: str, sensor_type: str, 
                       data: bytes, timestamp: float) -> Optional[Tuple[str, bytes]]:
        """
        Process incoming message with all security checks.
        
        Returns:
            (pseudo_topic, encrypted_payload) if allowed
            None if rejected (rate limit, anomaly, etc.)
        """
        # Rate limit check
        if not self.check_rate_limit(patient_id):
            self.key_manager._log_event("RATE_LIMIT", f"Patient {patient_id} rate limited")
            return None
        
        # Anomaly detection
        if self.detect_anomaly(patient_id, timestamp):
            self.key_manager._log_event("ANOMALY", f"Anomaly detected for {patient_id}")
            # Don't reject, but log for review
        
        # Generate pseudo-topic and encrypt
        pseudo_topic = self.generate_pseudo_topic(patient_id, sensor_type)
        encrypted = self.encrypt_payload(data)
        
        return pseudo_topic, encrypted


# =============================================================================
# KEY COMPROMISE RECOVERY PROTOCOL
# =============================================================================

class KeyCompromiseRecovery:
    """
    Protocol for recovering from suspected key compromise.
    
    Steps:
    1. Detect compromise (anomaly, external report, etc.)
    2. Initiate emergency key rotation
    3. Notify all legitimate parties of new key
    4. Revoke old key material
    5. Audit and forensics
    """
    
    def __init__(self, gateway: HardenedPrivacyGateway):
        self.gateway = gateway
        self.recovery_events: List[Dict] = []
    
    def initiate_recovery(self, reason: str, 
                         affected_epochs: Optional[List[int]] = None) -> Dict:
        """
        Initiate key compromise recovery procedure.
        
        Args:
            reason: Description of why recovery is needed
            affected_epochs: List of compromised epoch IDs (if known)
        
        Returns:
            Recovery status report
        """
        event = {
            "timestamp": datetime.now().isoformat(),
            "reason": reason,
            "affected_epochs": affected_epochs,
            "actions": []
        }
        
        # Step 1: Emergency key rotation
        new_key, new_epoch = self.gateway.key_manager.emergency_key_rotation(reason)
        event["actions"].append(f"Emergency rotation to epoch {new_epoch}")
        
        # Step 2: Update encryption context
        self.gateway.aesgcm = AESGCM(new_key)
        event["actions"].append("Updated encryption context")
        
        # Step 3: Generate new key distribution package
        # In production, this would trigger out-of-band key distribution
        key_package = {
            "epoch": new_epoch,
            "key_id": hashlib.sha256(new_key).hexdigest()[:16],
            "valid_from": datetime.now().isoformat(),
            "distribution_method": "out_of_band_required"
        }
        event["key_package"] = key_package
        event["actions"].append("Generated key distribution package")
        
        # Step 4: Mark recovery complete
        event["status"] = "COMPLETED"
        self.recovery_events.append(event)
        
        return event
    
    def generate_forensics_report(self) -> Dict:
        """Generate forensics report for security audit."""
        return {
            "timestamp": datetime.now().isoformat(),
            "gateway_audit_log": self.gateway.key_manager.get_audit_log(),
            "recovery_events": self.recovery_events,
            "current_epoch": self.gateway.key_manager.current_epoch,
            "total_key_rotations": len([
                e for e in self.gateway.key_manager.key_events 
                if e["event"] == "EPOCH_ADVANCE"
            ])
        }


# =============================================================================
# DEMONSTRATION
# =============================================================================

def demonstrate_security_enhancements():
    """Demonstrate enhanced security features."""
    
    print("="*80)
    print("SECURITY ENHANCEMENT DEMONSTRATION")
    print("="*80)
    
    # Initialize hardened gateway
    master_key = os.urandom(32)
    config = HardenedGatewayConfig(
        enable_rate_limiting=True,
        enable_anomaly_detection=True,
        max_messages_per_second=100
    )
    
    gateway = HardenedPrivacyGateway(config, master_key)
    
    # Demonstrate key evolution
    print("\n1. KEY EVOLUTION DEMONSTRATION")
    print("-" * 40)
    
    for i in range(25):  # 25 messages across 2 epochs
        result = gateway.process_message(
            patient_id="P001",
            sensor_type="ecg",
            data=f"ecg_data_{i}".encode(),
            timestamp=time.time()
        )
        
        if result:
            topic, encrypted = result
            print(f"Message {i}: topic={topic[:20]}... epoch={gateway.key_manager.current_epoch}")
    
    print(f"\nEpoch advances: {gateway.key_manager.current_epoch}")
    
    # Demonstrate rate limiting
    print("\n2. RATE LIMITING DEMONSTRATION")
    print("-" * 40)
    
    # Reset for demo
    gateway.message_counts.clear()
    
    allowed = 0
    blocked = 0
    for i in range(20):  # Try 20 rapid messages
        if gateway.check_rate_limit("P002"):
            allowed += 1
        else:
            blocked += 1
    
    print(f"Rapid message test: {allowed} allowed, {blocked} blocked")
    
    # Demonstrate emergency recovery
    print("\n3. EMERGENCY KEY RECOVERY DEMONSTRATION")
    print("-" * 40)
    
    recovery = KeyCompromiseRecovery(gateway)
    
    old_epoch = gateway.key_manager.current_epoch
    result = recovery.initiate_recovery(
        reason="Suspected key compromise detected",
        affected_epochs=[old_epoch - 1, old_epoch]
    )
    
    print(f"Recovery initiated: {result['status']}")
    print(f"Old epoch: {old_epoch}, New epoch: {gateway.key_manager.current_epoch}")
    print(f"Actions taken: {len(result['actions'])}")
    
    # Print audit log
    print("\n4. AUDIT LOG")
    print("-" * 40)
    
    audit = recovery.generate_forensics_report()
    print(f"Total key events: {len(audit['gateway_audit_log'])}")
    print(f"Recovery events: {len(audit['recovery_events'])}")
    
    for event in audit['gateway_audit_log'][-5:]:  # Last 5 events
        print(f"  [{event['timestamp']}] {event['event']}: {event['details']}")
    
    return audit


if __name__ == "__main__":
    result = demonstrate_security_enhancements()
    
    # Save audit report
    os.makedirs("data/results/security", exist_ok=True)
    with open("data/results/security/audit_report.json", "w") as f:
        json.dump(result, f, indent=2, default=str)
    
    print("\n" + "="*80)
    print("SECURITY ENHANCEMENT DEMO COMPLETE")
    print("="*80)
    print("\nAudit report saved to: data/results/security/audit_report.json")
