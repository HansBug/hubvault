"""Compare pytest-benchmark JSON reports and curated Phase 12 summaries."""

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, Tuple


def _load_report(path: Path) -> dict:
    """Load one JSON report from disk."""

    with path.open("r", encoding="utf-8") as fileobj:
        return json.load(fileobj)


def _report_kind(report: dict) -> str:
    """Detect the report format."""

    if isinstance(report.get("benchmarks"), list):
        return "pytest-benchmark"
    if isinstance(report.get("results"), dict):
        return "curated-summary"
    return "unknown"


def _normalize_machine(report: dict) -> Dict[str, object]:
    """Extract a cross-format machine signature."""

    raw = report.get("machine")
    if not isinstance(raw, dict):
        raw = report.get("machine_info", {})
    if not isinstance(raw, dict):
        return {}
    return {
        "python_version": raw.get("python_version", raw.get("python_implementation_version", "")),
        "python_implementation": raw.get("python_implementation", ""),
        "platform_system": raw.get("platform_system", raw.get("system", "")),
        "platform_release": raw.get("platform_release", raw.get("release", "")),
        "platform_machine": raw.get("platform_machine", raw.get("machine", "")),
        "platform_processor": raw.get("platform_processor", raw.get("processor", "")),
        "python_executable": raw.get("python_executable", ""),
    }


def _normalize_config(report: dict) -> Dict[str, object]:
    """Extract the comparable config surface from a curated summary."""

    raw = report.get("config", {})
    if not isinstance(raw, dict):
        return {}
    keys = (
        "scale",
        "scenario_set",
        "rounds",
        "warmup_rounds",
        "chunk_threshold",
        "large_file_size",
        "mixed_large_file_size",
        "history_deep_depth",
        "merge_side_commit_count",
        "cache_warm_rounds",
    )
    return {key: raw.get(key) for key in keys if key in raw}


def _extra_info(item: dict) -> dict:
    """Return the benchmark extra info payload."""

    payload = item.get("extra_info")
    if isinstance(payload, dict):
        return payload
    return {}


def _pytest_benchmark_rows(report: dict) -> Dict[str, dict]:
    """Normalize ``pytest-benchmark`` rows into a common comparison shape."""

    rows = {}
    for benchmark in report.get("benchmarks", []):
        name = benchmark.get("name") or benchmark.get("fullname")
        if not name:
            continue
        stats = benchmark.get("stats", {})
        extra = _extra_info(benchmark)
        rows[name] = {
            "name": name,
            "category": extra.get("category", ""),
            "dataset_family": extra.get("dataset_family", ""),
            "latency_p50_seconds": float(stats.get("median", 0.0)),
            "latency_iqr_seconds": float(stats.get("iqr", 0.0)),
            "sample_count": int(stats.get("rounds", 0)),
            "metrics": extra,
        }
    return rows


def _curated_summary_rows(report: dict) -> Dict[str, dict]:
    """Normalize curated summary rows into a common comparison shape."""

    rows = {}
    for name, payload in report.get("results", {}).items():
        if not isinstance(payload, dict):
            continue
        row = dict(payload)
        row["name"] = name
        rows[name] = row
    return rows


def _normalized_rows(report: dict) -> Dict[str, dict]:
    """Return the comparable row map for any supported report."""

    kind = _report_kind(report)
    if kind == "pytest-benchmark":
        return _pytest_benchmark_rows(report)
    if kind == "curated-summary":
        return _curated_summary_rows(report)
    return {}


def _metric_payload(row: dict) -> Dict[str, object]:
    """Flatten the interesting per-row metrics for diffing."""

    payload = {}
    metrics = row.get("metrics", {})
    if isinstance(metrics, dict):
        payload.update(metrics)
    for key in (
        "wall_clock_seconds",
        "latency_p50_seconds",
        "latency_p95_seconds",
        "latency_p99_seconds",
        "latency_iqr_seconds",
        "latency_stddev_seconds",
        "throughput_mib_per_sec",
        "throughput_stddev_mib_per_sec",
        "operations_per_sec",
        "operations_stddev_per_sec",
        "sample_count",
    ):
        if key in row:
            payload[key] = row.get(key)
    return payload


def _compare_metric(before_value: object, after_value: object) -> Dict[str, object]:
    """Build a before/after comparison payload for one metric."""

    comparison = {
        "before": before_value,
        "after": after_value,
    }
    if isinstance(before_value, (int, float)) and isinstance(after_value, (int, float)):
        delta = float(after_value) - float(before_value)
        comparison["delta"] = round(delta, 6)
        comparison["delta_ratio"] = round((delta / float(before_value)), 6) if float(before_value) else 0.0
    return comparison


