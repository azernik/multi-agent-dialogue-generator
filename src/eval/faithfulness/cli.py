from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List, Optional

from .judge import evaluate_faithfulness


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate assistant faithfulness against conversation evidence.")
    parser.add_argument("conversation", help="Path to conversation.json")
    parser.add_argument(
        "--model",
        default="gpt-5.1",
        help="OpenAI model to use (default: gpt-5.1)",
    )
    parser.add_argument(
        "--api-key",
        dest="api_key",
        help="OpenAI API key (default: use OPENAI_API_KEY env variable)",
    )
    args = parser.parse_args(argv)

    report = evaluate_faithfulness(Path(args.conversation), model=args.model, api_key=args.api_key)
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
