"""
reporter.py
-----------
Generate structured CSV and plain-text QC reports from metric results.

Each QC run produces:
  1. A timestamped CSV row appended to the running QC log
  2. A human-readable text summary printed to stdout and/or written to file
"""

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def build_record(
    scanner_id: str,
    metrics: Dict[str, float],
    tolerance_results: Dict[str, object],
    metadata: Optional[dict] = None,
    notes: str = "",
) -> dict:
    """
    Build a flat dict representing one QC run — suitable for CSV export.

    Parameters
    ----------
    scanner_id         : unique identifier for the CT scanner (e.g. "CT-01")
    metrics            : {metric_name: measured_value}
    tolerance_results  : {metric_name: ToleranceResult}
    metadata           : optional acquisition metadata dict from DicomSeries
    notes              : free-text note (e.g. "post-service QC")

    Returns
    -------
    dict  Flat record ready for csv.DictWriter
    """
    record = {
        "date":        datetime.now().strftime("%Y-%m-%d"),
        "time":        datetime.now().strftime("%H:%M"),
        "scanner_id":  scanner_id,
        "notes":       notes,
    }
    if metadata:
        record["kVp"]              = metadata.get("kVp", "")
        record["slice_thickness"]  = metadata.get("SliceThickness_mm", "")
        record["institution"]      = metadata.get("InstitutionName", "")
        record["manufacturer"]     = metadata.get("Manufacturer", "")
        record["model"]            = metadata.get("ModelName", "")

    for name, value in metrics.items():
        record[name] = round(value, 4) if isinstance(value, float) else value

    for name, result in tolerance_results.items():
        record[f"{name}_status"] = result.severity
        record[f"{name}_pass"]   = result.passed

    return record


def write_csv(record: dict, csv_path: str) -> None:
    """Append a QC record dict to a CSV file. Creates file + header if new."""
    path = Path(csv_path)
    write_header = not path.exists()
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=record.keys())
        if write_header:
            writer.writeheader()
        writer.writerow(record)
    logger.info("QC record appended to %s", csv_path)


def print_summary(
    scanner_id: str,
    metrics: Dict[str, float],
    tolerance_results: Dict[str, object],
    trend_results: Optional[Dict[str, dict]] = None,
) -> str:
    """
    Format and return a human-readable QC summary string.
    Also prints to stdout via logger.
    """
    lines = []
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines.append("=" * 60)
    lines.append(f"  CT QC REPORT  |  Scanner: {scanner_id}  |  {ts}")
    lines.append("=" * 60)

    # Metric results
    lines.append("")
    lines.append("METRIC RESULTS")
    lines.append("-" * 60)
    for name, value in metrics.items():
        result = tolerance_results.get(name)
        if result:
            status_icon = {"pass": "[PASS]", "warning": "[WARN]", "action": "[ACTION]"}.get(result.severity, "[ ?? ]")
            lines.append(f"  {status_icon}  {name:<30} {value:>10.3f}  |  {result.message}")
        else:
            lines.append(f"  [----]  {name:<30} {value:>10.3f}")

    # Overall pass/fail
    any_action  = any(r.severity == "action"  for r in tolerance_results.values())
    any_warning = any(r.severity == "warning" for r in tolerance_results.values())
    lines.append("")
    lines.append("-" * 60)
    if any_action:
        lines.append("  OVERALL: *** ACTION REQUIRED *** — contact supervising physicist immediately.")
    elif any_warning:
        lines.append("  OVERALL: WARNING — monitor closely. Notify physicist at next scheduled review.")
    else:
        lines.append("  OVERALL: PASS — all metrics within tolerance.")

    # Drift summary
    if trend_results:
        lines.append("")
        lines.append("DRIFT ANALYSIS")
        lines.append("-" * 60)
        for metric, stats in trend_results.items():
            if "drift_status" in stats:
                icon = {"stable": "[OK]", "warning": "[WARN]", "action": "[ACTION]"}.get(stats["drift_status"], "[ ? ]")
                lines.append(
                    f"  {icon}  {metric:<30} z={stats.get('z_score', 0):>+6.2f}  "
                    f"slope={stats.get('slope_per_meas', 0):>+.4f}/meas"
                )

    lines.append("=" * 60)
    summary = "\n".join(lines)
    print(summary)
    return summary


def write_text_report(summary: str, output_path: str) -> None:
    """Write the text summary to a file."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(summary)
    logger.info("Text report written to %s", output_path)
