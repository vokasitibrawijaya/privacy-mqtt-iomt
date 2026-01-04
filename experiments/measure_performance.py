"""
Performance Measurement Script for Privacy-Aware MQTT
Measures throughput, latency, CPU usage, and privacy metrics at scale
"""

import json
import time
import statistics
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from config.config import ExperimentConfig, EXPERIMENT_SCENARIOS
from metrics.metrics_collector import MetricsCollector, MetricsComparator


def measure_docker_stats() -> Dict[str, Any]:
    """Measure Docker container resource usage"""
    import subprocess
    
    try:
        result = subprocess.run(
            ['docker', 'stats', '--no-stream', '--format', 
             'json={{json .}}'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        containers = []
        for line in result.stdout.strip().split('\n'):
            if line:
                try:
                    containers.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        
        return {
            'timestamp': datetime.now().isoformat(),
            'containers': containers,
            'total_containers': len(containers)
        }
    except Exception as e:
        print(f"Error measuring Docker stats: {e}")
        return {}


def analyze_experiment_results(results_file: Path) -> Dict[str, Any]:
    """Analyze experiment results and compute performance metrics"""
    
    with open(results_file, 'r') as f:
        data = json.load(f)
    
    baseline = data.get('baseline', {})
    privacy = data.get('namespace_privacy', {})
    
    # Calculate improvements
    topic_improvement = privacy['privacy']['topic_diversity'] / baseline['privacy']['topic_diversity']
    clientid_improvement = privacy['privacy']['clientid_diversity'] / baseline['privacy']['clientid_diversity']
    
    # Calculate overhead
    comp_overhead = privacy['overhead']['computation_overhead_ms'] - baseline['overhead']['computation_overhead_ms']
    latency_overhead = privacy['qos']['avg_latency_ms'] - baseline['qos']['avg_latency_ms']
    
    # Duplication during overlap
    overlap_duplication = privacy['overhead']['overlap_duplication_rate'] * 100
    
    analysis = {
        'privacy_improvement': {
            'topic_diversity': {
                'baseline': baseline['privacy']['topic_diversity'],
                'privacy': privacy['privacy']['topic_diversity'],
                'improvement_factor': round(topic_improvement, 2)
            },
            'clientid_diversity': {
                'baseline': baseline['privacy']['clientid_diversity'],
                'privacy': privacy['privacy']['clientid_diversity'],
                'improvement_factor': round(clientid_improvement, 2)
            },
            'topic_entropy': {
                'baseline': round(baseline['privacy']['anonymity_entropy'], 4),
                'privacy': round(privacy['privacy']['anonymity_entropy'], 4)
            }
        },
        'performance_overhead': {
            'computation_ms': {
                'baseline': round(baseline['overhead']['computation_overhead_ms'], 6),
                'privacy': round(privacy['overhead']['computation_overhead_ms'], 6),
                'overhead_ms': round(comp_overhead, 6),
                'overhead_percentage': round((comp_overhead / baseline['overhead']['computation_overhead_ms']) * 100, 2) if baseline['overhead']['computation_overhead_ms'] > 0 else 0
            },
            'latency_ms': {
                'baseline': round(baseline['qos']['avg_latency_ms'], 4),
                'privacy': round(privacy['qos']['avg_latency_ms'], 4),
                'overhead_ms': round(latency_overhead, 4),
                'clinical_threshold_ms': 100,
                'within_threshold': privacy['qos']['avg_latency_ms'] < 100
            },
            'throughput': {
                'baseline_msg_per_sec': baseline['qos']['messages_per_second'],
                'privacy_msg_per_sec': privacy['qos']['messages_per_second']
            }
        },
        'overlap_cost': {
            'duplication_percentage': round(overlap_duplication, 2),
            'bandwidth_increase': f"{overlap_duplication:.1f}% during rotation"
        },
        'assessment': {
            'privacy_gain': 'HIGH' if topic_improvement >= 3.0 else 'MEDIUM',
            'overhead': 'NEGLIGIBLE' if comp_overhead < 1.0 else 'MODERATE',
            'qos_maintained': privacy['qos']['avg_latency_ms'] < 100,
            'production_ready': (
                topic_improvement >= 3.0 and 
                comp_overhead < 5.0 and 
                privacy['qos']['avg_latency_ms'] < 100
            )
        }
    }
    
    return analysis


def generate_performance_report(
    analysis: Dict[str, Any],
    docker_stats: Dict[str, Any],
    num_gateways: int
) -> str:
    """Generate formatted performance report"""
    
    report = f"""
================================================================================
PERFORMANCE MEASUREMENT REPORT - Privacy-Aware MQTT for IoMT
================================================================================
Measurement Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Configuration: {num_gateways} Gateway Instances

PRIVACY IMPROVEMENT
-------------------
Topic Diversity:
  Baseline:    {analysis['privacy_improvement']['topic_diversity']['baseline']} unique topics
  Privacy:     {analysis['privacy_improvement']['topic_diversity']['privacy']} unique topics
  Improvement: {analysis['privacy_improvement']['topic_diversity']['improvement_factor']}x

ClientID Diversity:
  Baseline:    {analysis['privacy_improvement']['clientid_diversity']['baseline']} unique IDs
  Privacy:     {analysis['privacy_improvement']['clientid_diversity']['privacy']} unique IDs
  Improvement: {analysis['privacy_improvement']['clientid_diversity']['improvement_factor']}x

Topic Entropy:
  Baseline:    {analysis['privacy_improvement']['topic_entropy']['baseline']}
  Privacy:     {analysis['privacy_improvement']['topic_entropy']['privacy']}

PERFORMANCE OVERHEAD
--------------------
Computation Time:
  Baseline:    {analysis['performance_overhead']['computation_ms']['baseline']} ms
  Privacy:     {analysis['performance_overhead']['computation_ms']['privacy']} ms
  Overhead:    {analysis['performance_overhead']['computation_ms']['overhead_ms']} ms ({analysis['performance_overhead']['computation_ms']['overhead_percentage']}%)

Latency:
  Baseline:    {analysis['performance_overhead']['latency_ms']['baseline']} ms
  Privacy:     {analysis['performance_overhead']['latency_ms']['privacy']} ms
  Overhead:    {analysis['performance_overhead']['latency_ms']['overhead_ms']} ms
  Threshold:   {analysis['performance_overhead']['latency_ms']['clinical_threshold_ms']} ms (Clinical requirement)
  Status:      {'✓ WITHIN THRESHOLD' if analysis['performance_overhead']['latency_ms']['within_threshold'] else '✗ EXCEEDS THRESHOLD'}

Throughput:
  Baseline:    {analysis['performance_overhead']['throughput']['baseline_msg_per_sec']:,} msg/sec
  Privacy:     {analysis['performance_overhead']['throughput']['privacy_msg_per_sec']:,} msg/sec

OVERLAP COST
------------
Duplication:   {analysis['overlap_cost']['duplication_percentage']}% during epoch rotation
Impact:        {analysis['overlap_cost']['bandwidth_increase']}

INFRASTRUCTURE (Docker)
-----------------------
Total Containers:  {docker_stats.get('total_containers', 'N/A')}
Gateway Instances: {num_gateways}

ASSESSMENT
----------
Privacy Gain:      {analysis['assessment']['privacy_gain']}
Overhead:          {analysis['assessment']['overhead']}
QoS Maintained:    {'YES ✓' if analysis['assessment']['qos_maintained'] else 'NO ✗'}
Production Ready:  {'YES ✓' if analysis['assessment']['production_ready'] else 'NO ✗'}

CONCLUSION
----------
"""
    
    if analysis['assessment']['production_ready']:
        report += """
The Privacy-Aware MQTT system demonstrates:
✓ Significant privacy improvement ({topic_imp}x topic diversity)
✓ Negligible performance overhead ({overhead}ms computation)
✓ QoS maintained within clinical requirements (<100ms latency)
✓ System is PRODUCTION READY for IoMT deployment

RECOMMENDATION: Proceed with large-scale testing (N=100-10,000 patients)
""".format(
            topic_imp=analysis['privacy_improvement']['topic_diversity']['improvement_factor'],
            overhead=analysis['performance_overhead']['computation_ms']['overhead_ms']
        )
    else:
        report += "\nFurther optimization required before production deployment.\n"
    
    report += "\n" + "=" * 80 + "\n"
    
    return report


def main():
    """Main performance measurement script"""
    
    print("=" * 80)
    print("PRIVACY-AWARE MQTT PERFORMANCE MEASUREMENT")
    print("=" * 80)
    print()
    
    # Find latest experiment results
    results_dir = Path(__file__).parent.parent / 'data' / 'results'
    results_files = sorted(results_dir.glob('quick_experiment_*.json'), reverse=True)
    
    if not results_files:
        print("ERROR: No experiment results found!")
        print("Please run experiments first: python experiments/quick_experiment.py")
        return
    
    latest_results = results_files[0]
    print(f"Analyzing results from: {latest_results.name}")
    print()
    
    # Analyze experiment results
    print("Computing privacy and performance metrics...")
    analysis = analyze_experiment_results(latest_results)
    
    # Measure Docker stats
    print("Measuring Docker container stats...")
    docker_stats = measure_docker_stats()
    
    # Count gateway instances
    num_gateways = sum(1 for c in docker_stats.get('containers', []) 
                      if 'gateway' in c.get('Name', '').lower())
    
    if num_gateways == 0:
        num_gateways = 1  # Default if Docker stats unavailable
    
    print(f"Detected {num_gateways} gateway instances")
    print()
    
    # Generate report
    report = generate_performance_report(analysis, docker_stats, num_gateways)
    
    # Save report
    report_file = results_dir / f'performance_report_{int(time.time())}.txt'
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    # Save analysis JSON
    analysis_file = results_dir / f'performance_analysis_{int(time.time())}.json'
    with open(analysis_file, 'w') as f:
        json.dump({
            'analysis': analysis,
            'docker_stats': docker_stats,
            'num_gateways': num_gateways,
            'timestamp': datetime.now().isoformat()
        }, f, indent=2)
    
    # Print report
    print(report)
    
    print(f"\nReport saved to: {report_file}")
    print(f"Analysis data saved to: {analysis_file}")
    print()


if __name__ == '__main__':
    main()
