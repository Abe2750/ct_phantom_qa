"""
dicom_loader.py
---------------
Utilities for loading DICOM series and converting to Hounsfield Units (HU).
"""

import logging
from pathlib import Path
from typing import NamedTuple
import pydicom
import numpy as np

logger = logging.getLogger(__name__)


class DicomSeries(NamedTuple):
    """Container for a loaded DICOM series with metadata."""
    middle_slice: np.ndarray  # 2D array of HU values
    metadata: dict            # Series metadata (NumSlices, kVp, etc.)
    slices: list              # List of all slice arrays in HU


def load_series(dicom_dir: str) -> DicomSeries:
    """
    Load a DICOM series from a directory and convert to Hounsfield Units.
    
    Parameters
    ----------
    dicom_dir : str
        Path to directory containing DICOM files (.dcm).
    
    Returns
    -------
    DicomSeries
        Named tuple with middle_slice (2D array), metadata (dict), and slices (list).
    
    Raises
    ------
    FileNotFoundError
        If directory doesn't exist or contains no DICOM files.
    """
    dicom_path = Path(dicom_dir)
    
    if not dicom_path.exists():
        raise FileNotFoundError(f"DICOM directory not found: {dicom_dir}")
    
    # Find all DICOM files
    dicom_files = sorted(dicom_path.glob("*.dcm"))
    if not dicom_files:
        raise FileNotFoundError(f"No DICOM files (.dcm) found in {dicom_dir}")
    
    logger.info(f"Loading {len(dicom_files)} DICOM files from {dicom_dir}")
    
    # Load and sort by slice location
    datasets = []
    for dcm_file in dicom_files:
        try:
            ds = pydicom.dcmread(dcm_file)
            datasets.append(ds)
        except Exception as e:
            logger.warning(f"Failed to read {dcm_file}: {e}")
    
    if not datasets:
        raise ValueError(f"No valid DICOM files could be loaded from {dicom_dir}")
    
    # Sort by slice location (ImagePositionPatient)
    def get_slice_location(ds):
        # Try SliceLocation first (most common)
        if hasattr(ds, 'SliceLocation'):
            return float(ds.SliceLocation)
        # Fall back to ImagePositionPatient z-coordinate
        if hasattr(ds, 'ImagePositionPatient'):
            return float(ds.ImagePositionPatient[2])
        # If neither exists, keep original order
        return 0.0
    
    datasets.sort(key=get_slice_location)
    
    # Convert to HU
    hu_slices = []
    for ds in datasets:
        hu = dicom_to_hu(ds)
        hu_slices.append(hu)
    
    # Get middle slice
    middle_idx = len(hu_slices) // 2
    middle_slice = hu_slices[middle_idx]
    
    # Extract metadata
    ref_ds = datasets[middle_idx]
    metadata = {
        "NumSlices": len(hu_slices),
        "Rows": int(ref_ds.Rows),
        "Columns": int(ref_ds.Columns),
        "SliceThickness": float(getattr(ref_ds, 'SliceThickness', 1.0)),
        "kVp": float(getattr(ref_ds, 'KVP', 0.0)),
        "mA": float(getattr(ref_ds, 'ExposureTime', 0.0)),  # Fallback
        "PatientName": str(getattr(ref_ds, 'PatientName', 'Unknown')),
        "StudyDate": str(getattr(ref_ds, 'StudyDate', 'Unknown')),
    }
    
    logger.info(f"Loaded {metadata['NumSlices']} slices, {metadata['Rows']}x{metadata['Columns']}, kVp={metadata['kVp']}")
    
    return DicomSeries(
        middle_slice=middle_slice,
        metadata=metadata,
        slices=hu_slices
    )


def dicom_to_hu(ds: pydicom.Dataset) -> np.ndarray:
    """
    Convert DICOM pixel array to Hounsfield Units.
    
    Uses the standard DICOM formula:
        HU = pixel_array * RescaleSlope + RescaleIntercept
    
    Parameters
    ----------
    ds : pydicom.Dataset
        DICOM dataset.
    
    Returns
    -------
    np.ndarray
        2D array of HU values.
    """
    pixel_array = ds.pixel_array.astype(np.float32)
    
    # Get rescale slope and intercept (default to standard Hounsfield scale)
    slope = float(getattr(ds, 'RescaleSlope', 1.0))
    intercept = float(getattr(ds, 'RescaleIntercept', 0.0))
    
    hu = pixel_array * slope + intercept
    
    return hu.astype(np.float32)
