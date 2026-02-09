#!/usr/bin/env python3
"""
Compare all models across both evaluation sets and generate visualizations.

This script:
1. Analyzes APIGen-on-APIGen predictions (existing)
2. Analyzes APIGen-on-Local-Data predictions (from eval_all_hf_models.py)
3. Creates comparison tables
4. Generates graphs (success rates, domain breakdown, impossibility breakdown)
"""

import json
import subprocess
import sys
from pathlib import Path

try:
    import matplotlib.pyplot as plt
    import numpy as np
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("Warning: matplotlib not available. Graphs will be skipped.")

APIGEN_PREDICTIONS = {
    "32b_epoch1": "training/models/apigen_model_32B/predictions_epoch1.jsonl",
    "32b_epoch3": "training/models/apigen_model_32B/predictions_epoch3.jsonl",
    "32b_epoch5": "training/models/apigen_model_32B/predictions_epoch5.jsonl",
    "14b_epoch1": "training/models/apigen_model_14B/predictions_epoch1.jsonl",
    "14b_epoch3": "training/models/apigen_model_14B/predictions_epoch3.jsonl",
    "14b_epoch5": "training/models/apigen_model_14B/predictions_epoch5.jsonl",
    "7b_checkpoint38": "training/models/apigen_model_7B/predictions_checkpoint-38.jsonl",
    "7b_checkpoint114": "training/models/apigen_model_7B/predictions_checkpoint-114.jsonl",
    "7b_checkpoint185": "training/models/apigen_model_7B/predictions_checkpoint-185.jsonl",
}

LOCAL_DATA_PREDICTIONS = {
    "32b_epoch1": "training/models/apigen_model_32B/predictions_local_data_32b_epoch1.jsonl",
    "32b_epoch3": "training/models/apigen_model_32B/predictions_local_data_32b_epoch3.jsonl",
    "32b_epoch5": "training/models/apigen_model_32B/predictions_local_data_32b_epoch5.jsonl",
    "14b_epoch1": "training/models/apigen_model_14B/predictions_local_data_14b_epoch1.jsonl",
    "14b_epoch3": "training/models/apigen_model_14B/predictions_local_data_14b_epoch3.jsonl",
    "14b_epoch5": "training/models/apigen_model_14B/predictions_local_data_14b_epoch5.jsonl",
    "7b_checkpoint38": "training/models/apigen_model_7B/predictions_local_data_7b_checkpoint38.jsonl",
    "7b_checkpoint114": "training/models/apigen_model_7B/predictions_local_data_7b_checkpoint114.jsonl",
    "7b_checkpoint185": "training/models/apigen_model_7B/predictions_local_data_7b_checkpoint185.jsonl",
}


