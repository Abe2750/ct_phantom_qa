#!/usr/bin/env python3
"""
run_qc.py
---------
Main entry point for the CT Phantom QA pipeline.

Usage
-----
    python run_qc.py --dicom_dir data/sample_dicoms/session_01 \
                     --scanner_id CT-01 \
                     --output_dir output \
                     --config config/tolerances.json

The script will:
  1. Load DICOM series and convert to HU
  2. Compute noise, uniformity, CNR, HU accuracy metrics
  3. Check results against tolerances
  4. Detect drift vs. historical records
  5. Generate trend plots and HU accuracy bar chart
  6. Append results to CSV log
  7. Print text summary report

Outputs (in --output_dir)
-------------------------
  plots/roi_overlay_<date>.png
  plots/trend_noise_<date>.png
  plots/trend_uniformity_<date>.png
  plots/hu_accuracy_<date>.png
  reports/summary_<date>.txt
  qc_log.csv
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add src to path when running from project root
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dicom_loader import load_series
from metrics import (
    ROI, measure_noise, measure_uniformity,
    measure_cnr, measure_hu_accuracy
)
from tolerance import ToleranceChecker
from trending import load_csv_records, append_csv_record, detect_drift
from visualizer import plot_roi_overlay, plot_trend, plot_hu_accuracy, close_all
from reporter import build_record, write_csv, print_summary, write_text_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_qc")


def build_acr_rois(rows: int, cols: int) -> dict:
    """
    Build a standard set of ROIs for a circular water phantom.

    Positions are defined as fractions of image dimensions so the
    function works regardless of matrix size. Adjust fractions for
    your specific phantom geometry.
    """
    cx, cy = cols // 2, rows // 2
    r_centre  = min(rows, cols) // 14   # ~3cm for a 25cm DFOV, 512x512 matrix
    r_periph  = r_centre

    # Peripheral ROIs offset ~40% of phantom radius from centre
    offset = min(rows, cols) // 5

    return {
        "centre": ROI(cx, cy, r_centre),
        "top":    ROI(cx,          cy - offset, r_periph),
        "bottom": ROI(cx,          cy + offset, r_periph),
        "left":   ROI(cx - offset, cy,          r_periph),
        "right":  ROI(cx + offset, cy,          r_periph),
    }


def run_pipeline(args):
    date_str = datetime.now().strftime("%Y%m%d_%H%M")
    out      = Path(args.output_dir)
    plots    = out / "plots"
    reports  = out / "reports"
    plots.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)
    csv_path = str(out / "qc_log.csv")

    # ── 1. Load DICOM ──────────────────────────────────────────────────
    logger.info("Loading DICOM series from %s", args.dicom_dir)
    series    = load_series(args.dicom_dir)
    hu_slice  = series.middle_slice
    meta      = series.metadata
    rows, cols = hu_slice.shape
    logger.info("Series: %dx%d, %d slices, kVp=%.0f", rows, cols, meta["NumSlices"], meta["kVp"])

    # ── 2. Build ROIs ──────────────────────────────────────────────────
    rois = build_acr_rois(rows, cols)

    # ── 3. Compute metrics ─────────────────────────────────────────────
    centre_roi     = rois["centre"]
    peripheral_rois = {k: v for k, v in rois.items() if k != "centre"}

    noise    = measure_noise(hu_slice, centre_roi)
    uni_data = measure_uniformity(hu_slice, centre_roi, peripheral_rois)
    cnr      = measure_cnr(hu_slice, rois["right"], centre_roi)

    # HU accuracy: place manual ROIs over known phantom material inserts
    # These positions assume standard ACR Module 1 phantom geometry.
    # Adjust cx/cy for your phantom and DFOV.
    r_insert = max(5, rows // 50)
    offset_x = cols // 6
    hu_acc_rois = {
        "water":        (ROI(cols // 2,           rows // 2,           r_insert),    0.0),
        "air":          (ROI(cols // 2,           rows // 2 - offset_x, r_insert), -1000.0),
        "polyethylene": (ROI(cols // 2 - offset_x, rows // 2,          r_insert),  -100.0),
        "acrylic":      (ROI(cols // 2 + offset_x, rows // 2,          r_insert),   120.0),
    }
    hu_acc = measure_hu_accuracy(hu_slice, hu_acc_rois)

    metrics = {
        "noise":                noise,
        "uniformity_deviation": uni_data["max_deviation_HU"],
        "cnr":                  cnr,
        "hu_water":             hu_acc["water"]["measured_HU"],
        "hu_air":               hu_acc["air"]["measured_HU"],
    }
    logger.info("Metrics: %s", {k: f"{v:.2f}" for k, v in metrics.items()})

    # ── 4. Tolerance checks ────────────────────────────────────────────
    checker   = ToleranceChecker.from_config(args.config) if args.config else ToleranceChecker()
    tol_results = checker.check_all(metrics)

    # ── 5. Drift detection ─────────────────────────────────────────────
    trend_results = {}
    if Path(csv_path).exists():
        records = load_csv_records(csv_path)
        trend_results = detect_drift(records, list(metrics.keys()))
    else:
        logger.info("No QC history found — skipping drift analysis for first run.")

    # ── 6. Plots ───────────────────────────────────────────────────────
    plot_roi_overlay(
        hu_slice, rois,
        title=f"ROI Overlay — {args.scanner_id} — {date_str}",
        output_path=str(plots / f"roi_overlay_{date_str}.png"),
    )
    plot_hu_accuracy(
        hu_acc,
        output_path=str(plots / f"hu_accuracy_{date_str}.png"),
    )

    if Path(csv_path).exists():
        from trending import load_csv_records, extract_series
        hist = load_csv_records(csv_path)
        for metric, (warn_u, act_u) in {
            "noise":                (15.0, 20.0),
            "uniformity_deviation": (5.0,  10.0),
        }.items():
            dates, vals = extract_series(hist, metric)
            if vals:
                plot_trend(
                    dates, vals, metric_name=metric,
                    warning_upper=warn_u, action_upper=act_u,
                    output_path=str(plots / f"trend_{metric}_{date_str}.png"),
                )

    close_all()

    # ── 7. Report & log ────────────────────────────────────────────────
    summary = print_summary(args.scanner_id, metrics, tol_results, trend_results)
    write_text_report(summary, str(reports / f"summary_{date_str}.txt"))

    record = build_record(args.scanner_id, metrics, tol_results, meta, notes=args.notes)
    write_csv(record, csv_path)
    logger.info("Pipeline complete. Outputs in: %s", out)


def main():
    parser = argparse.ArgumentParser(
        description="CT Phantom QA Analysis Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--dicom_dir",  required=True,  help="Path to DICOM series directory")
    parser.add_argument("--scanner_id", default="CT-01", help="Scanner identifier (default: CT-01)")
    parser.add_argument("--output_dir", default="output", help="Output directory (default: ./output)")
    parser.add_argument("--config",     default=None,   help="Path to tolerances JSON config")
    parser.add_argument("--notes",      default="",     help="Free-text note for this QC run")
    parser.add_argument("--verbose",    action="store_true", help="Enable DEBUG logging")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    run_pipeline(args)


if __name__ == "__main__":
    main()
