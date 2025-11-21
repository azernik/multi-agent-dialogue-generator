from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, Iterator, List

from .checker import evaluate_conversation, load_conversation_artifact


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
            # If no conversation.json at top level and not recursive, skip silently
            continue


def _print_result(result_dict: dict, as_jsonl: bool):
    if as_jsonl:
        sys.stdout.write(json.dumps(result_dict) + "\n")
    else:
        json.dump(result_dict, sys.stdout, indent=2)
        sys.stdout.write("\n")


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate conversation syntax compliance.")
    parser.add_argument(
        "targets",
        nargs="+",
        help="Path(s) to conversation.json files or directories containing them.",
    )
    parser.add_argument(
        "--scenario-file",
        help="Optional explicit scenario file path (only valid when a single conversation is evaluated).",
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
    args = parser.parse_args(argv)

    scenario_override = Path(args.scenario_file) if args.scenario_file else None
    conversation_paths = list(_iter_conversation_files(args.targets, args.recursive))
    if not conversation_paths:
        parser.error("No conversation.json files found in provided targets.")
    if scenario_override and len(conversation_paths) != 1:
        parser.error("--scenario-file can only be used with a single conversation file or directory.")

    for conversation_path in conversation_paths:
        artifact = load_conversation_artifact(
            conversation_path,
            scenario_file=scenario_override,
        )
        result = evaluate_conversation(artifact)
        _print_result(result.to_dict(), as_jsonl=args.jsonl)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
