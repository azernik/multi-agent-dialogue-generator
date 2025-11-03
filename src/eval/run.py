from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable, Iterator, List, Optional

from eval.syntax import evaluate_conversation, load_conversation_artifact
from eval.success import evaluate_success


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
        default="gpt-4.1-mini",
        help="OpenAI model to use for success judge (default: gpt-4.1-mini).",
    )
    parser.add_argument(
        "--api-key",
        dest="api_key",
        help="OpenAI API key for success judge (default: use OPENAI_API_KEY env variable).",
    )
    parser.add_argument(
        "--syntax-only",
        action="store_true",
        help="Skip the LLM success judge and run syntax checks only.",
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
                    "raw": success_eval.raw_response,
                }
            except Exception as exc:  # pragma: no cover - best effort catch
                success_payload = {
                    "error": str(exc),
                }

        output = {
            "conversation_id": syntax_result.conversation_id,
            "source_path": str(conversation_path),
            "syntax": syntax_result.to_dict(),
            "success": success_payload,
        }

        if args.jsonl:
            print(json.dumps(output, ensure_ascii=False))
        else:
            print(json.dumps(output, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
