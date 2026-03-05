import streamlit as st
import numpy as np
import pydicom
import matplotlib.pyplot as plt
import pandas as pd
import os
import google.generativeai as genai
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- CONFIG & PHYSICS SETTINGS ---
HISTORY_FILE = "qc_history.csv"
TOLERANCE_NOISE = 15.0  # HU
TOLERANCE_UNI = 5.0    # HU

# --- CORE PHYSICS FUNCTIONS ---
def get_roi_stats(data, cx, cy, r=20):
    """Calculates Mean and SD for a circular ROI using NumPy indexing."""
    rows, cols = data.shape
    yy, xx = np.ogrid[:rows, :cols]
    mask = (xx - cx)**2 + (yy - cy)**2 <= r**2
    pixels = data[mask]
    return np.mean(pixels), np.std(pixels)

def analyze_ct_slice(hu_data):
    """Computes key metrics: Noise, Uniformity, and CNR."""
    rows, cols = hu_data.shape
    cx, cy = cols // 2, rows // 2
    
    # 1. Center ROI (Water/Noise)
    mean_c, sd_c = get_roi_stats(hu_data, cx, cy)
    
    # 2. Peripheral ROI (Uniformity check)
    mean_p, _ = get_roi_stats(hu_data, cx, cy - 120) 
    
    # 3. Bone ROI (for CNR) - assuming insert is at (cx-100, cy)
    mean_b, _ = get_roi_stats(hu_data, cx - 100, cy)
    
    metrics = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "noise": float(sd_c),
        "uniformity": float(abs(mean_c - mean_p)),
        "cnr": float(abs(mean_b - mean_c) / (sd_c or 1.0))
    }
    return metrics

# --- AI & TRENDING ---
def get_ai_advice(metrics):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key: return "Set GEMINI_API_KEY to enable AI interpretation."
    
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')
        prompt = f"As a Medical Physicist, interpret these CT results: Noise={metrics['noise']:.2f}HU, Uniformity={metrics['uniformity']:.2f}HU. Briefly explain the physics of any failures."
        return model.generate_content(prompt).text
    except Exception as e: return f"AI Error: {e}"

def save_to_history(metrics):
    df = pd.DataFrame([metrics])
    if not os.path.isfile(HISTORY_FILE):
        df.to_csv(HISTORY_FILE, index=False)
    else:
        df.to_csv(HISTORY_FILE, mode='a', header=False, index=False)

# --- DEMO GENERATOR ---
def generate_demo_phantom(path="demo_phantom.dcm"):
    """Generates a synthetic CT DICOM for testing."""
    file_meta = pydicom.dataset.Dataset()
    file_meta.MediaStorageSOPClassUID = '1.2.840.10008.5.1.4.1.1.2'
    file_meta.MediaStorageSOPInstanceUID = "1.2.3"
    file_meta.ImplementationClassUID = "1.2.3.4"
    file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian

    ds = pydicom.dataset.FileDataset(path, {}, file_meta=file_meta, preamble=b"\0" * 128)
    ds.PatientName = "PHANTOM^TEST"
    ds.Rows = ds.Columns = 512
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 1
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.RescaleSlope, ds.RescaleIntercept = 1.0, -1024.0
    
    image = np.full((512, 512), 24, dtype=np.int16) # Air
    yy, xx = np.ogrid[:512, :512]
    image[(xx-256)**2 + (yy-256)**2 <= 180**2] = 1024 # Water
    image[(xx-156)**2 + (yy-256)**2 <= 20**2] = 2024 # Bone insert
    image += np.random.normal(0, 10, (512, 512)).astype(np.int16) # Noise
    
    ds.PixelData = image.tobytes()
    ds.save_as(path)

# --- STREAMLIT UI ---
st.set_page_config(page_title="Simple CT QA", layout="wide")
st.title("🏥 Simplified CT Phantom QA")

with st.sidebar:
    st.header("1. Data Input")
    uploaded_file = st.file_uploader("Upload DICOM Slice", type=["dcm"])
    if st.button("Generate Demo Phantom"):
        generate_demo_phantom()
        st.success("demo_phantom.dcm created!")

if uploaded_file or os.path.exists("demo_phantom.dcm"):
    file_to_load = uploaded_file if uploaded_file else "demo_phantom.dcm"
    
    # 1. Load Data
    ds = pydicom.dcmread(file_to_load)
    hu_data = ds.pixel_array * float(getattr(ds, 'RescaleSlope', 1)) + float(getattr(ds, 'RescaleIntercept', 0))
    
    # 2. Analyze
    metrics = analyze_ct_slice(hu_data)
    
    # 3. Display Results
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Image Analysis (ROI Overlay)")
        fig, ax = plt.subplots()
        ax.imshow(hu_data, cmap='gray', vmin=-150, vmax=150)
        rows, cols = hu_data.shape
        ax.add_patch(plt.Circle((cols//2, rows//2), 20, color='red', fill=False, label="Center"))
        ax.add_patch(plt.Circle((cols//2, rows//2 - 120), 20, color='yellow', fill=False, label="Peri"))
        ax.add_patch(plt.Circle((cols//2 - 100, rows//2), 20, color='cyan', fill=False, label="Bone"))
        st.pyplot(fig)

    with col2:
        st.subheader("Metrics")
        st.metric("Noise (SD)", f"{metrics['noise']:.2f} HU", delta=f"{metrics['noise']-TOLERANCE_NOISE:.1f}", delta_color="inverse")
        st.metric("Uniformity", f"{metrics['uniformity']:.2f} HU", delta=f"{metrics['uniformity']-TOLERANCE_UNI:.1f}", delta_color="inverse")
        st.metric("CNR", f"{metrics['cnr']:.2f}")
        
        if st.button("Save Result to History"):
            save_to_history(metrics)
            st.success("Saved!")

    # 4. Trending & AI
    st.divider()
    t1, t2 = st.tabs(["📈 Trending", "🤖 AI Advisor"])
    
    with t1:
        if os.path.exists(HISTORY_FILE):
            history_df = pd.read_csv(HISTORY_FILE)
            st.line_chart(history_df.set_index("date")[["noise", "uniformity"]])
        else: st.info("No history yet.")
        
    with t2:
        if st.button("Generate Physics Report"):
            with st.spinner("Analyzing..."):
                st.write(get_ai_advice(metrics))
else:
    st.info("Please upload a CT DICOM file or click 'Generate Demo Phantom' in the sidebar.")
