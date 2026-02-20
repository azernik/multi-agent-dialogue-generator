#!/usr/bin/env python3
"""
Scenario-wise conversation success rate (L2 eval).

Reads all prediction JSONL files (predictions_local_data_*.jsonl), groups turns
into conversations by scenario_id and prompt-length boundaries, scores each
conversation (stop on first wrong turn; score = correct_so_far / attempted),
and writes per-model and per-scenario results to success_eval_l2.md.
"""

import argparse
import json
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "src"))

# Load parser without importing eval.syntax (which pulls in checker/scenario)
import importlib.util
import types
for name in ("eval", "eval.syntax"):
    if name not in sys.modules:
        sys.modules[name] = types.ModuleType(name)
_spec = importlib.util.spec_from_file_location(
    "eval.syntax.parser", repo_root / "src" / "eval" / "syntax" / "parser.py"
)
_parser_mod = importlib.util.module_from_spec(_spec)
sys.modules["eval.syntax.parser"] = _parser_mod
_spec.loader.exec_module(_parser_mod)
parse_action_blocks = _parser_mod.parse_action_blocks
ParsedAction = _parser_mod.ParsedAction


def _levenshtein(a: str, b: str) -> int:
    """Edit distance between two strings. O(n*m)."""
    a, b = a.lower(), b.lower()
    n, m = len(a), len(b)
    if n == 0:
        return m
    if m == 0:
        return n
    prev = list(range(m + 1))
    for i in range(1, n + 1):
        curr = [i] + [0] * m
        for j in range(1, m + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[m]


def _tool_name_match(gold_name: str, pred_name: str, fuzzy_threshold: int = 2) -> bool:
    """Exact (case-insensitive) or fuzzy match for tool names."""
    if not gold_name or not pred_name:
        return False
    g, p = gold_name.strip().lower(), pred_name.strip().lower()
    if g == p:
        return True
    if fuzzy_threshold <= 0:
        return False
    return _levenshtein(g, p) <= fuzzy_threshold


def compare_turn_l2(
    gold: ParsedAction,
    pred: ParsedAction,
    *,
    require_args_match: bool = False,
    fuzzy_tool_name_threshold: int = 2,
) -> bool:
    """
    Return True if this turn is correct (for L2 scoring).
    Tool: type tool, name exact or fuzzy (case-insensitive), args optional.
    Say: type say, valid syntax.
    """
    if not pred.action or "missing_action_block" in (pred.parse_errors or []):
        return False
    if gold.action_type != pred.action_type:
        return False
    if gold.action_type == "say":
        return True
    if gold.action_type == "tool":
        if not _tool_name_match(
            gold.action_name or "",
            pred.action_name or "",
            fuzzy_threshold=fuzzy_tool_name_threshold,
        ):
            return False
        if require_args_match:
            try:
                gold_args = json.loads(gold.action_body or "{}")
                pred_args = json.loads(pred.action_body or "{}")
                return gold_args == pred_args
            except json.JSONDecodeError:
                return False
        return True
    return False


def load_predictions(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def group_into_conversations(records: list[dict]) -> list[list[dict]]:
    """
    Group records by scenario_id, then split into conversations when
    prompt length drops (new conversation starts with shorter prompt).
    Preserves order within each conversation.
    """
    if not records:
        return []
    by_scenario: dict[str, list[dict]] = {}
    for r in records:
        sid = (r.get("metadata") or {}).get("scenario_id") or "unknown"
        by_scenario.setdefault(sid, []).append(r)
    conversations: list[list[dict]] = []
    for sid in sorted(by_scenario.keys()):
        rows = by_scenario[sid]
        prev_len = 0
        current: list[dict] = []
        for r in rows:
            plen = len(r.get("prompt") or "")
            if plen < prev_len and current:
                conversations.append(current)
                current = []
            current.append(r)
            prev_len = plen
        if current:
            conversations.append(current)
    return conversations


def score_conversation(
    turns: list[dict],
    *,
    require_args_match: bool = False,
    fuzzy_tool_name_threshold: int = 2,
) -> tuple[float, int, int]:
    """
    Score one conversation: evaluate in order, stop on first wrong turn.
    Returns (score, correct_count, attempted_count).
    First turn wrong -> (0.0, 0, 1). Otherwise (correct/attempted, correct, attempted).
    """
    if not turns:
        return (0.0, 0, 0)
    correct = 0
    for i, rec in enumerate(turns):
        gold_text = rec.get("gold_text") or ""
        pred_text = rec.get("pred_text") or ""
        gold_parsed = parse_action_blocks(gold_text)
        if "missing_action_block" in (gold_parsed.parse_errors or []):
            continue
        pred_parsed = parse_action_blocks(pred_text)
        ok = compare_turn_l2(
            gold_parsed,
            pred_parsed,
            require_args_match=require_args_match,
            fuzzy_tool_name_threshold=fuzzy_tool_name_threshold,
        )
        if not ok:
            attempted = i + 1
            return (correct / attempted if attempted else 0.0, correct, attempted)
        correct += 1
    attempted = len(turns)
    return (correct / attempted if attempted else 0.0, correct, attempted)


def run_eval_on_file(
    path: Path,
    *,
    require_args_match: bool = False,
    fuzzy_tool_name_threshold: int = 2,
) -> dict:
    """
    Run L2 eval on one prediction JSONL. Returns dict with per-scenario and
    overall stats: by_scenario, overall_score, total_conversations, etc.
    """
    records = load_predictions(path)
    conversations = group_into_conversations(records)
    scenario_scores: dict[str, list[float]] = {}
    scenario_counts: dict[str, int] = {}
    for conv in conversations:
        if not conv:
            continue
        sid = (conv[0].get("metadata") or {}).get("scenario_id") or "unknown"
        score, _, _ = score_conversation(
            conv,
            require_args_match=require_args_match,
            fuzzy_tool_name_threshold=fuzzy_tool_name_threshold,
        )
        scenario_scores.setdefault(sid, []).append(score)
        scenario_counts[sid] = scenario_counts.get(sid, 0) + 1
    by_scenario = {}
    for sid in sorted(scenario_scores.keys()):
        scores = scenario_scores[sid]
        avg = sum(scores) / len(scores) if scores else 0.0
        by_scenario[sid] = {
            "success_pct": round(avg * 100, 2),
            "conversations": len(scores),
        }
    all_scores = [s for scores in scenario_scores.values() for s in scores]
    overall_score_pct = round((sum(all_scores) / len(all_scores) * 100), 2) if all_scores else 0.0
    return {
        "count_conversations": len(conversations),
        "overall_success_pct": overall_score_pct,
        "by_scenario": by_scenario,
    }


def discover_prediction_files(root: Path) -> list[tuple[str, Path]]:
    out = []
    for p in root.rglob("predictions_local_data_*.jsonl"):
        suffix = p.stem.replace("predictions_local_data_", "")
        out.append((suffix, p))
    return sorted(out, key=lambda x: x[0])


def write_success_eval_md(
    results: dict[str, dict],
    output_path: Path,
    predictions_root: str,
) -> None:
    """Write success_eval_l2.md with per-model and per-scenario tables."""
    lines = [
        "# Scenario-wise conversation success (L2 eval)",
        "",
        f"Prediction files discovered under: `{predictions_root}`",
        "",
        "**Scoring:** Turns evaluated in order; stop on first wrong turn. "
        "Score = correct turns so far / turns attempted. First turn wrong → 0% for that conversation. "
        "Tool names: exact or fuzzy (case-insensitive, small edit distance).",
        "",
        "---",
        "",
        "## Overall by model",
        "",
        "| Model | Conversations | Overall success (%) |",
        "| :---- | -------------: | ------------------: |",
    ]
    for model_key in sorted(results.keys()):
        d = results[model_key]
        n_conv = d.get("count_conversations", 0)
        pct = d.get("overall_success_pct")
        pct_str = f"{pct:.2f}" if pct is not None else "—"
        lines.append(f"| {model_key} | {n_conv} | {pct_str} |")
    lines.extend(["", "---", "", "## Per-scenario success by model", ""])
    all_scenarios = set()
    for d in results.values():
        all_scenarios.update((d.get("by_scenario") or {}).keys())
    scenarios_sorted = sorted(all_scenarios)
    header = "| Scenario | " + " | ".join(results.keys()) + " |"
    sep = "| :------- | " + " | ".join("--------:" for _ in results) + " |"
    lines.append(header)
    lines.append(sep)
    for sid in scenarios_sorted:
        cells = [sid]
        for model_key in sorted(results.keys()):
            by_sc = (results[model_key].get("by_scenario") or {}).get(sid)
            if by_sc is not None and by_sc.get("success_pct") is not None:
                cells.append(f"{by_sc['success_pct']:.2f}")
            else:
                cells.append("—")
        lines.append("| " + " | ".join(cells) + " |")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Written: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="L2 eval: scenario-wise conversation success from prediction JSONL files"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Root directory to search for predictions_local_data_*.jsonl",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "analysis_results_apigen2" / "success_eval_l2.md",
        help="Output Markdown file path",
    )
    parser.add_argument(
        "--require-args",
        action="store_true",
        help="Require tool args to match (default: name match only)",
    )
    parser.add_argument(
        "--fuzzy-threshold",
        type=int,
        default=2,
        help="Max Levenshtein distance for fuzzy tool name match (default: 2)",
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=None,
        help="Process only this prediction JSONL file (skip discovery).",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    output_path = args.output.resolve()
    if args.file is not None:
        path = args.file.resolve()
        if not path.is_file():
            print(f"File not found: {path}", file=sys.stderr)
            sys.exit(1)
        suffix = path.stem.replace("predictions_local_data_", "")
        files = [(suffix, path)]
    else:
        files = discover_prediction_files(root)
    if not files:
        print("No prediction files found.", file=sys.stderr)
        sys.exit(1)
    print(f"Found {len(files)} prediction file(s).")
    results: dict[str, dict] = {}
    for suffix, path in files:
        print(f"  Processing: {path.relative_to(root)}")
        try:
            results[suffix] = run_eval_on_file(
                path,
                require_args_match=args.require_args,
                fuzzy_tool_name_threshold=args.fuzzy_threshold,
            )
        except Exception as e:
            print(f"  Error: {e}", file=sys.stderr)
            results[suffix] = {
                "count_conversations": 0,
                "overall_success_pct": None,
                "by_scenario": {},
            }
    write_success_eval_md(results, output_path, str(root))
    print("Done.")


if __name__ == "__main__":
    main()
