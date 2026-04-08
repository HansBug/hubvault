"""Compare two pytest-benchmark JSON reports."""

import argparse
import json
from pathlib import Path


def _load_report(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fileobj:
        return json.load(fileobj)


def _benchmark_map(report: dict) -> dict:
    items = {}
    for benchmark in report.get("benchmarks", []):
        name = benchmark.get("name") or benchmark.get("fullname")
        if not name:
            continue
        items[name] = benchmark
    return items


def _median_seconds(item: dict) -> float:
    stats = item.get("stats", {})
    value = stats.get("median", 0.0)
    return float(value)


def _extra_info(item: dict) -> dict:
    payload = item.get("extra_info")
    if isinstance(payload, dict):
        return payload
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare two pytest-benchmark JSON reports.")
    parser.add_argument("before", help="Older benchmark JSON path.")
    parser.add_argument("after", help="Newer benchmark JSON path.")
    args = parser.parse_args()

    before_report = _benchmark_map(_load_report(Path(args.before)))
    after_report = _benchmark_map(_load_report(Path(args.after)))

    names = sorted(set(before_report) | set(after_report))
    rows = []
    for name in names:
        before = before_report.get(name)
        after = after_report.get(name)
        if before is None or after is None:
            rows.append(
                {
                    "name": name,
                    "status": "added" if before is None else "removed",
                }
            )
            continue

        before_median = _median_seconds(before)
        after_median = _median_seconds(after)
        delta = after_median - before_median
        delta_ratio = (delta / before_median) if before_median else 0.0
        row = {
            "name": name,
            "before_median_seconds": round(before_median, 6),
            "after_median_seconds": round(after_median, 6),
            "delta_seconds": round(delta, 6),
            "delta_ratio": round(delta_ratio, 6),
        }

        before_extra = _extra_info(before)
        after_extra = _extra_info(after)
        interesting_keys = (
            "processed_bytes",
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
        extras = {}
        for key in interesting_keys:
            if key in before_extra or key in after_extra:
                extras[key] = {
                    "before": before_extra.get(key),
                    "after": after_extra.get(key),
                }
        if extras:
            row["extra_metrics"] = extras
        rows.append(row)

    print(json.dumps({"comparisons": rows}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
