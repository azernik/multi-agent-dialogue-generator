from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List, Optional

from .judge import evaluate_success


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Judge conversation success using an LLM.")
    parser.add_argument("conversation", help="Path to conversation.json")
    parser.add_argument(
        "--model",
        default="gpt-5.1",
        help="OpenAI model to use (default: gpt-5.1)",
    )
    parser.add_argument(
        "--api-key",
        dest="api_key",
        help="OpenAI API key (default: use OPENAI_API_KEY environment variable)",
    )
    args = parser.parse_args(argv)

    result = evaluate_success(Path(args.conversation), model=args.model, api_key=args.api_key)
    output = {
        "success": result.success,
        "reason": result.reason,
        "raw": result.raw_response,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
