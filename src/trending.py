"""
trending.py
-----------
Load historical QC records from CSV, compute trend statistics,
and detect drift before it becomes a clinical failure.

The trending system compares each new measurement to the
rolling baseline (mean +/- k*SD of recent N measurements).
"""

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

BASELINE_WINDOW = 20   # number of recent measurements to compute rolling baseline
WARNING_K       = 2.0  # k-sigma warning threshold
ACTION_K        = 3.0  # k-sigma action threshold


def load_csv_records(csv_path: str) -> List[dict]:
    """
    Load QC history from a CSV file.

    Expected columns (case-insensitive):
        date, noise, uniformity_deviation, hu_water, hu_air,
        slice_thickness, cnr, scanner_id

    Returns list of dicts with numeric values converted to float.
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"QC record file not found: {csv_path}")

    records = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cleaned = {}
            for k, v in row.items():
                key = k.strip().lower()
                try:
                    cleaned[key] = float(v.strip())
                except (ValueError, AttributeError):
                    cleaned[key] = v.strip() if isinstance(v, str) else v
            records.append(cleaned)
    logger.info("Loaded %d QC records from %s", len(records), csv_path)
    return records


def append_csv_record(csv_path: str, record: dict) -> None:
    """Append a single QC result dict to the CSV log. Creates file if absent."""
    path = Path(csv_path)
    write_header = not path.exists()
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=record.keys())
        if write_header:
            writer.writeheader()
        writer.writerow(record)
    logger.info("Appended QC record to %s", csv_path)


def extract_series(records: List[dict], metric: str) -> Tuple[List[str], List[float]]:
    """Extract (dates, values) for a single metric from a list of records."""
    dates, values = [], []
    for r in records:
        if metric in r and r[metric] != "":
            try:
                values.append(float(r[metric]))
                dates.append(r.get("date", ""))
            except (ValueError, TypeError):
                pass
    return dates, values


def compute_trend_stats(values: List[float]) -> dict:
    """
    Compute rolling baseline statistics for drift detection.

    Uses the most recent BASELINE_WINDOW measurements as the reference window.
    """
    if len(values) < 3:
        return {"status": "insufficient_data", "n": len(values)}

    arr = np.array(values, dtype=float)
    window = arr[-BASELINE_WINDOW:] if len(arr) >= BASELINE_WINDOW else arr

    baseline_mean = float(np.mean(window))
    baseline_sd   = float(np.std(window, ddof=1))
    latest        = float(arr[-1])

    z_score = (latest - baseline_mean) / baseline_sd if baseline_sd > 0 else 0.0

    if abs(z_score) >= ACTION_K:
        drift_status = "action"
    elif abs(z_score) >= WARNING_K:
        drift_status = "warning"
    else:
        drift_status = "stable"

    # Linear regression for overall trend slope
    x = np.arange(len(arr), dtype=float)
    slope = float(np.polyfit(x, arr, 1)[0])

    return {
        "n":              len(arr),
        "baseline_mean":  round(baseline_mean, 4),
        "baseline_sd":    round(baseline_sd, 4),
        "latest":         round(latest, 4),
        "z_score":        round(z_score, 3),
        "drift_status":   drift_status,
        "slope_per_meas": round(slope, 6),
    }


def detect_drift(records: List[dict], metrics: Optional[List[str]] = None) -> Dict[str, dict]:
    """
    Run drift detection across all metrics (or a specified subset).

    Returns dict of {metric: trend_stats}.
    """
    if not metrics:
        numeric_keys = [k for k, v in records[0].items()
                        if isinstance(v, float)] if records else []
        metrics = [k for k in numeric_keys if k != "date"]

    results = {}
    for metric in metrics:
        _, values = extract_series(records, metric)
        results[metric] = compute_trend_stats(values)
        status = results[metric].get("drift_status", "?")
        if status in ("warning", "action"):
            logger.warning("Drift detected in %s: status=%s", metric, status)
    return results
