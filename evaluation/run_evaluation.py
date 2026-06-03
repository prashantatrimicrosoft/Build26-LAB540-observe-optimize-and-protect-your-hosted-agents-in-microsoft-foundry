#!/usr/bin/env python3
# Copyright (c) Microsoft. All rights reserved.
"""Run evaluation on the Zava Travel Concierge using custom and built-in evaluators.

Usage:
    # Run custom evaluators only (no Azure credentials needed)
    python run_evaluation.py

    # Run with built-in LLM-based evaluators (requires .env with Azure credentials)
    python run_evaluation.py --builtin

    # Point at a different JSONL file
    python run_evaluation.py --data path/to/data.jsonl

    # Write results to a JSON file
    python run_evaluation.py --output results.json
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Ensure the evaluation/ directory is on sys.path so evaluators.py is importable
sys.path.insert(0, str(Path(__file__).parent))

from evaluators import (
    CompletenessEvaluator,
    DataAccuracyEvaluator,
    PolicyComplianceEvaluator,
)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_REPO_ROOT  = Path(__file__).resolve().parent.parent
_DATA_FILE  = _REPO_ROOT / "data" / "jsonl" / "evaluation_data.jsonl"
_DATA_DIR   = _REPO_ROOT / "data" / "csv"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def print_table(rows: list[dict], metrics: list[str]) -> None:
    """Print a simple ASCII results table."""
    col_w = 52
    metric_w = 22

    header = f"{'Query':<{col_w}}" + "".join(f"{m:<{metric_w}}" for m in metrics)
    print("\n" + "=" * (col_w + metric_w * len(metrics)))
    print(header)
    print("-" * (col_w + metric_w * len(metrics)))

    for row in rows:
        query_short = (row["query"][:49] + "…") if len(row["query"]) > 50 else row["query"]
        line = f"{query_short:<{col_w}}"
        for m in metrics:
            val  = row.get(m, "—")
            res  = row.get(f"{m}_result", "")
            cell = f"{val}/5 {'✓' if res == 'pass' else '✗'}"
            line += f"{cell:<{metric_w}}"
        print(line)

    print("=" * (col_w + metric_w * len(metrics)))


def print_summary(rows: list[dict], metrics: list[str]) -> None:
    """Print per-metric averages and pass rates."""
    print("\n--- Summary ---")
    for m in metrics:
        scores  = [r[m] for r in rows if m in r]
        passes  = [r for r in rows if r.get(f"{m}_result") == "pass"]
        if not scores:
            continue
        avg      = sum(scores) / len(scores)
        pass_pct = 100 * len(passes) / len(rows)
        print(f"  {m:<28} avg={avg:.2f}/5   pass={pass_pct:.0f}%  ({len(passes)}/{len(rows)})")


def run_custom_evaluators(
    data: list[dict],
    data_dir: Path,
) -> tuple[list[dict], list[str]]:
    """Run the three custom evaluators against every row and return annotated rows."""
    completeness  = CompletenessEvaluator()
    data_accuracy = DataAccuracyEvaluator(data_dir=data_dir)
    policy        = PolicyComplianceEvaluator(data_dir=data_dir)

    metrics = ["completeness", "data_accuracy", "policy_compliance"]
    results = []

    for row in data:
        annotated = dict(row)

        comp_out  = completeness(query=row["query"], response=row["response"])
        acc_out   = data_accuracy(response=row["response"])
        pol_out   = policy(response=row["response"])

        annotated.update(comp_out)
        annotated.update(acc_out)
        annotated.update(pol_out)

        results.append(annotated)

    return results, metrics


def run_builtin_evaluators(data_file: Path, output_dir: Path) -> None:
    """Run built-in LLM-based evaluators via azure-ai-evaluation (requires Azure credentials)."""
    try:
        from azure.ai.evaluation import (
            CoherenceEvaluator,
            FluencyEvaluator,
            GroundednessEvaluator,
            RelevanceEvaluator,
            evaluate,
        )
        from dotenv import load_dotenv
    except ImportError:
        print(
            "\n[!] azure-ai-evaluation is not installed. "
            "Run: pip install azure-ai-evaluation\n"
            "    Skipping built-in evaluators.\n"
        )
        return

    load_dotenv()

    endpoint   = (
        os.environ.get("AZURE_AI_FOUNDRY_ENDPOINT")
        or os.environ.get("AZURE_OPENAI_ENDPOINT")
        or os.environ.get("AZURE_AI_PROJECT_ENDPOINT")
    )
    deployment = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4.1-mini")

    if not endpoint:
        print(
            "\n[!] AZURE_AI_PROJECT_ENDPOINT not set. "
            "Copy scripts/sample.env → .env and fill in your values.\n"
            "    Skipping built-in evaluators.\n"
        )
        return

    # Strip Foundry project path suffix so we're left with the base
    # services endpoint that the Azure OpenAI-compatible API lives at.
    # e.g. https://xxx.services.ai.azure.com/api/projects/yyy  →  https://xxx.services.ai.azure.com
    import re as _re
    base_endpoint = _re.sub(r"/api/projects/[^/?]+/?$", "", endpoint.rstrip("/"))

    model_config = {
        "azure_endpoint": base_endpoint,
        "azure_deployment": deployment,
        "api_version": "2025-01-01-preview",
    }

    print("\nRunning built-in LLM evaluators (this may take a few minutes)…")

    builtin_evaluators = {
        "relevance":    RelevanceEvaluator(model_config),
        "groundedness": GroundednessEvaluator(model_config),
        "coherence":    CoherenceEvaluator(model_config),
        "fluency":      FluencyEvaluator(model_config),
    }

    builtin_col_mapping = {
        "relevance":    {"column_mapping": {"query": "${data.query}", "response": "${data.response}"}},
        "groundedness": {"column_mapping": {"query": "${data.query}", "context": "${data.context}", "response": "${data.response}"}},
        "coherence":    {"column_mapping": {"query": "${data.query}", "response": "${data.response}"}},
        "fluency":      {"column_mapping": {"response": "${data.response}"}},
    }

    result = evaluate(
        data=str(data_file),
        evaluators=builtin_evaluators,
        evaluator_config=builtin_col_mapping,
        output_path=str(output_dir / "builtin_eval_results.json"),
    )

    print(f"\nBuilt-in evaluation complete. Metrics summary:")
    for k, v in result.get("metrics", {}).items():
        print(f"  {k:<30} {v:.3f}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the Zava Travel Concierge.")
    parser.add_argument("--data",    default=str(_DATA_FILE),  help="Path to evaluation JSONL file")
    parser.add_argument("--output",  default=None,             help="Path to write JSON results")
    parser.add_argument("--builtin", action="store_true",      help="Also run built-in LLM evaluators (requires Azure credentials)")
    args = parser.parse_args()

    data_file = Path(args.data)
    if not data_file.exists():
        print(f"[!] Data file not found: {data_file}")
        sys.exit(1)

    print(f"Loading evaluation data from: {data_file}")
    data = load_jsonl(data_file)
    print(f"  {len(data)} rows loaded.\n")

    # ── Custom evaluators ──────────────────────────────────────────────────
    print("Running custom evaluators…")
    results, metrics = run_custom_evaluators(data, _DATA_DIR)

    print_table(results, metrics)
    print_summary(results, metrics)

    # ── Failures detail ────────────────────────────────────────────────────
    failures = [r for r in results if any(r.get(f"{m}_result") == "fail" for m in metrics)]
    if failures:
        print(f"\n--- Failures ({len(failures)}) ---")
        for r in failures:
            print(f"\n  Query   : {r['query']}")
            for m in metrics:
                if r.get(f"{m}_result") == "fail":
                    reason = r.get(f"{m}_reason", "")
                    print(f"  {m}: FAIL — {reason}")

    # ── Comparison: built-in pass vs custom fail ───────────────────────────
    # (Only meaningful after built-in results are merged — show concept)
    multi_component = [r for r in results if len(r.get("completeness_components_requested", [])) >= 2]
    if multi_component:
        print(f"\n--- Multi-component requests ({len(multi_component)}) ---")
        for r in multi_component:
            score = r.get("completeness", "?")
            result_flag = r.get("completeness_result", "?")
            print(f"  [{result_flag.upper():4}] score={score}/5  \"{r['query'][:70]}\"")

    # ── Optional: output JSON ──────────────────────────────────────────────
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\nResults written to: {out_path}")

    # ── Optional: built-in LLM evaluators ─────────────────────────────────
    if args.builtin:
        output_dir = Path(args.output).parent if args.output else _REPO_ROOT / "evaluation"
        run_builtin_evaluators(data_file, output_dir)

    print("\nDone.")


if __name__ == "__main__":
    main()
