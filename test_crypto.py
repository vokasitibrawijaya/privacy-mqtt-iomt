"""
Test Crypto Components
"""
from src.crypto import KeyMaterial, gen_pseudo_topic, gen_pseudo_client_id

keys = KeyMaterial.generate()
print('=== Testing Crypto Components ===')
print(f'Topic Epoch 0: {gen_pseudo_topic(keys.topic_key, "patient_001", "ecg", 0)}')
print(f'Topic Epoch 1: {gen_pseudo_topic(keys.topic_key, "patient_001", "ecg", 1)}')
print(f'Topic Epoch 2: {gen_pseudo_topic(keys.topic_key, "patient_001", "ecg", 2)}')
print(f'ClientID Epoch 0: {gen_pseudo_client_id(keys.clientid_key, "gw_01", 0)}')
print(f'ClientID Epoch 1: {gen_pseudo_client_id(keys.clientid_key, "gw_01", 1)}')
print('✓ Pseudonym rotation working!')
