#!/usr/bin/env python3
"""
Build a Markdown evaluation table from all_results.json.
Compares models by finetuning type (APIGen, Custom, RL) with metrics:
completeness, tool name, tool args, success; and by possible/impossible.
Output: training/analysis_results_apigen2/eval_table.md (or --output path).
"""

import argparse
import json
from pathlib import Path


def finetuning_type(model_key: str) -> str:
    if model_key.startswith("apigen_"):
        return "APIGen"
    if model_key.startswith("custom_"):
        return "Custom data"
    if model_key.startswith("rl_"):
        return "RL"
    return "Other"


def model_order_key(model_key: str) -> tuple:
    order = ("APIGen", "Custom data", "RL")
    ft = finetuning_type(model_key)
    idx = order.index(ft) if ft in order else 99
    return (idx, model_key)


def pct_to_dec(val) -> float:
    if val is None:
        return None
    return round(val / 100.0, 2)


def main():
    parser = argparse.ArgumentParser(description="Build eval table from all_results.json")
    parser.add_argument(
        "--results",
        type=str,
        default="training/analysis_results_apigen2/all_results.json",
        help="Path to all_results.json",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="training/analysis_results_apigen2/eval_table.md",
        help="Output Markdown file",
    )
    args = parser.parse_args()

    path = Path(args.results)
    if not path.exists():
        raise SystemExit(f"File not found: {path}")

    with open(path) as f:
        results = json.load(f)

    models = sorted(results.keys(), key=model_order_key)

    def get(d: dict, *keys, default=None):
        for k in keys:
            if isinstance(d, dict) and k in d:
                d = d[k]
            else:
                return default
        return d

    # Collect values for bolding (best per column)
    overall_compl = [get(results[m], "completeness_pct") for m in models]
    overall_tname = [get(results[m], "tool_name_match_pct") for m in models]
    overall_targs = [get(results[m], "tool_args_match_pct") for m in models]
    overall_succ = [get(results[m], "success_pct") for m in models]
    poss_compl = [get(results[m], "by_impossibility", "possible", "completeness_pct") for m in models]
    poss_succ = [get(results[m], "by_impossibility", "possible", "success_pct") for m in models]
    imp_compl = [get(results[m], "by_impossibility", "impossible", "completeness_pct") for m in models]
    imp_succ = [get(results[m], "by_impossibility", "impossible", "success_pct") for m in models]

    def best_idx(vals):
        clean = [v for v in vals if v is not None]
        if not clean:
            return set()
        m = max(clean)
        return {i for i, v in enumerate(vals) if v == m}

    best_overall_compl = best_idx(overall_compl)
    best_overall_tname = best_idx(overall_tname)
    best_overall_targs = best_idx(overall_targs)
    best_overall_succ = best_idx(overall_succ)
    best_poss_compl = best_idx(poss_compl)
    best_poss_succ = best_idx(poss_succ)
    best_imp_compl = best_idx(imp_compl)
    best_imp_succ = best_idx(imp_succ)

    def cell(val, bold: bool) -> str:
        if val is None:
            return "—"
        s = f"{pct_to_dec(val):.2f}"
        return f"**{s}**" if bold else s

    lines = [
        "# End-to-End Evaluation Results (Local Test Set)",
        "",
        "**Metrics:** Compl = Completeness, Tool name = Tool name match, Tool args = Tool args match, Success = Full success (syntax + type + name + args). "
        "Possible / Impossible refer to scenario difficulty. Bold = best in column.",
        "",
        "## Main results (overall, possible, impossible)",
        "",
        "| Finetuning   | Model              | Compl | Tool name | Tool args | Success | Poss. Compl | Poss. Succ | Imposs. Compl | Imposs. Succ |",
        "| :----------- | :----------------- | ----: | -------: | -------: | ------: | ----------: | ---------: | ------------: | -----------: |",
    ]

    for i, m in enumerate(models):
        ft = finetuning_type(m)
        o_compl = get(results[m], "completeness_pct")
        o_tname = get(results[m], "tool_name_match_pct")
        o_targs = get(results[m], "tool_args_match_pct")
        o_succ = get(results[m], "success_pct")
        p_compl = get(results[m], "by_impossibility", "possible", "completeness_pct")
        p_succ = get(results[m], "by_impossibility", "possible", "success_pct")
        i_compl = get(results[m], "by_impossibility", "impossible", "completeness_pct")
        i_succ = get(results[m], "by_impossibility", "impossible", "success_pct")

        row = [
            ft.ljust(11) if len(ft) <= 11 else ft,
            m,
            cell(o_compl, i in best_overall_compl),
            cell(o_tname, i in best_overall_tname),
            cell(o_targs, i in best_overall_targs),
            cell(o_succ, i in best_overall_succ),
            cell(p_compl, i in best_poss_compl),
            cell(p_succ, i in best_poss_succ),
            cell(i_compl, i in best_imp_compl),
            cell(i_succ, i in best_imp_succ),
        ]
        lines.append("| " + " | ".join(str(x) for x in row) + " |")

    domain_short = {
        "banking": "banking",
        "calendar_assistant": "calendar",
        "home_services": "home_services",
        "online_shopping": "online_shop",
        "restaurant_booking": "restaurant",
        "travel": "travel",
    }
    all_domains = set()
    for m in models:
        by_d = get(results[m], "by_domain") or {}
        all_domains.update(by_d.keys())
    all_domains = sorted(all_domains)
    domain_headers = [domain_short.get(d, d) for d in all_domains]

    lines.extend([
        "",
        "## By domain (success)",
        "",
        "Per-domain success rate. Use to compare **seen** vs **unseen** domains depending on your training setup.",
        "",
        "| Finetuning   | Model              | " + " | ".join(domain_headers) + " |",
        "| :----------- | :----------------- | " + " | ".join("-----:" for _ in all_domains) + " |",
    ])

    for m in models:
        ft = finetuning_type(m)
        by_d = get(results[m], "by_domain") or {}
        cells = [ft.ljust(11) if len(ft) <= 11 else ft, m]
        for d in all_domains:
            v = get(by_d, d, "success_pct")
            cells.append(f"{pct_to_dec(v):.2f}" if v is not None else "—")
        lines.append("| " + " | ".join(str(x) for x in cells) + " |")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Written: {out_path}")


if __name__ == "__main__":
    main()
