#!/usr/bin/env python3
"""
Analyze prediction files from eval runs and produce a narrative report on:
- Conversation completeness (valid, well-formed model outputs)
- Conversation success (syntax + type + tool name/args match where applicable)
- Domain-wise analysis
- Optional: impossibility breakdown and comparison graphs.
"""

import argparse
import json
import sys
from pathlib import Path


def load_predictions(path: Path) -> list[dict]:
    with open(path, "r") as f:
        return [json.loads(line) for line in f if line.strip()]


def is_success(record: dict) -> bool:
    m = record.get("metrics", {})
    if not m.get("valid_syntax"):
        return False
    if not m.get("type_match"):
        return False
    if record.get("gold_type") == "tool":
        return bool(m.get("name_match") and m.get("args_match"))
    return True


def compute_metrics(records: list[dict]) -> dict:
    if not records:
        return {"count": 0, "completeness_pct": 0.0, "success_pct": 0.0}

    n = len(records)
    completeness = sum(1 for r in records if r.get("metrics", {}).get("valid_syntax")) / n * 100
    success = sum(1 for r in records if is_success(r)) / n * 100

    out = {
        "count": n,
        "completeness_pct": round(completeness, 2),
        "success_pct": round(success, 2),
    }

    domains = {}
    for r in records:
        d = r.get("metadata", {}).get("domain") or "unknown"
        domains.setdefault(d, []).append(r)
    if len(domains) > 1:
        out["by_domain"] = {
            d: {
                "count": len(recs),
                "completeness_pct": round(sum(1 for r in recs if r.get("metrics", {}).get("valid_syntax")) / len(recs) * 100, 2),
                "success_pct": round(sum(1 for r in recs if is_success(r)) / len(recs) * 100, 2),
            }
            for d, recs in sorted(domains.items())
        }

    impossible_vals = set(r.get("metadata", {}).get("impossible") for r in records)
    if len(impossible_vals) > 1 or (len(impossible_vals) == 1 and next(iter(impossible_vals)) is not None):
        by_imp = {"possible": [], "impossible": []}
        for r in records:
            if r.get("metadata", {}).get("impossible"):
                by_imp["impossible"].append(r)
            else:
                by_imp["possible"].append(r)
        out["by_impossibility"] = {}
        for key, recs in by_imp.items():
            if recs:
                out["by_impossibility"][key] = {
                    "count": len(recs),
                    "completeness_pct": round(sum(1 for r in recs if r.get("metrics", {}).get("valid_syntax")) / len(recs) * 100, 2),
                    "success_pct": round(sum(1 for r in recs if is_success(r)) / len(recs) * 100, 2),
                }
    return out


def discover_prediction_files(root: Path) -> list[tuple[str, Path]]:
    out = []
    for p in root.rglob("predictions_local_data_*.jsonl"):
        suffix = p.stem.replace("predictions_local_data_", "")
        out.append((suffix, p))
    return sorted(out, key=lambda x: x[0])


def write_report(results: dict, output_path: Path, predictions_dir: str) -> None:
    best_success = max((d["success_pct"] for d in results.values()), default=0)
    best_model = next((m for m, d in results.items() if d["success_pct"] == best_success), "")
    avg_complete = sum(d["completeness_pct"] for d in results.values()) / len(results) if results else 0
    lines = [
        "# Evaluation Report",
        "",
        f"Prediction files were read from: `{predictions_dir}`",
        "",
        "## Summary",
        "",
        f"This report covers **{len(results)}** model(s). "
        f"**Conversation completeness** (well-formed outputs) averages **{avg_complete:.1f}%** across models. "
        f"**Conversation success** (correct action type and, for tools, correct name and arguments) is highest for **{best_model}** at **{best_success}%**. "
        "Below you find per-model completeness and success, domain-wise analysis where metadata is available, and possible vs impossible scenario breakdowns.",
        "",
        "---",
        "",
        "## 1. Conversation completeness",
        "",
        "**Completeness** is the share of turns where the model produced a valid, well-formed action block (correct `<think>`/`<plan>`/`<action>` structure and parseable output).",
        "",
        "| Model | Samples | Completeness (%) |",
        "|-------|--------|------------------|",
    ]
    for model, data in results.items():
        lines.append(f"| {model} | {data['count']} | {data['completeness_pct']} |")
    lines.extend([
        "",
        "---",
        "",
        "## 2. Conversation success",
        "",
        "**Success** means the model output was complete *and* matched the gold response: same action type (say vs tool), and for tool actions, correct tool name and arguments.",
        "",
        "| Model | Samples | Success (%) |",
        "|-------|--------|-------------|",
    ])
    for model, data in results.items():
        lines.append(f"| {model} | {data['count']} | {data['success_pct']} |")
    lines.extend([
        "",
        "---",
        "",
        "## 3. Domain-wise conversation analysis",
        "",
    ])
    models_with_domain = [(m, d) for m, d in results.items() if "by_domain" in d and d["by_domain"]]
    if not models_with_domain:
        lines.append("No domain breakdown (single domain or no domain metadata in predictions).")
    else:
        for model, data in models_with_domain:
            lines.append(f"### {model}")
            lines.append("")
            lines.append("| Domain | Count | Completeness (%) | Success (%) |")
            lines.append("|--------|-------|------------------|-------------|")
            for domain, dom_data in data["by_domain"].items():
                lines.append(f"| {domain} | {dom_data['count']} | {dom_data['completeness_pct']} | {dom_data['success_pct']} |")
            lines.append("")
    lines.extend([
        "---",
        "",
        "## 4. Possible vs impossible scenarios",
        "",
    ])
    models_with_imp = [(m, d) for m, d in results.items() if "by_impossibility" in d and d["by_impossibility"]]
    if not models_with_imp:
        lines.append("No impossibility breakdown (all possible or no impossibility metadata).")
    else:
        for model, data in models_with_imp:
            lines.append(f"### {model}")
            lines.append("")
            lines.append("| Type | Count | Completeness (%) | Success (%) |")
            lines.append("|------|-------|------------------|-------------|")
            for key, imp_data in data["by_impossibility"].items():
                lines.append(f"| {key} | {imp_data['count']} | {imp_data['completeness_pct']} | {imp_data['success_pct']} |")
            lines.append("")
    lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")


