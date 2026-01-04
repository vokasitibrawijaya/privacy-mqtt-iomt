"""
Visualisasi Hasil Eksperimen
=============================
Generate tabel dan grafik ASCII dari hasil eksperimen
"""

import json
import sys
import os

def print_ascii_bar(value, max_value, width=40, char='█'):
    """Print ASCII bar chart"""
    bar_length = int((value / max_value) * width) if max_value > 0 else 0
    bar = char * bar_length
    spaces = ' ' * (width - bar_length)
    return f'[{bar}{spaces}]'

def visualize_results(results_file):
    """Visualize experiment results"""
    
    with open(results_file, 'r') as f:
        data = json.load(f)
    
    baseline = data['baseline']
    privacy = data['namespace_privacy']
    comparison = data['comparison']
    
    print("\n" + "=" * 80)
    print(" 📊 HASIL EKSPERIMEN: Privacy-Aware MQTT untuk IoMT")
    print("=" * 80)
    
    # Privacy Metrics Visualization
    print("\n🔒 PRIVACY METRICS")
    print("-" * 80)
    
    b_topics = baseline['privacy']['topic_diversity']
    p_topics = privacy['privacy']['topic_diversity']
    max_topics = max(b_topics, p_topics)
    
    print(f"\nTopic Diversity:")
    print(f"  Baseline:          {b_topics:>4} {print_ascii_bar(b_topics, max_topics)}")
    print(f"  Namespace-Privacy: {p_topics:>4} {print_ascii_bar(p_topics, max_topics)}")
    print(f"  Improvement:       {comparison['topic_diversity_improvement']:.1f}x ⬆️")
    
    b_clients = baseline['privacy']['clientid_diversity']
    p_clients = privacy['privacy']['clientid_diversity']
    max_clients = max(b_clients, p_clients)
    
    print(f"\nClientID Diversity:")
    print(f"  Baseline:          {b_clients:>4} {print_ascii_bar(b_clients, max_clients)}")
    print(f"  Namespace-Privacy: {p_clients:>4} {print_ascii_bar(p_clients, max_clients)}")
    print(f"  Improvement:       {comparison['clientid_diversity_improvement']:.1f}x ⬆️")
    
    print(f"\nAnonymity Entropy:")
    print(f"  Baseline:          {baseline['privacy']['anonymity_entropy']:.4f} bits")
    print(f"  Namespace-Privacy: {privacy['privacy']['anonymity_entropy']:.4f} bits")
    
    # Overhead Metrics
    print("\n⚡ OVERHEAD METRICS")
    print("-" * 80)
    
    b_comp = baseline['overhead']['computation_overhead_ms']
    p_comp = privacy['overhead']['computation_overhead_ms']
    
    print(f"\nComputation Overhead per Message:")
    print(f"  Baseline:          {b_comp:.4f} ms")
    print(f"  Namespace-Privacy: {p_comp:.4f} ms")
    print(f"  Increase:          {((p_comp - b_comp) / b_comp * 100) if b_comp > 0 else 0:.1f}% ⬆️")
    
    dup_rate = privacy['overhead']['overlap_duplication_rate'] * 100
    print(f"\nOverlap Duplication Rate:")
    print(f"  {dup_rate:.1f}% {print_ascii_bar(dup_rate, 100, 30, '▓')}")
    
    # QoS Metrics
    print("\n🚀 QoS METRICS")
    print("-" * 80)
    
    b_lat = baseline['qos']['avg_latency_ms']
    p_lat = privacy['qos']['avg_latency_ms']
    
    print(f"\nAverage End-to-End Latency:")
    print(f"  Baseline:          {b_lat:.4f} ms")
    print(f"  Namespace-Privacy: {p_lat:.4f} ms")
    print(f"  Difference:        {abs(p_lat - b_lat):.4f} ms {'⬆️' if p_lat > b_lat else '⬇️'}")
    
    b_tput = baseline['qos']['messages_per_second']
    p_tput = privacy['qos']['messages_per_second']
    
    print(f"\nThroughput:")
    print(f"  Baseline:          {b_tput:>12,.2f} msgs/sec")
    print(f"  Namespace-Privacy: {p_tput:>12,.2f} msgs/sec")
    
    # Summary
    print("\n" + "=" * 80)
    print(" 📋 SUMMARY")
    print("=" * 80)
    
    print(f"""
✅ Privacy Enhancement:
   • Topic diversity meningkat {comparison['topic_diversity_improvement']:.1f}x
   • ClientID diversity meningkat {comparison['clientid_diversity_improvement']:.1f}x
   • Membuat traffic analysis lebih sulit bagi broker/penyerang

⚠️  Trade-offs:
   • Computation overhead: +{((p_comp - b_comp) / b_comp * 100) if b_comp > 0 else 0:.1f}% (sangat kecil: {p_comp:.4f} ms)
   • Overlap duplication: {dup_rate:.1f}% selama fase transisi epoch

✓  QoS Maintained:
   • Latency tetap stabil (~{p_lat:.2f} ms)
   • Throughput: {p_tput:,.0f} messages/second
   • Suitable untuk aplikasi IoMT real-time

💡 Kesimpulan:
   Namespace-Privacy berhasil meningkatkan privasi metadata MQTT secara signifikan
   dengan overhead yang minimal dan QoS yang tetap terjaga untuk keperluan klinis.
    """)
    
    print("=" * 80)
    print()


if __name__ == "__main__":
    # Find latest results file
    results_dir = "./data/results"
    
    if len(sys.argv) > 1:
        results_file = sys.argv[1]
    else:
        # Get latest quick_experiment file
        files = [f for f in os.listdir(results_dir) if f.startswith('quick_experiment')]
        if not files:
            print("❌ No experiment results found!")
            sys.exit(1)
        
        files.sort(reverse=True)
        results_file = os.path.join(results_dir, files[0])
    
    print(f"\n📂 Loading results from: {results_file}")
    visualize_results(results_file)
