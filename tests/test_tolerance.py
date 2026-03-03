"""
test_tolerance.py
Unit tests for the ToleranceChecker and ToleranceBand classes.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tolerance import ToleranceBand, ToleranceChecker, DEFAULT_TOLERANCES


class TestToleranceBand:
    def test_pass_within_limits(self):
        band = ToleranceBand(warning_upper=15.0, action_upper=20.0)
        result = band.evaluate("noise", 10.0)
        assert result.passed is True
        assert result.severity == "pass"

    def test_warning_triggered(self):
        band = ToleranceBand(warning_upper=15.0, action_upper=20.0)
        result = band.evaluate("noise", 16.0)
        assert result.severity == "warning"
        assert result.passed is True   # warning = pass but flagged

    def test_action_triggered(self):
        band = ToleranceBand(warning_upper=15.0, action_upper=20.0)
        result = band.evaluate("noise", 22.0)
        assert result.severity == "action"
        assert result.passed is False

    def test_lower_action_limit(self):
        band = ToleranceBand(action_lower=0.5)
        result = band.evaluate("cnr", 0.3)
        assert result.severity == "action"
        assert result.passed is False

    def test_no_limits_always_passes(self):
        band = ToleranceBand()
        result = band.evaluate("custom", 999.0)
        assert result.passed is True


class TestToleranceChecker:
    def test_default_noise_pass(self):
        checker = ToleranceChecker()
        result = checker.check("noise", 12.0)
        assert result.severity == "pass"

    def test_default_noise_warning(self):
        checker = ToleranceChecker()
        result = checker.check("noise", 16.0)
        assert result.severity == "warning"

    def test_default_noise_action(self):
        checker = ToleranceChecker()
        result = checker.check("noise", 22.0)
        assert result.severity == "action"

    def test_unknown_metric_passes_with_warning(self):
        checker = ToleranceChecker()
        result = checker.check("nonexistent_metric", 99.0)
        assert result.passed is True

    def test_check_all_returns_all_keys(self):
        checker = ToleranceChecker()
        measurements = {"noise": 12.0, "uniformity_deviation": 4.0, "cnr": 2.0}
        results = checker.check_all(measurements)
        assert set(results.keys()) == set(measurements.keys())