def plot_if_available(results: dict, output_dir: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return

    models = list(results.keys())
    completeness = [results[m]["completeness_pct"] for m in models]
    success = [results[m]["success_pct"] for m in models]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(max(8, len(models) * 0.5), 6))
    x = range(len(models))
    ax1.bar([i - 0.2 for i in x], completeness, width=0.4, label="Completeness (%)", color="steelblue")
    ax1.bar([i + 0.2 for i in x], success, width=0.4, label="Success (%)", color="darkorange")
    ax1.set_xticks(x)
    ax1.set_xticklabels(models, rotation=45, ha="right")
    ax1.set_ylabel("Percentage")
    ax1.set_title("Conversation completeness and success by model")
    ax1.legend()
    ax1.set_ylim(0, 105)

    ax2.bar(x, success, color="seagreen", alpha=0.8)
    ax2.set_xticks(x)
    ax2.set_xticklabels(models, rotation=45, ha="right")
    ax2.set_ylabel("Success (%)")
    ax2.set_title("Conversation success by model")
    ax2.set_ylim(0, 105)
    plt.tight_layout()
    fig.savefig(output_dir / "completeness_and_success.png", dpi=150, bbox_inches="tight")
    plt.close()

    models_with_domain = [(m, d) for m, d in results.items() if "by_domain" in d and d["by_domain"]]
    if models_with_domain:
        all_domains = sorted(set().union(*(set(d["by_domain"]) for _, d in models_with_domain)))
        if all_domains:
            fig, ax = plt.subplots(figsize=(max(8, len(models) * 0.4), 5))
            x = range(len(models))
            w = 0.8 / len(all_domains)
            for i, dom in enumerate(all_domains):
                vals = []
                for m, d in models_with_domain:
                    if dom in d["by_domain"]:
                        vals.append(d["by_domain"][dom]["success_pct"])
                    else:
                        vals.append(0)
                off = (i - len(all_domains) / 2 + 0.5) * w
                ax.bar([xi + off for xi in x], vals, width=w, label=dom)
            ax.set_xticks(x)
            ax.set_xticklabels([m for m, _ in models_with_domain], rotation=45, ha="right")
            ax.set_ylabel("Success (%)")
            ax.set_title("Success by domain and model")
            ax.legend(loc="upper right", fontsize=8)
            ax.set_ylim(0, 105)
            plt.tight_layout()
            fig.savefig(output_dir / "success_by_domain.png", dpi=150, bbox_inches="tight")
            plt.close()


def main():
    parser = argparse.ArgumentParser(
        description="Analyze eval predictions and generate a report on completeness, success, and domain-wise analysis."
    )
    parser.add_argument(
        "--predictions_dir",
        type=str,
        default="training/models",
        help="Root directory containing apigen_*, custom_dataset_* with predictions_local_data_*.jsonl",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="training/analysis_results",
        help="Where to write report.md, all_results.json, and optional graphs",
    )
    parser.add_argument(
        "--no_plots",
        action="store_true",
        help="Skip generating matplotlib graphs",
    )
    args = parser.parse_args()

    root = Path(args.predictions_dir)
    if not root.is_dir():
        print(f"Error: Not a directory: {root}", file=sys.stderr)
        sys.exit(1)

    found = discover_prediction_files(root)
    if not found:
        print(f"No predictions_local_data_*.jsonl found under {root}", file=sys.stderr)
        sys.exit(1)

    results = {}
    for suffix, path in found:
        records = load_predictions(path)
        results[suffix] = compute_metrics(records)
        print(f"Processed {path.relative_to(root)}: {results[suffix]['count']} samples, success={results[suffix]['success_pct']}%", file=sys.stderr)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(out_dir / "all_results.json", "w") as f:
        json.dump(results, f, indent=2)

    write_report(results, out_dir / "report.md", args.predictions_dir)
    print(f"Report written to {out_dir / 'report.md'}", file=sys.stderr)

    if not args.no_plots:
        plot_if_available(results, out_dir)
        print(f"Plots written to {out_dir}", file=sys.stderr)

    print("Done.", file=sys.stderr)


if __name__ == "__main__":
    main()
