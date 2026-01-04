"""
Quick Experiment Runner
=======================
Versi singkat untuk demonstrasi dan testing cepat
"""

import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.crypto import KeyMaterial, gen_pseudo_topic, encrypt_payload
from src.metrics import MetricsCollector, MetricsComparator


def run_quick_experiment():
    """Run a quick synchronous experiment for demo"""
    print("=" * 60)
    print("QUICK EXPERIMENT: Baseline vs Namespace-Privacy")
    print("=" * 60)
    
    keys = KeyMaterial.generate()
    
    # Parameters
    num_patients = 5
    num_sensors = 3
    num_messages = 100  # Quick test
    epoch_length = 20   # Messages per epoch
    
    patient_ids = [f"patient_{i:03d}" for i in range(num_patients)]
    sensor_types = ["spo2", "blood_pressure", "temperature"]
    
    # === BASELINE EXPERIMENT ===
    print("\n--- Running BASELINE ---")
    baseline_metrics = MetricsCollector("baseline_quick", "baseline")
    
    baseline_start = time.time()
    for msg_num in range(num_messages):
        for pid in patient_ids:
            for sid in sensor_types:
                # Baseline: static semantic topic
                topic = f"hospital/ward1/{pid}/{sid}"
                client_id = "gateway_baseline"
                
                # Simulate payload
                payload = f"data_{pid}_{sid}_{msg_num}".encode()
                encrypted = encrypt_payload(keys.control_encrypt_key, payload)
                
                start = time.time()
                # Simulate processing
                _ = len(encrypted)
                comp_time = time.time() - start
                
                baseline_metrics.record_message_sent(
                    patient_id=pid,
                    sensor_id=sid,
                    topic=topic,
                    client_id=client_id,
                    payload_size=len(encrypted),
                    computation_time=comp_time,
                    epoch=0
                )
                baseline_metrics.record_baseline_message_size(len(encrypted))
                baseline_metrics.record_message_received(latency_ms=5 + comp_time*1000)
    
    baseline_duration = time.time() - baseline_start
    baseline_result = baseline_metrics.collect_all_metrics()
    print(f"  Duration: {baseline_duration:.2f}s")
    print(f"  Total messages: {baseline_metrics.total_messages_sent}")
    print(f"  Unique topics: {len(baseline_metrics.unique_topics)}")
    print(f"  Unique ClientIDs: {len(baseline_metrics.unique_client_ids)}")
    
    # === NAMESPACE-PRIVACY EXPERIMENT ===
    print("\n--- Running NAMESPACE-PRIVACY ---")
    privacy_metrics = MetricsCollector("privacy_quick", "namespace_privacy")
    
    # Track epochs
    stream_epochs = {(pid, sid): 0 for pid in patient_ids for sid in sensor_types}
    stream_msg_count = {(pid, sid): 0 for pid in patient_ids for sid in sensor_types}
    client_epoch = 0
    
    privacy_start = time.time()
    for msg_num in range(num_messages):
        # Check ClientID rotation
        if msg_num > 0 and msg_num % (epoch_length * 2) == 0:
            client_epoch += 1
        
        from src.crypto import gen_pseudo_client_id
        client_id = gen_pseudo_client_id(keys.clientid_key, "gw_privacy", client_epoch)
        
        for pid in patient_ids:
            for sid in sensor_types:
                key = (pid, sid)
                
                # Check topic rotation
                stream_msg_count[key] += 1
                if stream_msg_count[key] > epoch_length:
                    stream_epochs[key] += 1
                    stream_msg_count[key] = 1
                
                current_epoch = stream_epochs[key]
                
                # Generate pseudo-topic
                topic = gen_pseudo_topic(keys.topic_key, pid, sid, current_epoch)
                
                # Simulate payload
                payload = f"data_{pid}_{sid}_{msg_num}".encode()
                encrypted = encrypt_payload(keys.control_encrypt_key, payload)
                
                start = time.time()
                # Simulate processing (PRF computation)
                _ = gen_pseudo_topic(keys.topic_key, pid, sid, current_epoch)
                comp_time = time.time() - start
                
                # Check if in overlap period (first few messages of new epoch)
                is_duplicate = stream_msg_count[key] <= 3 and current_epoch > 0
                
                privacy_metrics.record_message_sent(
                    patient_id=pid,
                    sensor_id=sid,
                    topic=topic,
                    client_id=client_id,
                    payload_size=len(encrypted),
                    computation_time=comp_time,
                    is_duplicate=is_duplicate,
                    epoch=current_epoch
                )
                
                # Also send to old topic during overlap
                if is_duplicate:
                    old_topic = gen_pseudo_topic(keys.topic_key, pid, sid, current_epoch - 1)
                    privacy_metrics.record_message_sent(
                        patient_id=pid,
                        sensor_id=sid,
                        topic=old_topic,
                        client_id=client_id,
                        payload_size=len(encrypted),
                        computation_time=comp_time,
                        is_duplicate=True,
                        epoch=current_epoch - 1
                    )
                
                privacy_metrics.record_baseline_message_size(len(encrypted))
                privacy_metrics.record_message_received(latency_ms=5 + comp_time*1000)
    
    privacy_duration = time.time() - privacy_start
    privacy_result = privacy_metrics.collect_all_metrics()
    print(f"  Duration: {privacy_duration:.2f}s")
    print(f"  Total messages: {privacy_metrics.total_messages_sent}")
    print(f"  Unique topics: {len(privacy_metrics.unique_topics)}")
    print(f"  Unique ClientIDs: {len(privacy_metrics.unique_client_ids)}")
    print(f"  Max epoch reached: {max(stream_epochs.values())}")
    
    # === COMPARISON ===
    print("\n" + "=" * 60)
    print("COMPARISON RESULTS")
    print("=" * 60)
    
    print("\n--- Privacy Metrics ---")
    print(f"{'Metric':<30} {'Baseline':>15} {'Privacy':>15} {'Improvement':>15}")
    print("-" * 75)
    
    b_priv = baseline_result.privacy
    p_priv = privacy_result.privacy
    
    print(f"{'Topic Diversity':<30} {b_priv.topic_diversity:>15} {p_priv.topic_diversity:>15} {p_priv.topic_diversity/b_priv.topic_diversity if b_priv.topic_diversity > 0 else 0:>14.2f}x")
    print(f"{'ClientID Diversity':<30} {b_priv.clientid_diversity:>15} {p_priv.clientid_diversity:>15} {p_priv.clientid_diversity/b_priv.clientid_diversity if b_priv.clientid_diversity > 0 else 0:>14.2f}x")
    print(f"{'Anonymity Entropy':<30} {b_priv.anonymity_entropy:>15.4f} {p_priv.anonymity_entropy:>15.4f}")
    print(f"{'Attack Success Rate':<30} {b_priv.attack_success_rate:>15.4f} {p_priv.attack_success_rate:>15.4f}")
    
    print("\n--- Unlinkability Metrics ---")
    b_unlink = baseline_result.unlinkability
    p_unlink = privacy_result.unlinkability
    print(f"{'Cross-Epoch Linkability':<30} {b_unlink.cross_epoch_linkability:>15.4f} {p_unlink.cross_epoch_linkability:>15.4f}")
    print(f"{'Traceable Rate':<30} {b_unlink.traceable_rate:>15.4f} {p_unlink.traceable_rate:>15.4f}")
    print(f"{'Unlinkability Score':<30} {b_unlink.unlinkability_score:>15.4f} {p_unlink.unlinkability_score:>15.4f}")
    
    print("\n--- Overhead Metrics ---")
    b_over = baseline_result.overhead
    p_over = privacy_result.overhead
    print(f"{'Computation Overhead (ms)':<30} {b_over.computation_overhead_ms:>15.4f} {p_over.computation_overhead_ms:>15.4f}")
    print(f"{'Overlap Duplication Rate':<30} {b_over.overlap_duplication_rate:>15.4f} {p_over.overlap_duplication_rate:>15.4f}")
    
    print("\n--- QoS Metrics ---")
    b_qos = baseline_result.qos
    p_qos = privacy_result.qos
    print(f"{'Avg Latency (ms)':<30} {b_qos.avg_latency_ms:>15.4f} {p_qos.avg_latency_ms:>15.4f}")
    print(f"{'Messages/sec':<30} {b_qos.messages_per_second:>15.2f} {p_qos.messages_per_second:>15.2f}")
    print(f"{'Packet Loss Rate':<30} {b_qos.packet_loss_rate:>15.4f} {p_qos.packet_loss_rate:>15.4f}")
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    topic_improvement = p_priv.topic_diversity / b_priv.topic_diversity if b_priv.topic_diversity > 0 else 0
    print(f"\nNamespace-Privacy meningkatkan topic diversity sebesar {topic_improvement:.1f}x")
    print(f"dengan overhead duplikasi {p_over.overlap_duplication_rate*100:.1f}% selama fase overlap.")
    
    # Save results
    os.makedirs("./data/results", exist_ok=True)
    
    results = {
        "baseline": baseline_result.to_dict(),
        "namespace_privacy": privacy_result.to_dict(),
        "comparison": {
            "topic_diversity_improvement": topic_improvement,
            "clientid_diversity_improvement": p_priv.clientid_diversity / b_priv.clientid_diversity if b_priv.clientid_diversity > 0 else 0,
            "overhead_duplication_rate": p_over.overlap_duplication_rate
        }
    }
    
    output_file = f"./data/results/quick_experiment_{int(time.time())}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\nResults saved to: {output_file}")
    
    return results


if __name__ == "__main__":
    run_quick_experiment()