def analyze_set(predictions_dict, eval_set_name, output_dir):
    """Analyze a set of predictions."""
    results = {}
    missing_files = []
    
    for label, pred_path in predictions_dict.items():
        path = Path(pred_path)
        if not path.exists():
            missing_files.append((label, pred_path))
            continue
        
        print(f"Analyzing {eval_set_name}: {label}...")
        cmd = [
            sys.executable,
            "training/compute_metrics.py",
            "--predictions", str(path),
            "--label", f"{label}_{eval_set_name}",
            "--format", "json"
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            data = json.loads(result.stdout)
            label_key = f"{label}_{eval_set_name}"
            if label_key in data:
                results[label] = data[label_key]
            else:
                results[label] = data
        except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
            print(f"  Error analyzing {label}: {e}")
            continue
    
    if missing_files:
        print(f"\nMissing files for {eval_set_name}:")
        for label, path in missing_files:
            print(f"  {label}: {path}")
    
    return results


def create_comparison_table(apigen_results, local_results):
    """Create a comparison table across both eval sets."""
    print("\n" + "=" * 120)
    print("COMPARISON: APIGen Test vs Local Data Test")
    print("=" * 120)
    
    models = sorted(set(list(apigen_results.keys()) + list(local_results.keys())))
    
    print(f"\n{'Model':<25} {'Eval Set':<15} {'Success Rate':<15} {'Valid Syntax':<15} {'Type Match':<15} {'Tool Name':<15} {'Tool Args':<15}")
    print("-" * 120)
    
    for model in models:
        apigen = apigen_results.get(model, {})
        local = local_results.get(model, {})
        
        if apigen and "overall_success_rate" in apigen:
            raw_apigen = apigen.get("raw_metrics", {})
            print(f"{model:<25} {'APIGen Test':<15} {apigen['overall_success_rate']:<15.4f} {raw_apigen.get('valid_syntax', 0):<15.4f} {raw_apigen.get('type_match', 0):<15.4f} {raw_apigen.get('tool_name_match', 0):<15.4f} {raw_apigen.get('tool_args_match', 0):<15.4f}")
        
        if local and "overall_success_rate" in local:
            raw_local = local.get("raw_metrics", {})
            print(f"{model:<25} {'Local Data':<15} {local['overall_success_rate']:<15.4f} {raw_local.get('valid_syntax', 0):<15.4f} {raw_local.get('type_match', 0):<15.4f} {raw_local.get('tool_name_match', 0):<15.4f} {raw_local.get('tool_args_match', 0):<15.4f}")
    
    print("\n" + "=" * 120)
    
    print("\nBy Domain (Local Data only):")
    print(f"{'Model':<25} {'Domain':<20} {'Success Rate':<15} {'Count':<10}")
    print("-" * 70)
    
    for model in sorted(local_results.keys()):
        local = local_results.get(model, {})
        if local and "by_domain" in local:
            for domain, stats in sorted(local["by_domain"].items()):
                print(f"{model:<25} {domain:<20} {stats['success_rate']:<15.4f} {stats['total']:<10}")
    
    print("\n" + "=" * 120)
    
    print("\nBy Impossibility (Local Data only):")
    print(f"{'Model':<25} {'Type':<15} {'Success Rate':<15} {'Count':<10}")
    print("-" * 65)
    
    for model in sorted(local_results.keys()):
        local = local_results.get(model, {})
        if local and "by_impossibility" in local:
            for key, stats in sorted(local["by_impossibility"].items()):
                print(f"{model:<25} {key:<15} {stats['success_rate']:<15.4f} {stats['total']:<10}")


def create_graphs(apigen_results, local_results, output_dir):
    """Create visualization graphs."""
    if not HAS_MATPLOTLIB:
        return
    
    output_dir = Path(output_dir)
    
    models = sorted(set(list(apigen_results.keys()) + list(local_results.keys())))
    if not models:
        return
    
    apigen_rates = []
    local_rates = []
    model_labels = []
    
    for model in models:
        apigen = apigen_results.get(model, {})
        local = local_results.get(model, {})
        
        if apigen and "overall_success_rate" in apigen:
            apigen_rates.append(apigen["overall_success_rate"])
        else:
            apigen_rates.append(0)
        
        if local and "overall_success_rate" in local:
            local_rates.append(local["overall_success_rate"])
        else:
            local_rates.append(0)
        
        model_labels.append(model)
    
    x = np.arange(len(model_labels))
    width = 0.35
    
    fig, ax = plt.subplots(figsize=(14, 8))
    bars1 = ax.bar(x - width/2, apigen_rates, width, label='APIGen Test', alpha=0.8)
    bars2 = ax.bar(x + width/2, local_rates, width, label='Local Data Test', alpha=0.8)
    
    ax.set_xlabel('Model & Epoch', fontsize=12)
    ax.set_ylabel('Success Rate', fontsize=12)
    ax.set_title('Success Rate Comparison: APIGen Test vs Local Data Test', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(model_labels, rotation=45, ha='right')
    ax.legend()
    ax.set_ylim([0, 1])
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_dir / 'success_rate_comparison.png', dpi=300, bbox_inches='tight')
    print(f"Graph saved: {output_dir / 'success_rate_comparison.png'}")
    plt.close()
    
    if local_results:
        create_domain_graphs(local_results, output_dir)
        create_impossibility_graphs(local_results, output_dir)


def create_domain_graphs(local_results, output_dir):
    """Create graphs for domain breakdown."""
    if not HAS_MATPLOTLIB:
        return
    
    domain_data = {}
    for model, result in local_results.items():
        if "by_domain" not in result:
            continue
        for domain, stats in result["by_domain"].items():
            if domain not in domain_data:
                domain_data[domain] = []
            domain_data[domain].append((model, stats["success_rate"]))
    
    if not domain_data:
        return
    
    domains = sorted(domain_data.keys())
    models = sorted(set(model for domain_stats in domain_data.values() for model, _ in domain_stats))
    
    fig, ax = plt.subplots(figsize=(14, 8))
    
    x = np.arange(len(models))
    width = 0.8 / len(domains)
    
    for i, domain in enumerate(domains):
        rates = [next((rate for m, rate in domain_data[domain] if m == model), 0) for model in models]
        offset = (i - len(domains)/2) * width + width/2
        ax.bar(x + offset, rates, width, label=domain, alpha=0.8)
    
    ax.set_xlabel('Model & Epoch', fontsize=12)
    ax.set_ylabel('Success Rate', fontsize=12)
    ax.set_title('Success Rate by Domain (Local Data Test)', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(models, rotation=45, ha='right')
    ax.legend()
    ax.set_ylim([0, 1])
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_dir / 'success_by_domain.png', dpi=300, bbox_inches='tight')
    print(f"Graph saved: {output_dir / 'success_by_domain.png'}")
    plt.close()


def create_impossibility_graphs(local_results, output_dir):
    """Create graphs for impossibility breakdown."""
    if not HAS_MATPLOTLIB:
        return
    
    impossible_data = {"impossible": [], "possible": []}
    models = sorted(local_results.keys())
    
    for model in models:
        result = local_results.get(model, {})
        if "by_impossibility" not in result:
            continue
        for key, stats in result["by_impossibility"].items():
            if key in impossible_data:
                impossible_data[key].append((model, stats["success_rate"]))
    
    if not any(impossible_data.values()):
        return
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    x = np.arange(len(models))
    width = 0.35
    
    impossible_rates = [next((rate for m, rate in impossible_data["impossible"] if m == model), 0) for model in models]
    possible_rates = [next((rate for m, rate in impossible_data["possible"] if m == model), 0) for model in models]
    
    bars1 = ax.bar(x - width/2, impossible_rates, width, label='Impossible', alpha=0.8, color='#ff6b6b')
    bars2 = ax.bar(x + width/2, possible_rates, width, label='Possible', alpha=0.8, color='#51cf66')
    
    ax.set_xlabel('Model & Epoch', fontsize=12)
    ax.set_ylabel('Success Rate', fontsize=12)
    ax.set_title('Success Rate by Impossibility (Local Data Test)', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(models, rotation=45, ha='right')
    ax.legend()
    ax.set_ylim([0, 1])
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_dir / 'success_by_impossibility.png', dpi=300, bbox_inches='tight')
    print(f"Graph saved: {output_dir / 'success_by_impossibility.png'}")
    plt.close()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Compare models across evaluation sets")
    parser.add_argument(
        "--apigen-only",
        action="store_true",
        help="Only analyze APIGen-on-APIGen predictions (skip local data)"
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Only analyze APIGen-on-Local-Data predictions (skip APIGen)"
    )
    args = parser.parse_args()
    
    output_dir = Path("training/analysis_results")
    output_dir.mkdir(exist_ok=True)
    
    apigen_results = {}
    local_results = {}
    
    if not args.local_only:
        print("=" * 80)
        print("ANALYZING APIGen-on-APIGen Predictions")
        print("=" * 80)
        apigen_results = analyze_set(APIGEN_PREDICTIONS, "apigen", output_dir)
    
    if not args.apigen_only:
        print("\n" + "=" * 80)
        print("ANALYZING APIGen-on-Local-Data Predictions")
        print("=" * 80)
        local_results = analyze_set(LOCAL_DATA_PREDICTIONS, "local", output_dir)
    
    if apigen_results and local_results:
        create_comparison_table(apigen_results, local_results)
        if HAS_MATPLOTLIB:
            print("\n" + "=" * 80)
            print("GENERATING GRAPHS")
            print("=" * 80)
            create_graphs(apigen_results, local_results, output_dir)
    elif apigen_results and not local_results:
        print("\n" + "=" * 80)
        print("APIGen-on-APIGen Results Summary")
        print("=" * 80)
        for model, result in sorted(apigen_results.items()):
            if isinstance(result, dict) and "overall_success_rate" in result:
                print(f"{model}: {result['overall_success_rate']:.4f} ({result['overall_success_rate']*100:.2f}%)")
    elif local_results and not apigen_results:
        print("\n" + "=" * 80)
        print("APIGen-on-Local-Data Results Summary")
        print("=" * 80)
        for model, result in sorted(local_results.items()):
            if isinstance(result, dict) and "overall_success_rate" in result:
                print(f"{model}: {result['overall_success_rate']:.4f} ({result['overall_success_rate']*100:.2f}%)")
    
    output_file = output_dir / "all_results.json"
    with open(output_file, 'w') as f:
        json.dump({
            "apigen_test": apigen_results,
            "local_data_test": local_results
        }, f, indent=2)
    
    print(f"\nDetailed results saved to: {output_file}")


if __name__ == "__main__":
    main()
