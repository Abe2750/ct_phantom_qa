"""
metrics.py
----------
Core CT QC metric computations on HU arrays.

All functions accept a 2-D numpy array (single HU slice) and an ROI
definition, and return a float or dict of floats.

Metrics implemented
-------------------
- Noise          : SD of HU values in a uniform ROI
- Uniformity     : centre vs. peripheral ROI mean difference
- CNR            : contrast-to-noise ratio between two ROIs
- HU Accuracy    : mean HU in a material ROI vs. expected value
- Slice Thickness: FWHM of the axial edge-spread profile (wire ramp method)
"""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np
from scipy.ndimage import label
from scipy.optimize import curve_fit


@dataclass
class ROI:
    """
    Circular ROI defined by centre pixel and radius in pixels.

    Parameters
    ----------
    cx, cy : int   Centre column and row (pixel coordinates).
    radius : int   Radius in pixels.
    """
    cx: int
    cy: int
    radius: int

    def mask(self, shape: Tuple[int, int]) -> np.ndarray:
        """Return a boolean mask of shape (rows, cols) for this ROI."""
        rows, cols = shape
        y, x = np.ogrid[:rows, :cols]
        return (x - self.cx) ** 2 + (y - self.cy) ** 2 <= self.radius ** 2

    def extract(self, hu_slice: np.ndarray) -> np.ndarray:
        """Return the HU pixel values inside this ROI as a 1-D array."""
        return hu_slice[self.mask(hu_slice.shape)]


# ── Noise ──────────────────────────────────────────────────────────────────
def measure_noise(hu_slice: np.ndarray, roi: ROI) -> float:
    """
    Image noise = standard deviation of HU values in a uniform phantom ROI.

    Parameters
    ----------
    hu_slice : 2-D HU array
    roi      : circular ROI placed over a uniform region (e.g. water insert)

    Returns
    -------
    float  Standard deviation in HU. Lower is better.

    Typical ACR tolerance
    ---------------------
    Baseline ± 10 HU  (tighter for high-dose protocols)
    """
    pixels = roi.extract(hu_slice)
    if pixels.size == 0:
        raise ValueError("ROI contains no pixels — check ROI position and radius.")
    return float(np.std(pixels, ddof=1))


# ── Uniformity ─────────────────────────────────────────────────────────────
def measure_uniformity(
    hu_slice: np.ndarray,
    centre_roi: ROI,
    peripheral_rois: Dict[str, ROI],
) -> Dict[str, float]:
    """
    Uniformity = deviation of peripheral ROI means from centre ROI mean.

    Peripheral ROIs are typically placed at top, bottom, left, right of the
    phantom at ~half-radius offset from the edge.

    Parameters
    ----------
    hu_slice        : 2-D HU array
    centre_roi      : ROI at phantom centre
    peripheral_rois : dict of {label: ROI}  e.g. {"top": ROI(...), ...}

    Returns
    -------
    dict with keys:
        "centre_mean"           : float  HU mean of centre ROI
        "peripheral_means"      : dict   {label: mean_HU}
        "max_deviation_HU"      : float  largest abs(peripheral - centre)
        "uniformity_index"      : float  (1 - max_dev / centre_mean) * 100  [%]

    ACR tolerance
    -------------
    All peripheral ROIs within ±5 HU of centre for water phantom.
    """
    centre_pixels = centre_roi.extract(hu_slice)
    centre_mean = float(np.mean(centre_pixels))

    peripheral_means = {}
    for label_name, roi in peripheral_rois.items():
        pix = roi.extract(hu_slice)
        peripheral_means[label_name] = float(np.mean(pix))

    deviations = [abs(v - centre_mean) for v in peripheral_means.values()]
    max_dev = max(deviations) if deviations else 0.0

    # Avoid division by zero for very low HU centres
    if abs(centre_mean) > 1e-6:
        ui = (1.0 - max_dev / abs(centre_mean)) * 100.0
    else:
        ui = float("nan")

    return {
        "centre_mean": centre_mean,
        "peripheral_means": peripheral_means,
        "max_deviation_HU": max_dev,
        "uniformity_index": ui,
    }


