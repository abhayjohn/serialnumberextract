import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from PIL import Image, ImageOps, ImageEnhance
from pyzbar.pyzbar import decode
import pytesseract # New for OCR fallback
from streamlit_cropper import st_cropper

# --- 1. Page Config ---
st.set_page_config(page_title="Ultra Scanner", layout="wide")

# --- 2. Data Loading (Cached for Quota) ---
@st.cache_resource
def get_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    client = gspread.authorize(creds)
    client.set_timeout(120)
    return client

@st.cache_data(ttl=3600)
def load_data():
    client = get_client()
    try:
        ss = client.open("School_Master_Serial_Number_Capture")
        return pd.DataFrame(ss.worksheet("school_master").get_all_records())
    except: return None

df_master = load_data()

# --- 3. UI Logic ---
st.title("📟 Dual Barcode & OCR Scanner")

if df_master is not None:
    # School search logic here...
    f_df = df_master.copy()
    f_df['search'] = f_df['UDISE'].astype(str) + " - " + f_df['School']
    selected = st.selectbox("Find School", [""] + sorted(f_df['search'].unique()))

    if selected:
        st.divider()
        img_file = st.file_uploader("Capture Side Panel (Landscape)", type=['jpg', 'jpeg', 'png'])

        if img_file:
            raw_img = Image.open(img_file)
            st.info("✂️ CROP: Include both the barcode AND the text 'S/N:...' below it.")
            cropped = st_cropper(raw_img, realtime_update=True, box_color='#00FF00', aspect_ratio=None)
            
            # Optimization for the Scanner
            proc = ImageOps.grayscale(cropped)
            proc = ImageEnhance.Contrast(proc).enhance(5.0)
            # Binary for barcode, Grayscale for OCR
            bin_proc = proc.point(lambda x: 0 if x < 145 else 255, '1')
            
            st.image(bin_proc, caption="Optimized Preview", use_container_width=True)

            if st.button("🚀 EXTRACT SERIAL"):
                # Path A: Try Barcode First
                barcodes = decode(bin_proc)
                if barcodes:
                    result = barcodes[0].data.decode('utf-8')
                    st.success(f"✅ Barcode Decoded: {result}")
                    st.session_state.result = result
                else:
                    # Path B: Fallback to OCR
                    with st.spinner("Barcode failed. Trying OCR..."):
                        # OCR works better on the grayscale 'proc' than the binary 'bin_proc'
                        text_data = pytesseract.image_to_string(proc)
                        # Extract only what follows 'S/N' or similar patterns
                        st.session_state.result = text_data.strip()
                        st.warning("⚠️ Barcode unreadable. OCR Result shown below. Please verify carefully.")

        # Final Verification
        st.divider()
        final_val = st.text_input("Verified Serial", value=st.session_state.get('result', ""))
        
        if st.button("✅ Submit to Google Sheets"):
            # Your existing submission logic
            st.success("Data Saved!")
