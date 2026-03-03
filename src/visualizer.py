"""
visualizer.py
-------------
Generate QC plots:
  1. ROI overlay on HU slice (verification that ROIs are placed correctly)
  2. Metric trend charts with control limits
  3. HU accuracy bar chart
  4. Summary dashboard figure
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")           # non-interactive backend for scripts/servers
import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np

logger = logging.getLogger(__name__)


def plot_roi_overlay(
    hu_slice: np.ndarray,
    rois: Dict[str, "ROI"],          # ROI objects from metrics.py
    title: str = "ROI Overlay",
    output_path: Optional[str] = None,
    window_center: float = 0,
    window_width: float = 400,
) -> plt.Figure:
    """
    Display HU slice with ROI circles overlaid.

    Parameters
    ----------
    hu_slice     : 2-D HU array
    rois         : dict of {label: ROI}
    window_center: CT window centre in HU (default 0 = soft tissue)
    window_width : CT window width  in HU (default 400)

    Returns
    -------
    matplotlib Figure (saved to output_path if provided)
    """
    vmin = window_center - window_width / 2
    vmax = window_center + window_width / 2

    fig, ax = plt.subplots(figsize=(8, 8))
    ax.imshow(hu_slice, cmap="gray", vmin=vmin, vmax=vmax, origin="upper")

    colors = plt.cm.Set1(np.linspace(0, 1, max(len(rois), 1)))
    for (label_name, roi), color in zip(rois.items(), colors):
        circle = patches.Circle(
            (roi.cx, roi.cy), roi.radius,
            linewidth=2, edgecolor=color, facecolor="none", label=label_name
        )
        ax.add_patch(circle)
        ax.text(roi.cx, roi.cy - roi.radius - 8, label_name,
                color=color, fontsize=9, ha="center",
                bbox=dict(facecolor="black", alpha=0.5, pad=2))

    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.set_xlabel("Column (px)")
    ax.set_ylabel("Row (px)")
    ax.legend(loc="upper right", fontsize=8, framealpha=0.7)
    plt.tight_layout()

    if output_path:
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        logger.info("Saved ROI overlay to %s", output_path)
    return fig


def plot_trend(
    dates: List[str],
    values: List[float],
    metric_name: str,
    units: str = "HU",
    warning_upper: Optional[float] = None,
    warning_lower: Optional[float] = None,
    action_upper:  Optional[float] = None,
    action_lower:  Optional[float] = None,
    baseline_mean: Optional[float] = None,
    title: Optional[str] = None,
    output_path: Optional[str] = None,
) -> plt.Figure:
    """
    Shewhart-style control chart for a QC metric over time.

    Plots:
    - Individual measurements (blue dots + line)
    - Warning limits (orange dashed)
    - Action limits (red dashed)
    - Baseline mean (green dashed)
    """
    fig, ax = plt.subplots(figsize=(12, 5))

    x = range(len(values))
    ax.plot(x, values, "o-", color="#2E75B6", linewidth=1.5,
            markersize=5, label="Measured", zorder=3)

    # Control limits
    if action_upper  is not None: ax.axhline(action_upper,  color="red",    ls="--", lw=1.5, alpha=0.8, label=f"Action upper ({action_upper})")
    if action_lower  is not None: ax.axhline(action_lower,  color="red",    ls="--", lw=1.5, alpha=0.8, label=f"Action lower ({action_lower})")
    if warning_upper is not None: ax.axhline(warning_upper, color="orange", ls="--", lw=1.5, alpha=0.8, label=f"Warning upper ({warning_upper})")
    if warning_lower is not None: ax.axhline(warning_lower, color="orange", ls="--", lw=1.5, alpha=0.8, label=f"Warning lower ({warning_lower})")
    if baseline_mean is not None: ax.axhline(baseline_mean, color="green",  ls="-",  lw=1.0, alpha=0.6, label=f"Baseline mean ({baseline_mean:.2f})")

    # Colour out-of-tolerance points red
    if action_upper is not None or action_lower is not None:
        for i, v in enumerate(values):
            out = (action_upper is not None and v > action_upper) or                   (action_lower is not None and v < action_lower)
            if out:
                ax.plot(i, v, "o", color="red", markersize=10, zorder=4)

    # X-axis tick labels (show every N-th date to avoid overlap)
    if dates:
        step = max(1, len(dates) // 12)
        ax.set_xticks(list(range(0, len(dates), step)))
        ax.set_xticklabels([dates[i] for i in range(0, len(dates), step)],
                           rotation=35, ha="right", fontsize=8)
    else:
        ax.set_xlabel("Measurement #")

    ax.set_ylabel(f"{metric_name} ({units})")
    ax.set_title(title or f"{metric_name} Trend Chart", fontsize=13, fontweight="bold")
    ax.legend(fontsize=8, loc="upper left")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    if output_path:
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        logger.info("Saved trend chart to %s", output_path)
    return fig


def plot_hu_accuracy(
    hu_accuracy_results: Dict[str, Dict],
    output_path: Optional[str] = None,
) -> plt.Figure:
    """
    Bar chart comparing measured vs. expected HU for phantom materials.
    Bars are coloured green (pass) or red (fail).
    """
    materials  = list(hu_accuracy_results.keys())
    measured   = [r["measured_HU"]  for r in hu_accuracy_results.values()]
    expected   = [r["expected_HU"]  for r in hu_accuracy_results.values()]
    errors     = [r["error_HU"]     for r in hu_accuracy_results.values()]
    pass_flags = [r["pass"]         for r in hu_accuracy_results.values()]

    x = np.arange(len(materials))
    width = 0.35
    colors = ["#2E7D32" if p else "#C62828" for p in pass_flags]

    fig, ax = plt.subplots(figsize=(10, 6))
    bars1 = ax.bar(x - width/2, measured, width, label="Measured HU", color=colors, alpha=0.85)
    bars2 = ax.bar(x + width/2, expected, width, label="Expected HU",
                   color="#90A4AE", alpha=0.85, edgecolor="black", linewidth=0.8)

    # Error labels on measured bars
    for bar, err, passed in zip(bars1, errors, pass_flags):
        label = f"{err:+.1f} HU"
        color = "darkgreen" if passed else "darkred"
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 15,
                label, ha="center", va="bottom", fontsize=9, color=color, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(materials, fontsize=11)
    ax.set_ylabel("Hounsfield Units (HU)", fontsize=11)
    ax.set_title("CT HU Accuracy — Phantom Material Verification", fontsize=13, fontweight="bold")
    ax.legend(fontsize=10)
    ax.axhline(0, color="black", linewidth=0.8, alpha=0.4)
    ax.grid(True, axis="y", alpha=0.3)
    plt.tight_layout()

    if output_path:
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        logger.info("Saved HU accuracy chart to %s", output_path)
    return fig


def close_all():
    """Close all matplotlib figures (call after saving to free memory)."""
    plt.close("all")