# ── CNR ────────────────────────────────────────────────────────────────────
def measure_cnr(
    hu_slice: np.ndarray,
    signal_roi: ROI,
    background_roi: ROI,
    noise_roi: Optional[ROI] = None,
) -> float:
    """
    Contrast-to-Noise Ratio.

    CNR = (mean_signal - mean_background) / noise_SD

    If noise_roi is None, noise is estimated from the background_roi SD.

    Parameters
    ----------
    hu_slice       : 2-D HU array
    signal_roi     : ROI over the high-contrast insert
    background_roi : ROI over the uniform background material
    noise_roi      : optional dedicated noise ROI (background corner)

    Returns
    -------
    float  CNR (dimensionless). Higher = better lesion detectability.
    """
    sig_pixels = signal_roi.extract(hu_slice)
    bg_pixels = background_roi.extract(hu_slice)

    mean_sig = float(np.mean(sig_pixels))
    mean_bg = float(np.mean(bg_pixels))

    if noise_roi is not None:
        noise_pixels = noise_roi.extract(hu_slice)
        noise_sd = float(np.std(noise_pixels, ddof=1))
    else:
        noise_sd = float(np.std(bg_pixels, ddof=1))

    if noise_sd < 1e-9:
        raise ValueError("Noise SD is effectively zero — check ROI placement.")

    return (mean_sig - mean_bg) / noise_sd


# ── HU Accuracy ────────────────────────────────────────────────────────────
def measure_hu_accuracy(
    hu_slice: np.ndarray,
    material_rois: Dict[str, Tuple[ROI, float]],
) -> Dict[str, Dict[str, float]]:
    """
    HU accuracy for known phantom materials.

    Parameters
    ----------
    hu_slice      : 2-D HU array
    material_rois : dict of {material_name: (ROI, expected_HU)}
                    Standard ACR phantom materials:
                    "air"         -> -1000 HU
                    "polyethylene"->  -100 HU
                    "water"       ->     0 HU
                    "acrylic"     ->   120 HU
                    "bone"        ->   955 HU  (bone-equivalent rod)

    Returns
    -------
    dict of {material: {"measured_HU": float, "expected_HU": float,
                        "error_HU": float, "pass": bool}}

    ACR tolerance
    -------------
    |measured - expected| <= 40 HU for each material.
    """
    ACR_TOLERANCE_HU = 40.0
    results = {}
    for name, (roi, expected) in material_rois.items():
        pixels = roi.extract(hu_slice)
        measured = float(np.mean(pixels))
        error = measured - expected
        results[name] = {
            "measured_HU": measured,
            "expected_HU": expected,
            "error_HU": error,
            "pass": abs(error) <= ACR_TOLERANCE_HU,
        }
    return results


# ── Slice Thickness (FWHM) ─────────────────────────────────────────────────
def measure_slice_thickness_fwhm(
    profile: np.ndarray,
    pixel_spacing_mm: float,
) -> float:
    """
    Estimate slice thickness from a wire ramp axial edge profile using FWHM.

    The wire ramp method (ACR Module 4) uses two angled wires. The image
    of the wire along the slice direction produces a bell-shaped profile
    whose FWHM equals the actual slice thickness.

    Parameters
    ----------
    profile          : 1-D array of HU values along the slice direction
    pixel_spacing_mm : physical size of each pixel in mm

    Returns
    -------
    float  Estimated slice thickness in mm.

    ACR tolerance
    -------------
    Nominal thickness >= 3 mm : measured within +/- 1 mm
    Nominal thickness  < 3 mm : measured within +/- 0.5 mm
    """
    profile = profile.astype(float)
    baseline = np.percentile(profile, 10)
    peak = np.max(profile)
    half_max = baseline + (peak - baseline) / 2.0

    above = profile >= half_max
    if not np.any(above):
        raise ValueError("No pixels above half-maximum — check profile extraction.")

    indices = np.where(above)[0]
    fwhm_pixels = indices[-1] - indices[0] + 1
    return float(fwhm_pixels * pixel_spacing_mm)


def _gaussian(x, amplitude, mean, sigma, offset):
    return amplitude * np.exp(-0.5 * ((x - mean) / sigma) ** 2) + offset


def measure_slice_thickness_gaussian(
    profile: np.ndarray,
    pixel_spacing_mm: float,
) -> float:
    """
    Fit a Gaussian to the wire ramp profile and compute FWHM from sigma.

    More robust than the threshold method when signal is noisy.
    FWHM = 2 * sqrt(2 * ln(2)) * sigma ~= 2.355 * sigma

    Returns
    -------
    float  Estimated slice thickness in mm.
    """
    x = np.arange(len(profile), dtype=float)
    p0 = [
        profile.max() - profile.min(),
        x[np.argmax(profile)],
        len(profile) / 6.0,
        profile.min(),
    ]
    try:
        popt, _ = curve_fit(_gaussian, x, profile.astype(float), p0=p0, maxfev=5000)
        sigma_pixels = abs(popt[2])
        fwhm_pixels = 2.355 * sigma_pixels
        return float(fwhm_pixels * pixel_spacing_mm)
    except RuntimeError:
        # Fall back to threshold method if Gaussian fit fails
        return measure_slice_thickness_fwhm(profile, pixel_spacing_mm)
