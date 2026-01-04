"""
Crypto Utilities for Privacy-Aware MQTT
========================================
Implementasi PRF (Pseudorandom Function) untuk generasi pseudo-topic dan pseudo-ClientID
Sesuai dengan protokol di BAB Desain Sistem
"""

import hashlib
import hmac
import base64
import secrets
from typing import Tuple
from dataclasses import dataclass


def prf(key: bytes, data: bytes) -> bytes:
    """
    Pseudorandom Function menggunakan HMAC-SHA256
    
    Args:
        key: Kunci simetris (32 bytes recommended)
        data: Data input untuk PRF
    
    Returns:
        Output PRF (32 bytes)
    """
    return hmac.new(key, data, hashlib.sha256).digest()


def encode_to_topic(token: bytes, prefix: str = "t") -> str:
    """
    Encode token PRF ke format topic MQTT yang valid
    Menggunakan base64url untuk kompatibilitas MQTT topic
    
    Args:
        token: Token dari PRF
        prefix: Prefix topic (default "t")
    
    Returns:
        String topic MQTT (misal: "t/abc123def456...")
    """
    # Ambil 16 bytes pertama untuk topic yang lebih pendek
    truncated = token[:16]
    encoded = base64.urlsafe_b64encode(truncated).decode('ascii').rstrip('=')
    return f"{prefix}/{encoded}"


def gen_pseudo_topic(key: bytes, patient_id: str, stream_id: str, epoch: int) -> str:
    """
    Generate pseudo-topic untuk stream tertentu pada epoch tertentu
    Implementasi dari: pseudo_topic = Encode(PRF_K(PID || SID || epoch))
    
    Args:
        key: Kunci simetris untuk topic
        patient_id: ID pasien internal (PID)
        stream_id: ID stream/sensor (SID) - misal "ecg", "spo2"
        epoch: Nomor epoch saat ini
    
    Returns:
        Pseudo-topic string
    """
    # Gabungkan PID || SID || epoch
    data = f"{patient_id}|{stream_id}|{epoch}".encode('utf-8')
    token = prf(key, data)
    return encode_to_topic(token)


def gen_pseudo_client_id(key: bytes, gateway_id: str, epoch: int) -> str:
    """
    Generate pseudo-ClientID untuk gateway pada epoch tertentu
    Implementasi dari: client_id = "gw_" || HEX(PRF_K(GATEWAY_ID || epoch)[0:8])
    
    Args:
        key: Kunci simetris untuk ClientID
        gateway_id: ID gateway internal
        epoch: Nomor epoch global
    
    Returns:
        Pseudo-ClientID string
    """
    data = f"{gateway_id}|{epoch}".encode('utf-8')
    token = prf(key, data)
    # Ambil 8 bytes pertama dan encode ke hex
    hex_part = token[:8].hex()
    return f"gw_{hex_part}"


def generate_shared_keys() -> Tuple[bytes, bytes]:
    """
    Generate pasangan kunci untuk topic dan ClientID
    Kunci ini harus dibagi secara aman antara Gateway dan Backend
    
    Returns:
        Tuple (topic_key, clientid_key)
    """
    topic_key = secrets.token_bytes(32)
    clientid_key = secrets.token_bytes(32)
    return topic_key, clientid_key


def derive_control_channel_key(master_key: bytes, purpose: str) -> bytes:
    """
    Derive kunci untuk control channel dari master key
    
    Args:
        master_key: Master key
        purpose: Tujuan kunci (misal "control_encrypt", "control_auth")
    
    Returns:
        Derived key
    """
    return prf(master_key, purpose.encode('utf-8'))


@dataclass
class KeyMaterial:
    """Container untuk semua key material yang dibutuhkan"""
    topic_key: bytes
    clientid_key: bytes
    control_encrypt_key: bytes
    control_auth_key: bytes
    
    @classmethod
    def generate(cls) -> 'KeyMaterial':
        """Generate fresh key material"""
        master_key = secrets.token_bytes(32)
        topic_key, clientid_key = generate_shared_keys()
        control_encrypt_key = derive_control_channel_key(master_key, "control_encrypt")
        control_auth_key = derive_control_channel_key(master_key, "control_auth")
        
        return cls(
            topic_key=topic_key,
            clientid_key=clientid_key,
            control_encrypt_key=control_encrypt_key,
            control_auth_key=control_auth_key
        )
    
    def to_hex_dict(self) -> dict:
        """Export keys sebagai hex strings untuk konfigurasi"""
        return {
            "topic_key": self.topic_key.hex(),
            "clientid_key": self.clientid_key.hex(),
            "control_encrypt_key": self.control_encrypt_key.hex(),
            "control_auth_key": self.control_auth_key.hex()
        }
    
    @classmethod
    def from_hex_dict(cls, data: dict) -> 'KeyMaterial':
        """Import keys dari hex strings"""
        return cls(
            topic_key=bytes.fromhex(data["topic_key"]),
            clientid_key=bytes.fromhex(data["clientid_key"]),
            control_encrypt_key=bytes.fromhex(data["control_encrypt_key"]),
            control_auth_key=bytes.fromhex(data["control_auth_key"])
        )


# Simple payload encryption (AES-GCM untuk production, ini simplified)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def encrypt_payload(key: bytes, plaintext: bytes, associated_data: bytes = b"") -> bytes:
    """
    Encrypt payload menggunakan AES-GCM
    
    Args:
        key: 32-byte key
        plaintext: Data untuk dienkripsi
        associated_data: Additional authenticated data (opsional)
    
    Returns:
        nonce (12 bytes) + ciphertext + tag
    """
    aesgcm = AESGCM(key)
    nonce = secrets.token_bytes(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data)
    return nonce + ciphertext


def decrypt_payload(key: bytes, ciphertext: bytes, associated_data: bytes = b"") -> bytes:
    """
    Decrypt payload yang dienkripsi dengan AES-GCM
    
    Args:
        key: 32-byte key  
        ciphertext: nonce + ciphertext + tag
        associated_data: Additional authenticated data
    
    Returns:
        Plaintext
    """
    aesgcm = AESGCM(key)
    nonce = ciphertext[:12]
    actual_ciphertext = ciphertext[12:]
    return aesgcm.decrypt(nonce, actual_ciphertext, associated_data)


if __name__ == "__main__":
    # Test functions
    print("=== Testing Crypto Utilities ===\n")
    
    # Generate keys
    keys = KeyMaterial.generate()
    print(f"Generated keys:\n{keys.to_hex_dict()}\n")
    
    # Test pseudo-topic generation
    pid = "patient_001"
    sid = "ecg"
    for epoch in range(3):
        topic = gen_pseudo_topic(keys.topic_key, pid, sid, epoch)
        print(f"Epoch {epoch}: {topic}")
    
    print()
    
    # Test pseudo-ClientID generation
    gw_id = "gateway_01"
    for epoch in range(3):
        client_id = gen_pseudo_client_id(keys.clientid_key, gw_id, epoch)
        print(f"Epoch {epoch}: ClientID = {client_id}")
    
    print()
    
    # Test encryption
    test_data = b"ECG reading: 72 bpm"
    encrypted = encrypt_payload(keys.control_encrypt_key, test_data)
    decrypted = decrypt_payload(keys.control_encrypt_key, encrypted)
    print(f"Original: {test_data}")
    print(f"Encrypted length: {len(encrypted)} bytes")
    print(f"Decrypted: {decrypted}")
    print(f"Match: {test_data == decrypted}")