def _iter_interesting_metrics() -> Iterable[str]:
    """Return the metric keys that should be surfaced in comparisons."""

    return (
        "processed_bytes",
        "operation_count",
        "wall_clock_seconds",
        "latency_p50_seconds",
        "latency_p95_seconds",
        "latency_p99_seconds",
        "latency_iqr_seconds",
        "latency_stddev_seconds",
        "throughput_mib_per_sec",
        "throughput_stddev_mib_per_sec",
        "operations_per_sec",
        "operations_stddev_per_sec",
        "files_materialized_per_sec",
        "write_amplification",
        "cache_amplification",
        "space_amplification_live",
        "space_amplification_live_after_gc",
        "space_amplification_unique",
        "space_amplification_unique_after_gc",
        "logical_live_bytes",
        "operation_seconds",
        "cache_delta_bytes",
        "chunk_pack_bytes_before_gc",
        "chunk_pack_bytes_after_gc",
        "dedup_gain_after_gc",
        "physical_over_unique_after_gc",
        "merge_status",
        "rewritten_commit_count",
        "threshold_boundary_at_chunked",
    )


def _build_row_comparison(name: str, before: dict, after: dict) -> Dict[str, object]:
    """Build one normalized scenario comparison row."""

    before_latency = float(before.get("latency_p50_seconds", 0.0))
    after_latency = float(after.get("latency_p50_seconds", 0.0))
    delta = after_latency - before_latency
    row = {
        "name": name,
        "category": after.get("category", before.get("category", "")),
        "dataset_family": after.get("dataset_family", before.get("dataset_family", "")),
        "before_latency_p50_seconds": round(before_latency, 6),
        "after_latency_p50_seconds": round(after_latency, 6),
        "latency_delta_seconds": round(delta, 6),
        "latency_delta_ratio": round((delta / before_latency), 6) if before_latency else 0.0,
    }

    before_payload = _metric_payload(before)
    after_payload = _metric_payload(after)
    metrics = {}
    for key in _iter_interesting_metrics():
        if key in before_payload or key in after_payload:
            metrics[key] = _compare_metric(before_payload.get(key), after_payload.get(key))
    if metrics:
        row["metrics"] = metrics
    return row


def _compare_category_summaries(before_report: dict, after_report: dict) -> Dict[str, dict]:
    """Compare per-category summary sections when both reports provide them."""

    before_sections = before_report.get("category_summaries", {})
    after_sections = after_report.get("category_summaries", {})
    if not isinstance(before_sections, dict) or not isinstance(after_sections, dict):
        return {}
    categories = sorted(set(before_sections) | set(after_sections))
    comparisons = {}
    for category in categories:
        before = before_sections.get(category)
        after = after_sections.get(category)
        if before is None or after is None:
            comparisons[category] = {
                "status": "added" if before is None else "removed",
            }
            continue
        metrics = {}
        keys = sorted(set(before) | set(after))
        for key in keys:
            if key == "scenarios":
                metrics[key] = {
                    "before": before.get(key, []),
                    "after": after.get(key, []),
                }
                continue
            metrics[key] = _compare_metric(before.get(key), after.get(key))
        comparisons[category] = metrics
    return comparisons


def _same_environment(before_report: dict, after_report: dict) -> Tuple[bool, bool]:
    """Return same-machine and same-config flags."""

    same_machine = _normalize_machine(before_report) == _normalize_machine(after_report)
    before_config = _normalize_config(before_report)
    after_config = _normalize_config(after_report)
    same_config = bool(before_config) and before_config == after_config
    return same_machine, same_config


def _threshold_map(report: dict) -> dict:
    """Return the threshold policy for curated summaries."""

    payload = report.get("threshold_policy", {})
    if isinstance(payload, dict):
        return payload
    return {}


