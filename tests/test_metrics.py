"""
test_metrics.py
---------------
Unit tests for all CT QC metric computations.

Tests use synthetic HU arrays so no real DICOM data is required.
Run with:  pytest tests/ -v
"""

import numpy as np
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from metrics import (
    ROI, measure_noise, measure_uniformity,
    measure_cnr, measure_hu_accuracy,
    measure_slice_thickness_fwhm, measure_slice_thickness_gaussian,
)


# ── Fixtures ───────────────────────────────────────────────────────────────
@pytest.fixture
def uniform_water_slice():
    """512x512 slice of pure water (0 HU) with slight Gaussian noise."""
    np.random.seed(42)
    return np.random.normal(loc=0.0, scale=10.0, size=(512, 512))


@pytest.fixture
def centre_roi():
    return ROI(cx=256, cy=256, radius=30)


@pytest.fixture
def peripheral_rois():
    return {
        "top":    ROI(256, 156, 20),
        "bottom": ROI(256, 356, 20),
        "left":   ROI(156, 256, 20),
        "right":  ROI(356, 256, 20),
    }


# ── ROI tests ──────────────────────────────────────────────────────────────
class TestROI:
    def test_mask_shape(self, uniform_water_slice):
        roi = ROI(256, 256, 30)
        mask = roi.mask(uniform_water_slice.shape)
        assert mask.shape == uniform_water_slice.shape

    def test_mask_is_boolean(self, uniform_water_slice):
        roi = ROI(256, 256, 30)
        mask = roi.mask(uniform_water_slice.shape)
        assert mask.dtype == bool

    def test_extract_returns_1d(self, uniform_water_slice):
        roi = ROI(256, 256, 30)
        pixels = roi.extract(uniform_water_slice)
        assert pixels.ndim == 1
        assert pixels.size > 0

    def test_extract_pixel_count_approx(self, uniform_water_slice):
        roi = ROI(256, 256, 30)
        pixels = roi.extract(uniform_water_slice)
        expected = int(np.pi * 30 ** 2)
        assert abs(pixels.size - expected) < 50   # within 50 pixels of pi*r^2


# ── Noise tests ────────────────────────────────────────────────────────────
class TestNoise:
    def test_noise_close_to_true_sd(self, uniform_water_slice, centre_roi):
        noise = measure_noise(uniform_water_slice, centre_roi)
        assert abs(noise - 10.0) < 2.0, f"Expected noise ~10 HU, got {noise:.2f}"

    def test_noise_zero_for_flat_image(self, centre_roi):
        flat = np.zeros((512, 512))
        assert measure_noise(flat, centre_roi) == pytest.approx(0.0, abs=1e-6)

    def test_noise_positive(self, uniform_water_slice, centre_roi):
        assert measure_noise(uniform_water_slice, centre_roi) >= 0

    def test_noise_raises_empty_roi(self):
        small = np.zeros((10, 10))
        huge_roi = ROI(5, 5, 100)      # radius bigger than image
        # Should still work -- mask clips to image bounds
        # (depending on implementation; here we just check it runs)
        result = measure_noise(small, huge_roi)
        assert isinstance(result, float)


# ── Uniformity tests ───────────────────────────────────────────────────────
class TestUniformity:
    def test_perfect_uniformity(self, centre_roi, peripheral_rois):
        flat = np.zeros((512, 512))
        result = measure_uniformity(flat, centre_roi, peripheral_rois)
        assert result["max_deviation_HU"] == pytest.approx(0.0, abs=1e-6)
        assert result["centre_mean"] == pytest.approx(0.0, abs=1e-6)

    def test_uniformity_detects_cupping(self, centre_roi, peripheral_rois):
        # Simulate cupping: centre is 0 HU, periphery is +20 HU
        cupped = np.zeros((512, 512))
        cupped[:100, :] = 20.0
        cupped[400:, :] = 20.0
        cupped[:, :100] = 20.0
        cupped[:, 400:] = 20.0
        result = measure_uniformity(cupped, centre_roi, peripheral_rois)
        assert result["max_deviation_HU"] > 0

    def test_uniformity_result_keys(self, uniform_water_slice, centre_roi, peripheral_rois):
        result = measure_uniformity(uniform_water_slice, centre_roi, peripheral_rois)
        for key in ("centre_mean", "peripheral_means", "max_deviation_HU", "uniformity_index"):
            assert key in result


# ── CNR tests ──────────────────────────────────────────────────────────────
class TestCNR:
    def test_cnr_positive_contrast(self):
        img = np.zeros((512, 512))
        img[200:300, 200:300] = 100.0   # 100 HU insert
        signal_roi = ROI(250, 250, 20)
        bg_roi     = ROI(256, 256, 5)   # low-signal background
        bg_roi2    = ROI(100, 100, 20)
        # patch background area to have small noise
        np.random.seed(0)
        img[80:120, 80:120] = np.random.normal(0, 5, (40, 40))
        cnr = measure_cnr(img, signal_roi, bg_roi2)
        assert cnr > 0

    def test_cnr_raises_on_zero_noise(self):
        flat = np.zeros((512, 512))
        flat[250:260, 250:260] = 50.0
        with pytest.raises(ValueError, match="Noise SD"):
            measure_cnr(flat, ROI(255, 255, 4), ROI(100, 100, 20))


# ── HU Accuracy tests ──────────────────────────────────────────────────────
class TestHuAccuracy:
    def test_perfect_hu_accuracy(self):
        img = np.zeros((512, 512))
        # Water at centre (0 HU) -- already zero
        rois = {"water": (ROI(256, 256, 20), 0.0)}
        result = measure_hu_accuracy(img, rois)
        assert result["water"]["error_HU"] == pytest.approx(0.0, abs=0.1)
        assert result["water"]["pass"] is True

    def test_failing_hu_accuracy(self):
        img = np.full((512, 512), 100.0)   # everything is 100 HU
        rois = {"water": (ROI(256, 256, 20), 0.0)}
        result = measure_hu_accuracy(img, rois)
        assert result["water"]["pass"] is False   # 100 HU error > 40 HU tolerance

    def test_all_materials_present_in_results(self):
        img = np.zeros((512, 512))
        rois = {
            "water":  (ROI(256, 256, 10), 0.0),
            "air":    (ROI(256, 100, 10), -1000.0),
        }
        result = measure_hu_accuracy(img, rois)
        assert "water" in result
        assert "air"   in result


# ── Slice thickness tests ──────────────────────────────────────────────────
class TestSliceThickness:
    def _make_gaussian_profile(self, sigma_px=5, n=100):
        x = np.arange(n, dtype=float)
        return np.exp(-0.5 * ((x - n/2) / sigma_px) ** 2) * 1000

    def test_fwhm_known_gaussian(self):
        sigma_px = 5
        profile = self._make_gaussian_profile(sigma_px)
        expected_fwhm_mm = 2.355 * sigma_px * 1.0    # pixel_spacing = 1.0 mm
        result = measure_slice_thickness_fwhm(profile, pixel_spacing_mm=1.0)
        assert abs(result - expected_fwhm_mm) < 2.0, f"FWHM: expected ~{expected_fwhm_mm:.1f}, got {result:.1f}"

    def test_gaussian_fit_close_to_fwhm(self):
        profile = self._make_gaussian_profile(sigma_px=5)
        fwhm   = measure_slice_thickness_fwhm(profile, pixel_spacing_mm=1.0)
        gauss  = measure_slice_thickness_gaussian(profile, pixel_spacing_mm=1.0)
        assert abs(fwhm - gauss) < 3.0, "Gaussian and FWHM methods should agree within 3 mm"
