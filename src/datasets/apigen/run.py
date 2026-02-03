#!/usr/bin/env python3
"""
Main entry point for converting APIGen-MT conversations, validating them,
and automatically copying valid ones to data/valid_outputs/apigen/

This mirrors the automatic workflow of simulate.py --run-eval
"""

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    from datasets import load_dataset
    DATASETS_AVAILABLE = True
    DATASETS_ERROR = None
except (ImportError, ModuleNotFoundError) as e:
    DATASETS_AVAILABLE = False
    DATASETS_ERROR = f"ImportError: {str(e)}"
except PermissionError as e:
    DATASETS_AVAILABLE = False
    DATASETS_ERROR = f"PermissionError: {str(e)}\n  This may be due to sandbox restrictions. Try running with network permissions."
except Exception as e:
    DATASETS_AVAILABLE = False
    DATASETS_ERROR = f"{type(e).__name__}: {str(e)}"

repo_root = Path(__file__).resolve().parent.parent.parent.parent
src_path = repo_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from core import LLMClient

convert_path = Path(__file__).resolve().parent / "convert.py"
spec = importlib.util.spec_from_file_location("apigen_convert", convert_path)
convert_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(convert_module)
convert_apigen_to_conversation_json = convert_module.convert_apigen_to_conversation_json


def convert_apigen_conversations(
    num_conversations: int,
    start_index: int,
    output_dir: Path,
    openai_client: LLMClient,
    model: str
) -> List[tuple]:
    """Convert APIGen conversations and return list of (conversation_json, conversation_id, output_path)."""
    if not DATASETS_AVAILABLE:
        print("Error: Cannot import 'datasets' library.")
        if DATASETS_ERROR:
            print(f"  Details: {DATASETS_ERROR}")
        else:
            print("  Install with: pip install datasets")
        return []
    
    print(f"Loading {num_conversations} conversations from APIGen-MT dataset (starting at index {start_index})...")
    try:
        dataset = load_dataset("Salesforce/APIGen-MT-5k", split="train")
        print(f"✓ Loaded dataset with {len(dataset)} conversations")
        
        max_index = min(start_index + num_conversations, len(dataset))
        entries_to_process = []
        
        for idx in range(start_index, max_index):
            entry = dataset[idx]
            conversation_id = f"apigen_{idx:04d}"
            entries_to_process.append((entry, conversation_id))
        
        print(f"✓ Will process {len(entries_to_process)} conversations")
    except Exception as e:
        print(f"Error loading dataset: {e}")
        return []
    
    converted = []
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for conv_num, (apigen_entry, conversation_id) in enumerate(entries_to_process, 1):
        print(f"\n{'='*60}")
        print(f"Converting {conv_num}/{len(entries_to_process)}: {conversation_id}")
        print(f"{'='*60}")
        
        try:
            conversation_json = convert_apigen_to_conversation_json(
                apigen_entry,
                conversation_id,
                openai_client
            )
            
            output_path = output_dir / f"{conversation_id}.json"
            with open(output_path, 'w') as f:
                json.dump(conversation_json, f, indent=2)
            
            converted.append((conversation_json, conversation_id, output_path))
            print(f"✓ Converted and saved to: {output_path}")
            
        except Exception as e:
            print(f"✗ Conversion failed: {e}")
            import traceback
            traceback.print_exc()
    
    return converted


