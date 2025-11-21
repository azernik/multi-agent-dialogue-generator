from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable, Iterator, List, Optional

from eval.syntax import evaluate_conversation, load_conversation_artifact
from eval.success import evaluate_success
from eval.faithfulness import evaluate_faithfulness
from eval.role_confusion import evaluate_role_confusion


def _iter_conversation_files(targets: Iterable[str], recursive: bool) -> Iterator[Path]:
    for target in targets:
        path = Path(target)
        if not path.exists():
            raise FileNotFoundError(f"Path not found: {path}")
        if path.is_file():
            yield path
            continue
        if path.is_dir():
            if recursive:
                yield from path.rglob("conversation.json")
            else:
                candidate = path / "conversation.json"
                if candidate.exists():
                    yield candidate
            continue


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run syntax checks and success evaluation for conversation artifacts."
    )
    parser.add_argument(
        "targets",
        nargs="+",
        help="Path(s) to conversation.json files or directories containing them.",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="When targets include directories, search recursively for conversation.json files.",
    )
    parser.add_argument(
        "--jsonl",
        action="store_true",
        help="Output each result as a single JSON line.",
    )
    parser.add_argument(
        "--model",
        default="gpt-5.1",
        help="OpenAI model to use for success judge (default: gpt-5.1).",
    )
    parser.add_argument(
        "--api-key",
        dest="api_key",
        help="OpenAI API key for success judge (default: use OPENAI_API_KEY env variable).",
    )
    parser.add_argument(
        "--faithfulness-model",
        default=None,
        help="OpenAI model to use for faithfulness judge (default: reuse --model).",
    )
    parser.add_argument(
        "--faithfulness-api-key",
        dest="faithfulness_api_key",
        help="API key for faithfulness judge (default: reuse success API key).",
    )
    parser.add_argument(
        "--syntax-only",
        action="store_true",
        help="Skip the LLM success judge and run syntax checks only.",
    )
    parser.add_argument(
        "--skip-faithfulness",
        action="store_true",
        help="Skip faithfulness evaluation (default is to run it unless --syntax-only).",
    )
    parser.add_argument(
        "--skip-role-confusion",
        action="store_true",
        help="Skip role confusion evaluation (default is to run it unless --syntax-only).",
    )
    parser.add_argument(
        "--role-confusion-model",
        default=None,
        help="OpenAI model to use for role confusion judge (default: reuse --model).",
    )
    parser.add_argument(
        "--role-confusion-api-key",
        dest="role_confusion_api_key",
        help="API key for role confusion judge (default: reuse success API key).",
    )
    args = parser.parse_args(argv)

    conversation_paths = list(_iter_conversation_files(args.targets, args.recursive))
    if not conversation_paths:
        parser.error("No conversation.json files found in provided targets.")

    for conversation_path in conversation_paths:
        artifact = load_conversation_artifact(conversation_path)
        syntax_result = evaluate_conversation(artifact)

        success_payload = None
        if not args.syntax_only:
            try:
                success_eval = evaluate_success(
                    conversation_path,
                    model=args.model,
                    api_key=args.api_key,
                )
                success_payload = {
                    "success": success_eval.success,
                    "reason": success_eval.reason,
                }
            except Exception as exc:  # pragma: no cover - best effort catch
                success_payload = {
                    "error": str(exc),
                }

        faithfulness_payload = None
        if not args.syntax_only and not args.skip_faithfulness:
            faithfulness_model = args.faithfulness_model or args.model
            faithfulness_key = args.faithfulness_api_key or args.api_key
            try:
                faithfulness_report = evaluate_faithfulness(
                    conversation_path,
                    model=faithfulness_model,
                    api_key=faithfulness_key,
                )
                faithfulness_payload = faithfulness_report.to_dict()
            except Exception as exc:  # pragma: no cover
                faithfulness_payload = {"error": str(exc)}

        role_confusion_payload = None
        if not args.syntax_only and not args.skip_role_confusion:
            role_confusion_model = args.role_confusion_model or args.model
            role_confusion_key = args.role_confusion_api_key or args.api_key
            try:
                role_confusion_eval = evaluate_role_confusion(
                    conversation_path,
                    model=role_confusion_model,
                    api_key=role_confusion_key,
                )
                role_confusion_payload = {
                    "has_confusion": role_confusion_eval.has_confusion,
                    "reason": role_confusion_eval.reason,
                    "confused_turns": role_confusion_eval.confused_turns,
                }
            except Exception as exc:  # pragma: no cover
                role_confusion_payload = {"error": str(exc)}

        # Clean up syntax dict: remove conversation_id and source_path (already at top level)
        syntax_dict = syntax_result.to_dict()
        syntax_dict.pop("conversation_id", None)
        syntax_dict.pop("source_path", None)

        # Determine overall success: all parts must succeed
        overall_success = True
        
        # Check syntax: both structure and tool must be valid
        if not (syntax_dict.get("summary", {}).get("structure", {}).get("valid", False) and
                syntax_dict.get("summary", {}).get("tool", {}).get("valid", False)):
            overall_success = False
        
        # Check success evaluation (if present and not an error)
        if success_payload and "error" not in success_payload:
            if not success_payload.get("success", False):
                overall_success = False
        
        # Check faithfulness (if present and not an error)
        if faithfulness_payload and "error" not in faithfulness_payload:
            if not faithfulness_payload.get("summary", {}).get("valid", False):
                overall_success = False
        
        # Check role confusion (if present and not an error)
        if role_confusion_payload and "error" not in role_confusion_payload:
            if role_confusion_payload.get("has_confusion", False):
                overall_success = False

        output = {
            "conversation_id": syntax_result.conversation_id,
            "source_path": str(conversation_path),
            "SUCCESS": overall_success,
            "syntax": syntax_dict,
            "success": success_payload,
            "faithfulness": faithfulness_payload,
            "role_confusion": role_confusion_payload,
        }

        if args.jsonl:
            print(json.dumps(output, ensure_ascii=False))
        else:
            print(json.dumps(output, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
