# 🏥 CT Phantom QA Analysis Dashboard

A simplified, automated tool for Computed Tomography (CT) Image Quality Control. This project replaces manual Excel-based workflows with a Python-powered dashboard, integrating **Physics-based metrics** and **AI-driven analysis**.

## 🧬 Physics for the Junior Medical Physicist

### 1. The Hounsfield Scale (HU)
The CT image is a map of the linear attenuation coefficient ($\mu$) of the scanned object. We normalize this to the attenuation of water:
$$HU = 1000 \times \frac{\mu - \mu_{water}}{\mu_{water} - \mu_{air}}$$
By definition, Water = 0 HU and Air = -1000 HU.

### 2. Image Noise (Precision)
Noise in CT is primarily due to **photon statistics** (Poisson distribution). As the number of photons hitting the detector increases, the signal-to-noise ratio improves. We measure noise as the **Standard Deviation (SD)** of HU values in a uniform ROI of a water phantom.

### 3. Uniformity (Accuracy)
Uniformity measures the consistency of HU values across the entire field of view. Deviations (like "cupping" or "capping" artifacts) usually indicate issues with **beam hardening** compensation or detector calibration.

### 4. Contrast-to-Noise Ratio (CNR)
CNR quantifies the ability to distinguish an object (like a bone insert) from its background. 
$$CNR = \frac{|Mean_{Object} - Mean_{Background}|}{SD_{Background}}$$

---

## 🚀 Getting Started

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the Dashboard
```bash
streamlit run ct_qa_simplified.py
```

### 3. Usage
- **Demo Mode**: Click "Generate Demo Phantom" in the sidebar to create a test DICOM file.
- **Real Data**: Upload any CT axial slice (.dcm) of a water phantom.
- **AI Advisor**: Set your `GEMINI_API_KEY` to enable the Physics Advisor, which interprets your results using an LLM.

## 🛠️ Project Structure
- `ct_qa_simplified.py`: The entire app (Physics Engine, UI, and AI Advisor).
- `README.md`: This guide.
- `requirements.txt`: Core dependencies.
- `data/`: Folder for your DICOM files.