def validate_conversations(
    conversation_files: List[Path],
    openai_api_key: Optional[str],
    model: str
) -> Dict[str, Dict[str, Any]]:
    """Run eval.run on conversations and return results.
    
    Uses the same evaluation infrastructure (src/eval/run.py) as the main dataset.
    """
    print(f"\n{'='*60}")
    print("VALIDATING CONVERSATIONS")
    print(f"{'='*60}")
    print(f"Running evals on {len(conversation_files)} conversations...")
    
    eval_script = repo_root / "src" / "eval" / "run.py"
    cmd = [
        sys.executable, str(eval_script)
    ] + [str(f) for f in conversation_files]
    
    if openai_api_key:
        cmd.extend(["--api-key", openai_api_key])
        cmd.extend(["--model", model])
        cmd.extend(["--faithfulness-model", model])
        cmd.extend(["--role-confusion-model", model])
        cmd.append("--skip-success")
    else:
        cmd.append("--syntax-only")
        print("Warning: No API key provided. Running syntax-only evaluation.")
    
    cmd.append("--jsonl")
    
    env = dict(os.environ)
    src_path = str(repo_root / "src")
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] = f"{src_path}:{env['PYTHONPATH']}"
    else:
        env["PYTHONPATH"] = src_path
    
    result = subprocess.run(
        cmd,
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"Error running evals (return code {result.returncode}):")
        if result.stderr:
            print(f"  stderr: {result.stderr[:500]}")
        if result.stdout:
            print(f"  stdout: {result.stdout[:500]}")
        return {}
    
    eval_results = {}
    for line in result.stdout.strip().split('\n'):
        if line.strip():
            try:
                result_data = json.loads(line)
                conv_id = result_data.get("conversation_id", "unknown")
                eval_results[conv_id] = result_data
            except json.JSONDecodeError as e:
                print(f"Warning: Failed to parse eval result line: {line[:100]}...")
                continue
    
    if not eval_results:
        print(f"Warning: No eval results parsed from output. stdout: {result.stdout[:500]}")
    
    return eval_results


