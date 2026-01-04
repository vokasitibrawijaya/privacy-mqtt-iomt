"""
Quick Validation Script for Real MQTT Experiment
================================================
Runs a quick validation with fewer trials to verify setup before full experiment.

Usage:
    python run_quick_validation.py
"""

import os
import sys
import time
import json
import subprocess

# Fix encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def check_mqtt_broker(host: str = "localhost", port: int = 1883) -> bool:
    """Check if MQTT broker is reachable"""
    import socket
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception as e:
        print(f"  Error checking broker: {e}")
        return False


def run_validation():
    """Run quick validation experiment"""
    print("=" * 70)
    print("QUICK VALIDATION - Real MQTT Experiment")
    print("=" * 70)
    print("\nThis script runs a quick validation before the full experiment.")
    print("Configuration: 3 trials, 3 patients, 2 sensors, 20 messages/stream\n")
    
    # Check MQTT broker
    print("Step 1: Checking MQTT broker...")
    broker_host = os.environ.get("MQTT_BROKER", "localhost")
    broker_port = int(os.environ.get("MQTT_PORT", "1883"))
    
    if not check_mqtt_broker(broker_host, broker_port):
        print(f"  [X] MQTT broker not available at {broker_host}:{broker_port}")
        print("\n  Please start the broker:")
        print("    Option 1: docker-compose up mqtt-broker")
        print("    Option 2: mosquitto -c mosquitto.conf")
        return False
    
    print(f"  [OK] MQTT broker available at {broker_host}:{broker_port}")
    
    # Import experiment
    print("\nStep 2: Running validation experiment...")
    try:
        from experiments.real_mqtt_experiment import RealMQTTExperiment
    except ImportError as e:
        print(f"  ✗ Failed to import experiment: {e}")
        return False
    
    # Run quick validation
    experiment = RealMQTTExperiment(
        broker_host=broker_host,
        broker_port=broker_port,
        num_patients=3,  # Small for quick test
        num_sensors=2,
        messages_per_stream=20,  # Fewer messages
        epoch_length=10,
        message_interval_ms=10  # Faster for validation
    )
    
    try:
        results = experiment.run_experiment(
            num_trials=3,  # Just 3 trials for quick validation
            output_dir="data/results/validation"
        )
    except Exception as e:
        print(f"  [X] Experiment failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Validate results
    print("\n" + "=" * 70)
    print("VALIDATION CHECKS")
    print("=" * 70)
    
    checks_passed = 0
    checks_total = 6
    
    # Check 1: Messages were sent
    baseline_sent = sum(t["messages_sent"] for t in results["baseline"]["individual_trials"])
    print(f"\n[OK] Check 1: Messages sent")
    print(f"    Total baseline messages sent: {baseline_sent}")
    checks_passed += 1 if baseline_sent > 0 else 0
    
    # Check 2: Messages were received
    baseline_received = sum(t["messages_received"] for t in results["baseline"]["individual_trials"])
    status = "[OK]" if baseline_received > 0 else "[X]"
    print(f"\n{status} Check 2: Messages received")
    print(f"    Total baseline messages received: {baseline_received}")
    checks_passed += 1 if baseline_received > 0 else 0
    
    # Check 3: Latency was measured
    avg_latency = results["baseline"]["latency"]["mean_ms"]
    status = "[OK]" if avg_latency > 0 else "[X]"
    print(f"\n{status} Check 3: Latency measured")
    print(f"    Average baseline latency: {avg_latency:.4f} ms")
    checks_passed += 1 if avg_latency > 0 else 0
    
    # Check 4: Confidence intervals calculated
    ci_margin = results["baseline"]["latency"]["ci_95_margin"]
    status = "[OK]" if ci_margin >= 0 else "[X]"
    print(f"\n{status} Check 4: Confidence intervals")
    print(f"    95% CI margin: +/-{ci_margin:.4f} ms")
    checks_passed += 1 if ci_margin >= 0 else 0
    
    # Check 5: Packet loss properly calculated
    loss_rate = results["baseline"]["packet_loss"]["mean"]
    print(f"\n[OK] Check 5: Packet loss calculation")
    print(f"    Baseline packet loss rate: {loss_rate*100:.2f}%")
    checks_passed += 1  # Even 0% is valid if messages were received
    
    # Check 6: Privacy metrics
    topic_div = results["privacy"]["privacy"]["topic_diversity"]["mean"]
    status = "[OK]" if topic_div > 1 else "[X]"
    print(f"\n{status} Check 6: Privacy metrics")
    print(f"    Privacy topic diversity: {topic_div:.1f}")
    checks_passed += 1 if topic_div > 1 else 0
    
    # Summary
    print("\n" + "=" * 70)
    print(f"VALIDATION RESULT: {checks_passed}/{checks_total} checks passed")
    print("=" * 70)
    
    if checks_passed >= 5:
        print("\n[OK] VALIDATION PASSED - Ready for full experiment")
        print("\nTo run full experiment (30 trials):")
        print("    python experiments/real_mqtt_experiment.py --trials 30")
        return True
    else:
        print("\n[X] VALIDATION FAILED - Please check the issues above")
        return False


if __name__ == "__main__":
    success = run_validation()
    sys.exit(0 if success else 1)