def _evaluate_alerts(comparisons: Iterable[dict], threshold_policy: dict, same_machine: bool, same_config: bool) -> list:
    """Return alert rows for metrics that breach the configured thresholds."""

    if not threshold_policy:
        return []
    if threshold_policy.get("same_machine_required_for_alerts") and not same_machine:
        return []
    if threshold_policy.get("same_config_required_for_alerts") and not same_config:
        return []

    alerts = []
    latency_thresholds = threshold_policy.get("latency_p50_regression_ratio", {})
    throughput_thresholds = threshold_policy.get("throughput_regression_ratio", {})
    operations_thresholds = threshold_policy.get("operations_regression_ratio", {})
    amplification_thresholds = threshold_policy.get("amplification_growth_ratio", {})

    for row in comparisons:
        category = row.get("category", "")
        latency_ratio = float(row.get("latency_delta_ratio", 0.0))
        if category in latency_thresholds and latency_ratio > float(latency_thresholds[category]):
            alerts.append(
                {
                    "name": row["name"],
                    "metric": "latency_p50_seconds",
                    "category": category,
                    "delta_ratio": round(latency_ratio, 6),
                    "threshold": float(latency_thresholds[category]),
                }
            )
        metric_rows = row.get("metrics", {})
        throughput = metric_rows.get("throughput_mib_per_sec")
        if category in throughput_thresholds and isinstance(throughput, dict):
            delta_ratio = float(throughput.get("delta_ratio", 0.0))
            if delta_ratio < (0.0 - float(throughput_thresholds[category])):
                alerts.append(
                    {
                        "name": row["name"],
                        "metric": "throughput_mib_per_sec",
                        "category": category,
                        "delta_ratio": round(delta_ratio, 6),
                        "threshold": 0.0 - float(throughput_thresholds[category]),
                    }
                )
        operations = metric_rows.get("operations_per_sec")
        if category in operations_thresholds and isinstance(operations, dict):
            delta_ratio = float(operations.get("delta_ratio", 0.0))
            if delta_ratio < (0.0 - float(operations_thresholds[category])):
                alerts.append(
                    {
                        "name": row["name"],
                        "metric": "operations_per_sec",
                        "category": category,
                        "delta_ratio": round(delta_ratio, 6),
                        "threshold": 0.0 - float(operations_thresholds[category]),
                    }
                )
        for metric_name, threshold in amplification_thresholds.items():
            metric_row = metric_rows.get(metric_name)
            if not isinstance(metric_row, dict):
                continue
            delta_ratio = float(metric_row.get("delta_ratio", 0.0))
            if delta_ratio > float(threshold):
                alerts.append(
                    {
                        "name": row["name"],
                        "metric": metric_name,
                        "category": category,
                        "delta_ratio": round(delta_ratio, 6),
                        "threshold": float(threshold),
                    }
                )
    return alerts


def main() -> int:
    """Compare two benchmark reports."""

    parser = argparse.ArgumentParser(description="Compare two benchmark JSON reports.")
    parser.add_argument("before", help="Older benchmark JSON path.")
    parser.add_argument("after", help="Newer benchmark JSON path.")
    args = parser.parse_args()

    before_path = Path(args.before)
    after_path = Path(args.after)
    before_report = _load_report(before_path)
    after_report = _load_report(after_path)

    before_rows = _normalized_rows(before_report)
    after_rows = _normalized_rows(after_report)
    names = sorted(set(before_rows) | set(after_rows))

    comparisons = []
    for name in names:
        before = before_rows.get(name)
        after = after_rows.get(name)
        if before is None or after is None:
            comparisons.append(
                {
                    "name": name,
                    "status": "added" if before is None else "removed",
                }
            )
            continue
        comparisons.append(_build_row_comparison(name, before, after))

    same_machine, same_config = _same_environment(before_report, after_report)
    threshold_policy = _threshold_map(after_report) or _threshold_map(before_report)
    alerts = _evaluate_alerts(comparisons, threshold_policy, same_machine, same_config)

    output = {
        "before": {
            "path": str(before_path),
            "kind": _report_kind(before_report),
            "generated_at_utc": before_report.get("generated_at_utc", ""),
            "git": before_report.get("git", {}),
            "machine": _normalize_machine(before_report),
            "config": _normalize_config(before_report),
        },
        "after": {
            "path": str(after_path),
            "kind": _report_kind(after_report),
            "generated_at_utc": after_report.get("generated_at_utc", ""),
            "git": after_report.get("git", {}),
            "machine": _normalize_machine(after_report),
            "config": _normalize_config(after_report),
        },
        "environment": {
            "same_machine": same_machine,
            "same_config": same_config,
        },
        "threshold_policy": threshold_policy,
        "alerts": alerts,
        "category_comparisons": _compare_category_summaries(before_report, after_report),
        "comparisons": comparisons,
    }
    if not same_machine:
        output["warning"] = "machine signature mismatch; regression alerts are informational only"
    elif _normalize_config(before_report) and not same_config:
        output["warning"] = "benchmark config mismatch; regression alerts are informational only"

    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
