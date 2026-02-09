#!/usr/bin/env python3
"""
Script to evaluate all HuggingFace models on our main test dataset.
Loads models directly from HuggingFace Hub.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Model configurations: (base_model, hf_adapter_id, output_suffix, adapter_subfolder or None)
# - APIGen: finetuned on APIGen dataset
# - Custom dataset: finetuned on our own training data (conversations from valid_outputs)
MODELS = [
    # APIGen-finetuned (32B, 14B, 7B)
    ("Qwen/Qwen2.5-32B-Instruct", "ishikakulkarni/apigen-model-32b-epoch-1", "apigen_32b_epoch1", None),
    ("Qwen/Qwen2.5-32B-Instruct", "ishikakulkarni/apigen-model-32b-epoch-3", "apigen_32b_epoch3", None),
    ("Qwen/Qwen2.5-32B-Instruct", "ishikakulkarni/apigen-model-32b-epoch-5", "apigen_32b_epoch5", None),
    ("Qwen/Qwen2.5-14B-Instruct", "ishikakulkarni/apigen-model-14b-epoch-1", "apigen_14b_epoch1", None),
    ("Qwen/Qwen2.5-14B-Instruct", "ishikakulkarni/apigen-model-14b-epoch-3", "apigen_14b_epoch3", None),
    ("Qwen/Qwen2.5-14B-Instruct", "ishikakulkarni/apigen-model-14b-epoch-5", "apigen_14b_epoch5", None),
    ("Qwen/Qwen2.5-7B-Instruct", "ishikakulkarni/apigen-model-7b-checkpoint-38", "apigen_7b_cp38", None),
    ("Qwen/Qwen2.5-7B-Instruct", "ishikakulkarni/apigen-model-7b-checkpoint-114", "apigen_7b_cp114", None),
    ("Qwen/Qwen2.5-7B-Instruct", "ishikakulkarni/apigen-model-7b-checkpoint-185", "apigen_7b_cp185", None),
    # Custom dataset (our training data) - 14B checkpoints 17, 51, 85
    ("Qwen/Qwen2.5-14B-Instruct", "ishikakulkarni/qwen2.5-14b-sft", "custom_14b_cp17", "checkpoint-17"),
    ("Qwen/Qwen2.5-14B-Instruct", "ishikakulkarni/qwen2.5-14b-sft", "custom_14b_cp51", "checkpoint-51"),
    ("Qwen/Qwen2.5-14B-Instruct", "ishikakulkarni/qwen2.5-14b-sft", "custom_14b_cp85", "checkpoint-85"),
    # Custom dataset (our training data) - 7B checkpoint 33
    ("Qwen/Qwen2.5-7B-Instruct", "ishikakulkarni/capstone", "custom_7b_cp33", "qwen2.5-7b/checkpoint-33"),
]

def main():
    parser = argparse.ArgumentParser(
        description="Evaluate all HuggingFace models on our test dataset"
    )
    parser.add_argument(
        "--test_data",
        type=str,
        default="training/data/sft_test.jsonl",
        help="Path to test dataset (default: training/data/sft_test.jsonl)"
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="training/models",
        help="Base output directory for results (default: training/models)"
    )
    parser.add_argument(
        "--gpu_id",
        type=int,
        default=0,
        help="GPU ID to use (default: 0)"
    )
    parser.add_argument(
        "--max_samples",
        type=int,
        default=None,
        help="Limit number of samples to evaluate (for testing)"
    )
    parser.add_argument(
        "--models",
        type=str,
        nargs="+",
        default=None,
        help="Specific model suffixes to evaluate (e.g. 'apigen_32b_epoch1' or 'custom_14b_cp17'). If not provided, evaluates all."
    )
    args = parser.parse_args()
    
    # Filter models if specific ones requested
    models_to_eval = MODELS
    if args.models:
        models_to_eval = [m for m in MODELS if m[2] in args.models]
        if not models_to_eval:
            print(f"Error: No matching models found for {args.models}")
            print(f"Available models: {[m[2] for m in MODELS]}")
            sys.exit(1)
    
    test_data_path = Path(args.test_data)
    if not test_data_path.exists():
        print(f"Error: Test data file not found: {test_data_path}")
        sys.exit(1)
    
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Evaluating {len(models_to_eval)} models on {test_data_path}")
    print(f"Results will be saved to {output_dir}")
    print()
    
    # Evaluate each model
    for base_model, hf_adapter, suffix, adapter_subfolder in models_to_eval:
        print("=" * 80)
        print(f"Evaluating: {suffix}")
        print(f"  Base model: {base_model}")
        print(f"  Adapter: {hf_adapter}" + (f" (subfolder: {adapter_subfolder})" if adapter_subfolder else ""))
        print("=" * 80)
        
        # Output dirs: custom_dataset_* for our training-data models, apigen_* for APIGen models
        if suffix.startswith("custom_"):
            size = "14B" if "14b" in suffix else "7B"
            model_output_dir = output_dir / f"custom_dataset_{size}"
        elif suffix.startswith("apigen_"):
            size = "32B" if "32b" in suffix else "14B" if "14b" in suffix else "7B"
            model_output_dir = output_dir / f"apigen_{size}"
        else:
            model_output_dir = output_dir / f"model_{suffix}"
        
        model_output_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = model_output_dir / f"eval_local_data_{suffix}.json"
        predictions_file = model_output_dir / f"predictions_local_data_{suffix}.jsonl"
        
        # Build command
        cmd = [
            sys.executable,
            "training/evaluate.py",
            "--test_data", str(test_data_path),
            "--base_model", base_model,
            "--adapter_path", hf_adapter,
            "--output_file", str(output_file),
            "--predictions_file", str(predictions_file),
        ]
        if adapter_subfolder:
            cmd.extend(["--adapter_subfolder", adapter_subfolder])
        
        if args.max_samples:
            cmd.extend(["--max_samples", str(args.max_samples)])
        
        # Set CUDA_VISIBLE_DEVICES if specified
        env = None
        if args.gpu_id is not None:
            env = dict(os.environ)
            env["CUDA_VISIBLE_DEVICES"] = str(args.gpu_id)
        
        # Run evaluation
        try:
            result = subprocess.run(
                cmd,
                env=env,
                check=True,
                capture_output=False  # Show output in real-time
            )
            print(f"✓ Completed: {suffix}")
            print(f"  Results: {output_file}")
            print(f"  Predictions: {predictions_file}")
            print()
        except subprocess.CalledProcessError as e:
            print(f"✗ Failed: {suffix}")
            print(f"  Error: {e}")
            print()
            continue
    
    print("=" * 80)
    print("All evaluations complete!")
    print("=" * 80)

if __name__ == "__main__":
    main()
