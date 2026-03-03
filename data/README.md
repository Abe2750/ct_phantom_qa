# Data Directory

Place your DICOM phantom scan files here.

## Structure

```
data/
  sample_dicoms/
    session_YYYYMMDD/       <- one directory per QC session
      IM-0001.dcm
      IM-0002.dcm
      ...
```

## Important

- **Never commit real patient DICOM data to Git.**
- Phantom QA scans that contain no patient identifiers may be committed for
  testing purposes, but confirm with your institution's data governance policy first.
- `.gitignore` is pre-configured to exclude all `.dcm` files.

## Getting Test Data

- The TCIA (The Cancer Imaging Archive) provides de-identified CT datasets for research.
- The ACR provides phantom scan datasets to accredited sites.
- You can also generate synthetic DICOM files using `pydicom` for unit testing.
