"""
tolerance.py
------------
Tolerance definitions and pass/fail evaluation for CT QC metrics.

Tolerances are based on:
  - ACR CT Accreditation Program requirements
  - AAPM Task Group 233 recommendations
  - Vendor-specific baselines (loaded from config)

Usage
-----
    checker = ToleranceChecker.from_config("config/tolerances.json")
    result  = checker.check("noise", measured=12.5)
    print(result.passed, result.message)
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class ToleranceResult:
    metric: str
    measured: float
    lower: Optional[float]
    upper: Optional[float]
    passed: bool
    severity: str           # "pass" | "warning" | "action"
    message: str


@dataclass
class ToleranceBand:
    """
    Two-level tolerance band:
      warning  : value outside warning limits but inside action limits -> flag, monitor
      action   : value outside action limits -> stop clinical use, call physicist
    """
    warning_lower: Optional[float] = None
    warning_upper: Optional[float] = None
    action_lower: Optional[float]  = None
    action_upper: Optional[float]  = None
    units: str = "HU"
    description: str = ""

    def evaluate(self, metric_name: str, measured: float) -> ToleranceResult:
        # Check action limits first (more severe)
        if self.action_lower is not None and measured < self.action_lower:
            return ToleranceResult(
                metric=metric_name, measured=measured,
                lower=self.action_lower, upper=self.action_upper,
                passed=False, severity="action",
                message=f"ACTION REQUIRED: {metric_name}={measured:.2f} {self.units} "
                        f"below action limit {self.action_lower:.2f} {self.units}."
            )
        if self.action_upper is not None and measured > self.action_upper:
            return ToleranceResult(
                metric=metric_name, measured=measured,
                lower=self.action_lower, upper=self.action_upper,
                passed=False, severity="action",
                message=f"ACTION REQUIRED: {metric_name}={measured:.2f} {self.units} "
                        f"above action limit {self.action_upper:.2f} {self.units}."
            )
        # Check warning limits
        if self.warning_lower is not None and measured < self.warning_lower:
            return ToleranceResult(
                metric=metric_name, measured=measured,
                lower=self.warning_lower, upper=self.warning_upper,
                passed=True, severity="warning",
                message=f"WARNING: {metric_name}={measured:.2f} {self.units} "
                        f"below warning limit {self.warning_lower:.2f} {self.units}."
            )
        if self.warning_upper is not None and measured > self.warning_upper:
            return ToleranceResult(
                metric=metric_name, measured=measured,
                lower=self.warning_lower, upper=self.warning_upper,
                passed=True, severity="warning",
                message=f"WARNING: {metric_name}={measured:.2f} {self.units} "
                        f"above warning limit {self.warning_upper:.2f} {self.units}."
            )
        return ToleranceResult(
            metric=metric_name, measured=measured,
            lower=self.warning_lower, upper=self.warning_upper,
            passed=True, severity="pass",
            message=f"PASS: {metric_name}={measured:.2f} {self.units} within tolerance."
        )


# Default ACR/AAPM-based tolerances
DEFAULT_TOLERANCES: Dict[str, ToleranceBand] = {
    "noise": ToleranceBand(
        warning_upper=15.0, action_upper=20.0, units="HU",
        description="Image noise (SD of HU in uniform water ROI). "
                    "ACR: baseline +/- 10 HU; action at +20 HU."
    ),
    "uniformity_deviation": ToleranceBand(
        warning_upper=5.0, action_upper=10.0, units="HU",
        description="Max peripheral vs centre HU deviation. ACR: <=5 HU."
    ),
    "hu_water": ToleranceBand(
        warning_lower=-7.0, warning_upper=7.0,
        action_lower=-15.0, action_upper=15.0, units="HU",
        description="HU accuracy for water (expected=0 HU). ACR: within +/-7 HU."
    ),
    "hu_air": ToleranceBand(
        warning_lower=-1010.0, warning_upper=-990.0,
        action_lower=-1020.0, action_upper=-980.0, units="HU",
        description="HU accuracy for air (expected=-1000 HU)."
    ),
    "slice_thickness": ToleranceBand(
        warning_lower=-1.0, warning_upper=1.0,
        action_lower=-2.0, action_upper=2.0, units="mm",
        description="Slice thickness deviation from nominal. ACR: +/- 1 mm for >=3mm slices."
    ),
    "cnr": ToleranceBand(
        warning_lower=1.0, action_lower=0.5, units="dimensionless",
        description="Contrast-to-noise ratio. Baseline-dependent."
    ),
}


class ToleranceChecker:
    def __init__(self, tolerances: Dict[str, ToleranceBand] = None):
        self.tolerances = tolerances or DEFAULT_TOLERANCES

    @classmethod
    def from_config(cls, config_path: str) -> "ToleranceChecker":
        """Load custom tolerances from a JSON config file."""
        path = Path(config_path)
        if not path.exists():
            logger.warning("Tolerance config %s not found. Using ACR defaults.", config_path)
            return cls()
        with open(path) as f:
            raw = json.load(f)
        tolerances = {}
        for key, val in raw.items():
            tolerances[key] = ToleranceBand(**val)
        logger.info("Loaded %d tolerance bands from %s", len(tolerances), config_path)
        return cls(tolerances)

    def check(self, metric_name: str, measured: float) -> ToleranceResult:
        if metric_name not in self.tolerances:
            logger.warning("No tolerance defined for metric: %s", metric_name)
            return ToleranceResult(
                metric=metric_name, measured=measured,
                lower=None, upper=None, passed=True,
                severity="pass", message=f"No tolerance defined for {metric_name}."
            )
        return self.tolerances[metric_name].evaluate(metric_name, measured)

    def check_all(self, measurements: Dict[str, float]) -> Dict[str, ToleranceResult]:
        return {k: self.check(k, v) for k, v in measurements.items()}
