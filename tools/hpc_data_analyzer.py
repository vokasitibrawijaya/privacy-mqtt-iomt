"""
HPC Results Analyzer
Analyzes large-scale HPC experiment results and generates comprehensive statistics
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Any
import matplotlib.pyplot as plt
import matplotlib
from datetime import datetime

matplotlib.rcParams['font.family'] = 'serif'
matplotlib.rcParams['font.size'] = 10
matplotlib.rcParams['figure.dpi'] = 300


def load_hpc_results(results_dir: Path) -> List[Dict[str, Any]]:
    """Load all HPC experiment results"""
    results = []
    for json_file in sorted(results_dir.glob('hpc_experiment_N*.json')):
        with open(json_file, 'r') as f:
            data = json.load(f)
            results.append(data)
    return results


def extract_metrics_table(results: List[Dict[str, Any]]) -> pd.DataFrame:
    """Extract metrics into pandas DataFrame"""
    
    rows = []
    for exp in results:
        config = exp.get('configuration', {})
        baseline = exp.get('baseline', {})
        privacy = exp.get('namespace_privacy', {})
        
        n_patients = config.get('num_patients', 0)
        
        row = {
            'N_Patients': n_patients,
            
            # Privacy metrics
            'Baseline_Topics': baseline.get('privacy', {}).get('topic_diversity', 0),
            'Privacy_Topics': privacy.get('privacy', {}).get('topic_diversity', 0),
            'Topic_Gain': privacy.get('privacy', {}).get('topic_diversity', 1) / 
                         max(baseline.get('privacy', {}).get('topic_diversity', 1), 1),
            
            'Baseline_ClientID': baseline.get('privacy', {}).get('clientid_diversity', 0),
            'Privacy_ClientID': privacy.get('privacy', {}).get('clientid_diversity', 0),
            'ClientID_Gain': privacy.get('privacy', {}).get('clientid_diversity', 1) / 
                            max(baseline.get('privacy', {}).get('clientid_diversity', 1), 1),
            
            # Performance metrics
            'Baseline_Latency_ms': baseline.get('qos', {}).get('avg_latency_ms', 0),
            'Privacy_Latency_ms': privacy.get('qos', {}).get('avg_latency_ms', 0),
            'Latency_Overhead_ms': privacy.get('qos', {}).get('avg_latency_ms', 0) - 
                                  baseline.get('qos', {}).get('avg_latency_ms', 0),
            
            'Baseline_Throughput': baseline.get('qos', {}).get('messages_per_second', 0),
            'Privacy_Throughput': privacy.get('qos', {}).get('messages_per_second', 0),
            'Throughput_Reduction_%': (1 - privacy.get('qos', {}).get('messages_per_second', 0) / 
                                      max(baseline.get('qos', {}).get('messages_per_second', 1), 1)) * 100,
            
            # Overhead metrics
            'Computation_Overhead_us': privacy.get('overhead', {}).get('computation_overhead_ms', 0) * 1000,
            'Bandwidth_Overhead_%': privacy.get('overhead', {}).get('overlap_duplication_rate', 0) * 100,
            
            # QoS validation
            'Packet_Loss_%': privacy.get('qos', {}).get('packet_loss_rate', 0) * 100,
            'Latency_Within_Threshold': privacy.get('qos', {}).get('avg_latency_ms', 0) < 100,
        }
        
        rows.append(row)
    
    df = pd.DataFrame(rows)
    return df.sort_values('N_Patients')


def generate_comprehensive_report(df: pd.DataFrame, output_file: Path):
    """Generate comprehensive text report"""
    
    report = []
    report.append("=" * 80)
    report.append("HPC EXPERIMENT RESULTS - COMPREHENSIVE ANALYSIS")
    report.append("=" * 80)
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"Total Experiments: {len(df)}")
    report.append("")
    
    # Privacy Improvement Summary
    report.append("1. PRIVACY IMPROVEMENT SUMMARY")
    report.append("-" * 80)
    report.append(f"{'Scale':<15} {'Topic Gain':<15} {'ClientID Gain':<15} {'Status':<20}")
    report.append("-" * 80)
    
    for _, row in df.iterrows():
        n = int(row['N_Patients'])
        topic_gain = row['Topic_Gain']
        clientid_gain = row['ClientID_Gain']
        status = "✓ EXCELLENT" if topic_gain >= 5.0 else "○ GOOD" if topic_gain >= 3.0 else "△ MODERATE"
        
        report.append(f"N={n:<12} {topic_gain:<15.2f}x {clientid_gain:<15.2f}x {status:<20}")
    
    report.append("")
    report.append(f"Average Topic Diversity Gain: {df['Topic_Gain'].mean():.2f}x")
    report.append(f"Average ClientID Diversity Gain: {df['ClientID_Gain'].mean():.2f}x")
    report.append("")
    
    # Performance Overhead Summary
    report.append("2. PERFORMANCE OVERHEAD SUMMARY")
    report.append("-" * 80)
    report.append(f"{'Scale':<15} {'Latency (ms)':<15} {'Overhead (ms)':<15} {'Status':<20}")
    report.append("-" * 80)
    
    for _, row in df.iterrows():
        n = int(row['N_Patients'])
        latency = row['Privacy_Latency_ms']
        overhead = row['Latency_Overhead_ms']
        status = "✓ ACCEPTABLE" if latency < 100 else "✗ EXCEEDS THRESHOLD"
        
        report.append(f"N={n:<12} {latency:<15.4f} {overhead:<15.4f} {status:<20}")
    
    report.append("")
    report.append(f"Average Latency Overhead: {df['Latency_Overhead_ms'].mean():.4f} ms")
    report.append(f"Clinical Threshold: 100 ms")
    report.append(f"All Tests Within Threshold: {df['Latency_Within_Threshold'].all()}")
    report.append("")
    
    # Throughput Analysis
    report.append("3. THROUGHPUT ANALYSIS")
    report.append("-" * 80)
    report.append(f"{'Scale':<15} {'Baseline (msg/s)':<20} {'Privacy (msg/s)':<20} {'Reduction %':<15}")
    report.append("-" * 80)
    
    for _, row in df.iterrows():
        n = int(row['N_Patients'])
        baseline_tp = row['Baseline_Throughput']
        privacy_tp = row['Privacy_Throughput']
        reduction = row['Throughput_Reduction_%']
        
        report.append(f"N={n:<12} {baseline_tp:<20,.0f} {privacy_tp:<20,.0f} {reduction:<15.1f}")
    
    report.append("")
    report.append(f"Average Throughput Reduction: {df['Throughput_Reduction_%'].mean():.1f}%")
    report.append("")
    
    # Computational Overhead
    report.append("4. COMPUTATIONAL OVERHEAD")
    report.append("-" * 80)
    report.append(f"Average Computation Overhead: {df['Computation_Overhead_us'].mean():.2f} μs")
    report.append(f"Max Computation Overhead: {df['Computation_Overhead_us'].max():.2f} μs")
    report.append(f"Min Computation Overhead: {df['Computation_Overhead_us'].min():.2f} μs")
    report.append("")
    
    # Bandwidth Overhead
    report.append("5. BANDWIDTH OVERHEAD (OVERLAP)")
    report.append("-" * 80)
    report.append(f"Average Overlap Duplication: {df['Bandwidth_Overhead_%'].mean():.2f}%")
    report.append(f"Max Overlap Duplication: {df['Bandwidth_Overhead_%'].max():.2f}%")
    report.append("")
    
    # QoS Validation
    report.append("6. QoS VALIDATION")
    report.append("-" * 80)
    report.append(f"Average Packet Loss: {df['Packet_Loss_%'].mean():.4f}%")
    report.append(f"Max Packet Loss: {df['Packet_Loss_%'].max():.4f}%")
    report.append(f"All Tests Zero Packet Loss: {(df['Packet_Loss_%'] == 0).all()}")
    report.append("")
    
    # Scalability Assessment
    report.append("7. SCALABILITY ASSESSMENT")
    report.append("-" * 80)
    
    if len(df) >= 2:
        # Linear regression for latency vs scale
        from scipy import stats
        log_n = np.log10(df['N_Patients'])
        latency = df['Privacy_Latency_ms']
        
        slope, intercept, r_value, p_value, std_err = stats.linregress(log_n, latency)
        
        report.append(f"Latency Scaling: log-linear fit")
        report.append(f"  Slope: {slope:.4f} ms per 10x scale increase")
        report.append(f"  R²: {r_value**2:.4f}")
        report.append(f"  Projected latency at N=10,000: {slope * np.log10(10000) + intercept:.2f} ms")
        report.append("")
    
    # Overall Verdict
    report.append("8. OVERALL ASSESSMENT")
    report.append("-" * 80)
    
    all_latency_ok = df['Latency_Within_Threshold'].all()
    all_packet_loss_ok = (df['Packet_Loss_%'] == 0).all()
    avg_privacy_gain = df['Topic_Gain'].mean()
    
    if all_latency_ok and all_packet_loss_ok and avg_privacy_gain >= 5.0:
        verdict = "✓ PRODUCTION READY - All metrics within acceptable ranges"
    elif all_latency_ok and all_packet_loss_ok:
        verdict = "○ ACCEPTABLE - Performance good, privacy moderate"
    else:
        verdict = "△ NEEDS OPTIMIZATION - Some metrics require improvement"
    
    report.append(f"Verdict: {verdict}")
    report.append("")
    report.append("Key Achievements:")
    report.append(f"  ✓ Privacy improvement: {avg_privacy_gain:.1f}x average")
    report.append(f"  ✓ Latency overhead: {df['Latency_Overhead_ms'].mean():.4f} ms average")
    report.append(f"  ✓ QoS maintained: {'Yes' if all_latency_ok and all_packet_loss_ok else 'Partial'}")
    report.append("")
    
    report.append("=" * 80)
    
    # Write to file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report))
    
    return '\n'.join(report)


def generate_hpc_figures(df: pd.DataFrame, output_dir: Path):
    """Generate figures for HPC results"""
    
    output_dir.mkdir(exist_ok=True, parents=True)
    
    print("\nGenerating HPC analysis figures...")
    
    # Figure: Privacy Gain vs Scale
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(df['N_Patients'], df['Topic_Gain'], marker='o', linewidth=2, 
            markersize=8, label='Topic Diversity Gain', color='#4ECDC4')
    ax.plot(df['N_Patients'], df['ClientID_Gain'], marker='s', linewidth=2,
            markersize=8, label='ClientID Diversity Gain', color='#FF6B6B')
    ax.axhline(y=5.0, color='green', linestyle='--', linewidth=2, label='Target (5x)')
    ax.set_xlabel('Number of Patients (N)', fontsize=12, weight='bold')
    ax.set_ylabel('Privacy Improvement Factor (x)', fontsize=12, weight='bold')
    ax.set_title('Privacy Gain Across Different Scales', fontsize=14, weight='bold')
    ax.set_xscale('log')
    ax.grid(True, alpha=0.3, linestyle='--')
    ax.legend(fontsize=10, loc='best')
    plt.tight_layout()
    fig.savefig(output_dir / 'hpc_privacy_scaling.png', dpi=300, bbox_inches='tight')
    fig.savefig(output_dir / 'hpc_privacy_scaling.pdf', format='pdf', bbox_inches='tight')
    plt.close(fig)
    print("  ✓ Generated: hpc_privacy_scaling.png/pdf")
    
    # Figure: Latency vs Scale
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(df['N_Patients'], df['Baseline_Latency_ms'], marker='o', linewidth=2,
            markersize=8, label='Baseline', color='#FF6B6B', alpha=0.7)
    ax.plot(df['N_Patients'], df['Privacy_Latency_ms'], marker='s', linewidth=2,
            markersize=8, label='Privacy-Enhanced', color='#4ECDC4')
    ax.axhline(y=100, color='orange', linestyle='--', linewidth=2, 
               label='Clinical Threshold (100 ms)')
    ax.set_xlabel('Number of Patients (N)', fontsize=12, weight='bold')
    ax.set_ylabel('Average Latency (ms)', fontsize=12, weight='bold')
    ax.set_title('Latency Scalability Analysis', fontsize=14, weight='bold')
    ax.set_xscale('log')
    ax.grid(True, alpha=0.3, linestyle='--')
    ax.legend(fontsize=10, loc='best')
    plt.tight_layout()
    fig.savefig(output_dir / 'hpc_latency_scaling.png', dpi=300, bbox_inches='tight')
    fig.savefig(output_dir / 'hpc_latency_scaling.pdf', format='pdf', bbox_inches='tight')
    plt.close(fig)
    print("  ✓ Generated: hpc_latency_scaling.png/pdf")
    
    # Figure: Throughput Comparison
    fig, ax = plt.subplots(figsize=(10, 6))
    x = np.arange(len(df))
    width = 0.35
    ax.bar(x - width/2, df['Baseline_Throughput'], width, label='Baseline',
           color='#FF6B6B', alpha=0.8, edgecolor='black')
    ax.bar(x + width/2, df['Privacy_Throughput'], width, label='Privacy-Enhanced',
           color='#4ECDC4', alpha=0.8, edgecolor='black')
    ax.set_xlabel('Scale', fontsize=12, weight='bold')
    ax.set_ylabel('Throughput (messages/second)', fontsize=12, weight='bold')
    ax.set_title('Throughput Comparison Across Scales', fontsize=14, weight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([f"N={int(n)}" for n in df['N_Patients']])
    ax.legend(fontsize=10)
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    plt.tight_layout()
    fig.savefig(output_dir / 'hpc_throughput_comparison.png', dpi=300, bbox_inches='tight')
    fig.savefig(output_dir / 'hpc_throughput_comparison.pdf', format='pdf', bbox_inches='tight')
    plt.close(fig)
    print("  ✓ Generated: hpc_throughput_comparison.png/pdf")
    
    # Figure: Overhead Analysis
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    
    ax1.plot(df['N_Patients'], df['Latency_Overhead_ms'], marker='o',
             linewidth=2, markersize=8, color='#4ECDC4')
    ax1.set_xlabel('Number of Patients (N)', fontsize=11, weight='bold')
    ax1.set_ylabel('Latency Overhead (ms)', fontsize=11, weight='bold')
    ax1.set_title('Latency Overhead vs Scale', fontsize=12, weight='bold')
    ax1.set_xscale('log')
    ax1.grid(True, alpha=0.3, linestyle='--')
    
    ax2.plot(df['N_Patients'], df['Bandwidth_Overhead_%'], marker='s',
             linewidth=2, markersize=8, color='#FF6B6B')
    ax2.set_xlabel('Number of Patients (N)', fontsize=11, weight='bold')
    ax2.set_ylabel('Bandwidth Overhead (%)', fontsize=11, weight='bold')
    ax2.set_title('Bandwidth Overhead (Overlap) vs Scale', fontsize=12, weight='bold')
    ax2.set_xscale('log')
    ax2.grid(True, alpha=0.3, linestyle='--')
    
    fig.suptitle('Overhead Analysis Across Scales', fontsize=14, weight='bold', y=1.00)
    plt.tight_layout()
    fig.savefig(output_dir / 'hpc_overhead_analysis.png', dpi=300, bbox_inches='tight')
    fig.savefig(output_dir / 'hpc_overhead_analysis.pdf', format='pdf', bbox_inches='tight')
    plt.close(fig)
    print("  ✓ Generated: hpc_overhead_analysis.png/pdf")
    
    print(f"\nAll figures saved to: {output_dir}")


def main():
    """Main execution"""
    
    # Results directory
    results_dir = Path(__file__).parent.parent / 'data' / 'results'
    
    # Load HPC results
    print("Loading HPC experiment results...")
    results = load_hpc_results(results_dir)
    
    if not results:
        print("\n" + "=" * 80)
        print("NO HPC RESULTS FOUND")
        print("=" * 80)
        print("\nExpected files: hpc_experiment_N100.json, hpc_experiment_N1000.json, etc.")
        print(f"Search directory: {results_dir}")
        print("\nTo generate HPC results:")
        print("  1. Deploy to HPC cluster (see HPC_DEPLOYMENT_GUIDE.md)")
        print("  2. Run experiments for N=100, 1000, 10000")
        print("  3. Copy result JSON files to data/results/")
        print("  4. Re-run this analyzer")
        return
    
    print(f"Found {len(results)} HPC experiment results\n")
    
    # Extract metrics
    df = extract_metrics_table(results)
    
    # Generate comprehensive report
    output_dir = Path(__file__).parent.parent / 'dissertation'
    report_file = output_dir / 'HPC_ANALYSIS_REPORT.txt'
    
    report = generate_comprehensive_report(df, report_file)
    print(report)
    print(f"\nReport saved to: {report_file}")
    
    # Generate figures
    figures_dir = output_dir / 'figures'
    generate_hpc_figures(df, figures_dir)
    
    # Save DataFrame as CSV for further analysis
    csv_file = output_dir / 'hpc_metrics_summary.csv'
    df.to_csv(csv_file, index=False)
    print(f"\nMetrics CSV saved to: {csv_file}")
    
    print("\n" + "=" * 80)
    print("HPC ANALYSIS COMPLETE!")
    print("=" * 80)
    print("\nGenerated files:")
    print(f"  - {report_file}")
    print(f"  - {csv_file}")
    print(f"  - {figures_dir}/hpc_*.png (4 figures)")
    print(f"  - {figures_dir}/hpc_*.pdf (4 figures)")
    print("\nNext steps:")
    print("  1. Review comprehensive report")
    print("  2. Include figures in BAB 4 dissertation")
    print("  3. Use metrics for BAB 5 conclusions")


if __name__ == '__main__':
    main()
