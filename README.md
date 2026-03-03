# CT Phantom QA Analysis Scripts

> Automated quality control pipeline for CT imaging equipment.
> Parses DICOM phantom scan files, computes standard image quality metrics,
> checks results against ACR/AAPM tolerance limits, detects equipment drift,
> and produces structured CSV logs and trend plots — replacing a manual Excel workflow.

---

## Table of Contents

- [Overview](#overview)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Usage](#usage)
  - [Running the Full Pipeline](#running-the-full-pipeline)
  - [Using Individual Modules](#using-individual-modules)
  - [Configuration](#configuration)
- [Metrics Computed](#metrics-computed)
- [Output Files](#output-files)
- [Running Tests](#running-tests)
- [Extending the Pipeline](#extending-the-pipeline)
- [Clinical Context and Limitations](#clinical-context-and-limitations)
- [Dependencies](#dependencies)
- [License](#license)

---

## Overview

This project automates the CT phantom QA workflow used in diagnostic radiology
departments for routine equipment quality control. It is designed around the
**ACR CT Accreditation Phantom** protocol and produces outputs compatible with
ACR accreditation documentation requirements.

**What it does, step by step:**

1. Loads a DICOM series from a directory and converts stored pixel values to Hounsfield Units using `HU = pixel * RescaleSlope + RescaleIntercept`
2. Computes ACR standard QC metrics: noise, uniformity, CNR, HU accuracy
3. Evaluates results against two-level tolerance bands (warning and action limits)
4. Detects slow equipment drift by tracking z-scores across the historical CSV log
5. Generates Shewhart-style trend charts and an HU accuracy bar chart using Matplotlib
6. Appends a structured record to the running CSV log for long-term trending
7. Prints and saves a human-readable pass/fail summary report

**Who it is for:**

- Medical physics assistants and physicists performing routine CT QC
- Physics students learning CT image quality measurement principles
- Software engineers building clinical QC automation tools

---

## Project Structure

```
ct_phantom_qa/
|
|-- run_qc.py                   Main entry point. Runs the full pipeline.
|-- requirements.txt            Python package dependencies.
|-- .gitignore                  Excludes DICOM data and output files from Git.
|-- README.md                   This file.
|
|-- src/                        Core library modules.
|   |-- __init__.py
|   |-- dicom_loader.py         DICOM file I/O, HU conversion, DicomSeries class.
|   |-- metrics.py              QC metric functions: noise, uniformity, CNR, HU accuracy, slice thickness.
|   |-- tolerance.py            Tolerance band definitions and pass/fail evaluation.
|   |-- trending.py             CSV history management, drift detection, trend statistics.
|   |-- visualizer.py           Matplotlib plots: trend charts, ROI overlay, HU accuracy bar chart.
|   `-- reporter.py             CSV log writer and text report generator.
|
|-- config/
|   `-- tolerances.json         Customisable ACR/AAPM tolerance limits. Edit for your scanner.
|
|-- tests/
|   |-- test_metrics.py         Unit tests for all metric computations (no DICOM data required).
|   `-- test_tolerance.py       Unit tests for tolerance checker.
|
|-- data/
|   |-- README.md               Instructions for placing DICOM files.
|   `-- sample_dicoms/          Place .dcm files here. Excluded from Git by .gitignore.
|
`-- output/                     Auto-created on first run. All output files live here.
    |-- qc_log.csv              Running QC measurement log (appended each run).
    |-- plots/                  PNG charts: trend, ROI overlay, HU accuracy.
    `-- reports/                Text summary reports.
```

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/abe/ct-phantom-qa.git
cd ct-phantom-qa

# 2. Virtual environment
python3 -m venv .venv
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\activate           # Windows

# 3. Install
pip install -r requirements.txt

# 4. Place DICOM phantom scan files
mkdir -p data/sample_dicoms/session_01
cp /path/to/your/phantom/*.dcm data/sample_dicoms/session_01/

# 5. Run
python run_qc.py \
    --dicom_dir data/sample_dicoms/session_01 \
    --scanner_id CT-01

# 6. View results
cat output/reports/summary_*.txt
```

---

## Installation

### Requirements

- Python 3.9 or higher
- pip

### Install steps

```bash
pip install -r requirements.txt
```

### Verify

```bash
python3 -c "import pydicom, numpy, scipy, matplotlib; print('All dependencies OK')"
```

---

## Usage

### Running the Full Pipeline

```bash
python run_qc.py \
    --dicom_dir  data/sample_dicoms/session_20250115 \
    --scanner_id CT-GANTRY-02 \
    --output_dir output \
    --config     config/tolerances.json \
    --notes      "Post-service QC after tube replacement" \
    --verbose
```

**All arguments:**

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--dicom_dir` | Yes | — | Directory of .dcm files for one series |
| `--scanner_id` | No | `CT-01` | Unique scanner ID for logging |
| `--output_dir` | No | `output` | Root output directory |
| `--config` | No | None | Path to custom tolerances.json. Uses ACR defaults if omitted. |
| `--notes` | No | `""` | Free-text annotation (e.g. "routine daily", "post-service") |
| `--verbose` | No | False | Enable DEBUG logging |

---

### Using Individual Modules

Import any module independently in your own scripts or Jupyter notebooks:

```python
# Load a DICOM series and inspect metadata
from src.dicom_loader import load_series

series = load_series("data/sample_dicoms/session_01")
print(series.metadata)
# {'kVp': 120.0, 'SliceThickness_mm': 10.0, 'Rows': 512, 'Cols': 512, ...}

hu_slice = series.middle_slice     # 2D numpy array in HU
print(hu_slice.shape, hu_slice.mean())
```

```python
# Compute noise in a circular ROI
from src.metrics import ROI, measure_noise

rows, cols = hu_slice.shape
centre_roi = ROI(cx=cols // 2, cy=rows // 2, radius=30)
noise = measure_noise(hu_slice, centre_roi)
print(f"Noise: {noise:.2f} HU")
```

```python
# Check a measurement against ACR tolerance
from src.tolerance import ToleranceChecker

checker = ToleranceChecker()
result = checker.check("noise", noise)
print(result.severity)   # "pass", "warning", or "action"
print(result.message)
```

```python
# Plot a noise trend chart from historical records
from src.trending import load_csv_records, extract_series
from src.visualizer import plot_trend

records = load_csv_records("output/qc_log.csv")
dates, values = extract_series(records, "noise")

plot_trend(
    dates, values,
    metric_name="noise",
    units="HU",
    warning_upper=15.0,
    action_upper=20.0,
    output_path="output/plots/noise_trend.png"
)
```

---

### Configuration

Edit `config/tolerances.json` to set tolerance limits for your specific scanner
and institution protocols:

```json
{
  "noise": {
    "warning_upper": 15.0,
    "action_upper":  20.0,
    "units": "HU",
    "description": "Image noise SD. ACR baseline +/- 10 HU."
  },
  "uniformity_deviation": {
    "warning_upper": 5.0,
    "action_upper":  10.0,
    "units": "HU"
  }
}
```

**Two-level tolerance system:**

| Level | Meaning | Required Action |
|-------|---------|----------------|
| Pass | Within warning limits | Continue normal operation |
| Warning | Outside warning limits, inside action limits | Flag for physicist review |
| Action | Outside action limits | Take scanner offline. Contact supervising physicist immediately |

**ACR/AAPM default tolerances built into the system:**

| Metric | Warning | Action | Reference |
|--------|---------|--------|-----------|
| Noise (SD) | > 15 HU | > 20 HU | ACR + AAPM TG-233 |
| Uniformity deviation | > 5 HU | > 10 HU | ACR (centre vs. periphery) |
| HU accuracy — water | outside ±7 HU | outside ±15 HU | ACR Module 1 |
| HU accuracy — air | outside ±10 HU | outside ±20 HU | ACR Module 1 |
| Slice thickness | outside ±1 mm | outside ±2 mm | ACR Module 4 (slices >= 3 mm) |
| CNR | < 1.0 | < 0.5 | Baseline-dependent |

---

## Metrics Computed

### Noise

Standard deviation of HU values in a circular ROI placed over the uniform
water-equivalent region of the phantom:

```
Noise = std(HU values in ROI)
```

Noise rises as radiation dose decreases. Trending noise over time detects
detector degradation and protocol drift before they affect clinical image quality.

---

### Uniformity

Maximum absolute difference between peripheral ROI means and the centre ROI mean.
Five ROIs: one at phantom centre, four at top / bottom / left / right (~40% of
phantom radius offset from centre):

```
uniformity_deviation = max(| peripheral_mean_i - centre_mean |)
```

ACR tolerance: all peripheral ROIs within ±5 HU of centre for a water phantom.
Non-uniformity indicates detector calibration problems or beam hardening artifacts.

---

### CNR — Contrast-to-Noise Ratio

Quantifies how detectable a structure is against its background:

```
CNR = (mean_signal - mean_background) / noise_SD
```

Higher CNR means better low-contrast lesion detectability. CNR drops when
noise increases (lower dose) or when contrast decreases (incorrect protocol).

---

### HU Accuracy

Mean measured HU compared to expected HU for known phantom material inserts.
ACR Module 1 standard materials:

| Material | Expected HU |
|----------|------------|
| Air | -1000 |
| Polyethylene | -100 |
| Water | 0 |
| Acrylic | +120 |
| Bone-equivalent | +955 |

Radiologists rely on HU values to characterise tissue types (fat, blood, calcification).
Calibration drift in HU accuracy can affect diagnostic decisions.

---

### Slice Thickness (FWHM)

Estimated from a wire ramp axial profile using full-width at half-maximum (FWHM):

```
FWHM = width of the profile at 50% of (peak - baseline)
Slice thickness (mm) = FWHM_pixels * pixel_spacing_mm
```

A Gaussian fit method is also implemented for noisy profiles. ACR tolerance:
±1 mm from nominal for slices >= 3 mm.

---

## Output Files

```
output/
|-- qc_log.csv                          Running cumulative QC log. Appended each run.
|-- plots/
|   |-- roi_overlay_YYYYMMDD_HHMM.png  HU image slice with ROI circles overlaid.
|   |-- hu_accuracy_YYYYMMDD_HHMM.png  Bar chart: measured vs expected HU per material.
|   |-- trend_noise_YYYYMMDD_HHMM.png  Noise control chart with warning/action limits.
|   `-- trend_uniformity_*.png          Uniformity deviation control chart.
`-- reports/
    `-- summary_YYYYMMDD_HHMM.txt      Human-readable pass/fail report.
```

### CSV log columns

```
date, time, scanner_id, notes, kVp, slice_thickness, institution, manufacturer,
model, noise, uniformity_deviation, cnr, hu_water, hu_air,
noise_status, noise_pass, uniformity_deviation_status, ...
```

Status values: `pass`, `warning`, `action`

---

## Running Tests

No DICOM data is required. Tests use synthetic numpy arrays.

```bash
# Run all tests
pytest tests/ -v

# Run with coverage report
pytest tests/ -v --cov=src --cov-report=term-missing

# Run a single test class
pytest tests/test_metrics.py::TestNoise -v

# Run a single test
pytest tests/test_metrics.py::TestNoise::test_noise_close_to_true_sd -v
```

Expected output:

```
tests/test_metrics.py::TestROI::test_mask_shape                  PASSED
tests/test_metrics.py::TestROI::test_mask_is_boolean             PASSED
tests/test_metrics.py::TestROI::test_extract_returns_1d          PASSED
tests/test_metrics.py::TestROI::test_extract_pixel_count_approx  PASSED
tests/test_metrics.py::TestNoise::test_noise_close_to_true_sd    PASSED
tests/test_metrics.py::TestNoise::test_noise_zero_for_flat_image PASSED
tests/test_metrics.py::TestUniformity::test_perfect_uniformity   PASSED
...
tests/test_tolerance.py::TestToleranceBand::test_pass_within_limits  PASSED
tests/test_tolerance.py::TestToleranceBand::test_warning_triggered   PASSED
tests/test_tolerance.py::TestToleranceBand::test_action_triggered    PASSED
...
====================== 22 passed in 0.9s ======================
```

---

## Extending the Pipeline

### Add a new metric

1. Implement in `src/metrics.py`:

```python
def measure_my_metric(hu_slice: np.ndarray, roi: ROI) -> float:
    pixels = roi.extract(hu_slice)
    return float(some_computation(pixels))
```

2. Add tolerance band in `config/tolerances.json`:

```json
"my_metric": {
  "warning_upper": 10.0,
  "action_upper":  20.0,
  "units": "HU"
}
```

3. Add to `metrics` dict in `run_qc.py` and call `checker.check("my_metric", value)`.

4. Add unit tests in `tests/test_metrics.py`.

---

### Add MRI or Ultrasound QC

The architecture is modality-agnostic. To add MRI:

1. Create `src/mri_loader.py` — MRI DICOM uses different tags (TE, TR, flip angle, B0)
2. Create `src/mri_metrics.py` — SNR, geometric distortion, ghosting ratio, slice position
3. Create `run_mri_qc.py` following the same pipeline pattern as `run_qc.py`
4. Add MRI tolerances (ACR MRI accreditation limits) to `config/tolerances.json`

---

### Automate daily QC with cron (Linux/macOS)

```bash
crontab -e

# Run every weekday at 7:00 AM
0 7 * * 1-5 /path/to/.venv/bin/python /path/to/ct_phantom_qa/run_qc.py \
    --dicom_dir /dicom/daily_phantom \
    --scanner_id CT-01 \
    --output_dir /qc/output \
    >> /logs/qc_cron.log 2>&1
```

---

## Clinical Context and Limitations

**This software is a QC support tool, not a clinical decision system.**

- All QC results must be reviewed by a qualified Diagnostic Medical Physicist (ABR-certified).
- Out-of-tolerance findings must be escalated to the supervising physicist immediately.
- ROI positions in `run_qc.py` are defaults for a 25 cm DFOV, 512x512 matrix. They must be verified and adjusted for your specific phantom geometry and DFOV before clinical use.
- This software does not replace formal ACR accreditation testing procedures.
- Never use this software as the sole basis for clinical scanner clearance.
- Patient safety is paramount: when in doubt, take the scanner offline and contact your physicist.

### Regulatory context

CT QC programs in the United States are governed by:

- **ACR CT Accreditation Program** — sets minimum QC standards for accredited sites
- **AAPM Task Group 233** — comprehensive CT QC protocol recommendations
- **State radiation control programs** — some states have additional mandatory QC requirements
- **Joint Commission** — requires documented QC programs for accredited hospitals

---

## Dependencies

| Package | Version | License | Purpose |
|---------|---------|---------|---------|
| `pydicom` | >=2.4 | MIT | DICOM file I/O and tag extraction |
| `numpy` | >=1.24 | BSD-3 | Pixel array computations |
| `scipy` | >=1.10 | BSD-3 | Gaussian curve fitting, statistical checks |
| `matplotlib` | >=3.7 | PSF | All plots and visualisations |
| `pytest` | >=7.4 | MIT | Unit test runner |
| `pytest-cov` | >=4.0 | MIT | Test coverage reporting |

---

## License

MIT License

```
Copyright (c) 2025 Abenezer Chane

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.
```

---

*Abenezer Chane | abenezerchane@gmail.com | abenezerchane.dev*