def copy_to_valid_outputs(
    conversation_file: Path,
    conversation_id: str,
    valid_outputs_root: Path,
    repo_root: Path
) -> Optional[Path]:
    """Copy valid conversation to valid_outputs/apigen/ directory."""
    conversation_filename = conversation_file.name
    dest_file = (valid_outputs_root / conversation_filename).resolve()
    dest_file.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        shutil.copy2(conversation_file, dest_file)
        return dest_file
    except Exception as e:
        print(f"Error copying {conversation_id} to valid_outputs: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Convert APIGen-MT conversations, validate, and copy valid ones to valid_outputs/apigen/"
    )
    parser.add_argument(
        "--num_conversations",
        type=int,
        default=5,
        help="Number of conversations to convert (default: 5)"
    )
    parser.add_argument(
        "--start_index",
        type=int,
        default=0,
        help="Starting index in dataset (default: 0)"
    )
    parser.add_argument(
        "--temp_dir",
        type=str,
        default="data/apigen_conversion_temp",
        help="Temporary directory for converted conversations (default: data/apigen_conversion_temp)"
    )
    parser.add_argument(
        "--openai_api_key",
        type=str,
        help="OpenAI API key (or use OPENAI_API_KEY env var)"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4o-mini",
        help="OpenAI model to use (default: gpt-4o-mini)"
    )
    parser.add_argument(
        "--valid_outputs_dir",
        type=str,
        default="data/valid_outputs/apigen",
        help="Directory to copy valid conversations (default: data/valid_outputs/apigen, separate from main dataset)"
    )
    parser.add_argument(
        "--syntax-only",
        action="store_true",
        help="Run syntax-only validation (faster, no API calls for faithfulness/role confusion)"
    )
    args = parser.parse_args()
    
    api_key = args.openai_api_key or os.getenv("OPENAI_API_KEY")
    if not api_key and not args.syntax_only:
        print("Warning: No OpenAI API key provided.")
        print("  Use --syntax-only for syntax checks only, or set OPENAI_API_KEY env var")
        print("  Running with --syntax-only mode...")
        args.syntax_only = True
    
    openai_client = LLMClient(model=args.model, api_key=api_key) if api_key else None
    
    temp_dir = Path(args.temp_dir)
    valid_outputs_root = Path(args.valid_outputs_dir)
    
    print("="*60)
    print("APIGEN TO VALIDATED CONVERSATIONS")
    print("="*60)
    print(f"Conversations to convert: {args.num_conversations}")
    print(f"Starting index: {args.start_index}")
    print(f"Temporary directory: {temp_dir}")
    print(f"Valid outputs directory: {valid_outputs_root}")
    if args.syntax_only:
        validation_mode = "Syntax only"
    else:
        validation_mode = "Full (syntax + faithfulness + role confusion, success skipped for APIGen)"
    print(f"Validation mode: {validation_mode}")
    print("="*60)
    
    if not openai_client:
        print("Error: OpenAI client required for conversion")
        return 1
    
    converted = convert_apigen_conversations(
        args.num_conversations,
        args.start_index,
        temp_dir,
        openai_client,
        args.model
    )
    
    if not converted:
        print("No conversations converted successfully.")
        return 1
    
    print(f"\n✓ Converted {len(converted)} conversations")
    
    conversation_files = [path for _, _, path in converted]
    eval_results = validate_conversations(
        conversation_files,
        api_key if not args.syntax_only else None,
        args.model
    )
    
    if not eval_results:
        print("No evaluation results returned.")
        return 1
    
    print(f"\n{'='*60}")
    print("COPYING VALID CONVERSATIONS")
    print(f"{'='*60}")
    
    valid_count = 0
    invalid_count = 0
    
    for conversation_json, conversation_id, output_path in converted:
        result = eval_results.get(conversation_id)
        if not result:
            print(f"  ✗ {conversation_id}: No eval result found (available: {list(eval_results.keys())})")
            invalid_count += 1
            continue
        
        syntax_result = result.get("syntax", {})
        syntax_summary = syntax_result.get("summary", {})
        syntax_errors = syntax_result.get("error_turns", [])
        faithfulness_eval = result.get("faithfulness", {})
        role_confusion_eval = result.get("role_confusion", {})
        
        syntax_valid = (
            syntax_summary.get("structure", {}).get("valid", False) and
            syntax_summary.get("tool", {}).get("valid", False)
        )
        
        faithfulness_valid = True
        if faithfulness_eval and "error" not in faithfulness_eval:
            faithfulness_valid = faithfulness_eval.get("summary", {}).get("valid", False)
        elif faithfulness_eval and "error" in faithfulness_eval:
            faithfulness_valid = False
        
        role_confusion_valid = True
        if role_confusion_eval and "error" not in role_confusion_eval:
            role_confusion_valid = not role_confusion_eval.get("has_confusion", False)
        elif role_confusion_eval and "error" in role_confusion_eval:
            role_confusion_valid = False
        
        is_valid = syntax_valid and faithfulness_valid and role_confusion_valid
        
        if is_valid:
            dest_file = copy_to_valid_outputs(
                output_path,
                conversation_id,
                valid_outputs_root,
                repo_root
            )
            if dest_file:
                try:
                    display_path = dest_file.relative_to(repo_root.resolve())
                except (ValueError, AttributeError):
                    display_path = dest_file
                print(f"  ✓ {conversation_id}: Copied to {display_path}")
                valid_count += 1
                
                try:
                    output_path.unlink()
                except Exception as e:
                    print(f"    Warning: Could not delete {conversation_id} from temp folder: {e}")
            else:
                print(f"  ✗ {conversation_id}: Failed to copy")
                invalid_count += 1
        else:
            print(f"  ✗ {conversation_id}: Failed validation")
            invalid_count += 1
    
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Total converted: {len(converted)}")
    print(f"Valid and copied: {valid_count}")
    print(f"Invalid: {invalid_count}")
    print(f"\nValid conversations saved to: {valid_outputs_root}")
    if invalid_count > 0:
        print(f"Invalid conversations kept in: {temp_dir} (for review/debugging)")
    else:
        print(f"Temporary folder: {temp_dir} (empty, can be deleted)")
    print("="*60)
    
    if valid_count > 0:
        print(f"\n✓ {valid_count} conversation(s) are now ready for training!")
        print(f"  APIGen conversations saved to: {valid_outputs_root}")
        print(f"  (separate from main dataset in data/valid_outputs/v2/)")
        print(f"\n  To prepare training data:")
        print(f"    python training/prepare_data.py --input_dir {valid_outputs_root}")
        print(f"  Or combine with main dataset:")
        print(f"    python training/prepare_data.py --input_dir data/valid_outputs")
    
    return 0 if valid_count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
