import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from PIL import Image, ImageOps, ImageEnhance
from pyzbar.pyzbar import decode
from streamlit_cropper import st_cropper

# --- 1. Page Config & Mobile Responsive CSS ---
st.set_page_config(page_title="Serial Scanner", layout="wide")

st.markdown("""
    <style>
    /* Force full width on mobile */
    [data-testid="stCameraInput"] { width: 100% !important; }
    [data-testid="stCameraInput"] video { 
        width: 100% !important; 
        height: auto !important; 
        border-radius: 10px; 
    }
    .stButton>button { width: 100%; height: 3em; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. Data Loading ---
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

@st.cache_data(ttl=600)
def load_data():
    try:
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        client = gspread.authorize(creds)
        ss = client.open("School_Master_Serial_Number_Capture")
        df = pd.DataFrame(ss.worksheet("school_master").get_all_records())
        df.columns = [str(c).strip() for c in df.columns]
        df['UDISE'] = df['UDISE'].astype(str)
        return df, ss.worksheet("smartboard_serials")
    except Exception as e:
        st.error(f"Setup Error: {e}")
        return None, None

df_master, sheet_serials = load_data()

# --- 3. App UI ---
st.title("📟 Smartboard Serial Capture")

if df_master is not None:
    # --- School Selection ---
    st.markdown("### 1. Select School")
    
    f_df = df_master.copy()
    f_df['search_display'] = f_df['UDISE'] + " - " + f_df['School']
    selected_option = st.selectbox("Search School/UDISE", [""] + sorted(f_df['search_display'].unique()))

    if selected_option:
        udise = selected_option.split(" - ")[0]
        school = df_master[df_master['UDISE'] == udise].iloc[0]['School']
        devices = df_master[df_master['UDISE'] == udise]['Device Name'].tolist()
        device = st.selectbox("Select Device", devices)

        st.divider()

        # --- Step 2: Capture & Crop ---
        st.markdown("### 2. Capture & Crop Barcode")
        img_file = st.camera_input("Capture the barcode label")
        
        scanned_val = ""
        if img_file:
            raw_img = Image.open(img_file)
            
            st.info("✂️ Drag the box to cover ONLY the barcode lines.")
            
            # The Cropper tool allows you to isolate the barcode
            # aspect_ratio=None allows for long, thin barcodes
            cropped_img = st_cropper(raw_img, realtime_update=True, box_color='#00FF00', aspect_ratio=None)
            
            # Image Enhancement for the cropped area
            proc = ImageOps.grayscale(cropped_img)
            proc = ImageEnhance.Contrast(proc).enhance(3.0)
            
            st.write("Preview for Scanning:")
            st.image(proc, use_container_width=True)

            if st.button("🚀 Scan Cropped Barcode"):
                with st.spinner("Decoding..."):
                    barcodes = decode(proc)
                    if barcodes:
                        scanned_val = barcodes[0].data.decode('utf-8')
                        st.success(f"✅ Found: **{scanned_val}**")
                    else:
                        st.error("❌ Barcode not found in cropped area. Try adjusting the crop box.")

        # --- Step 3: Verification & Submit ---
        st.divider()
        final_serial = st.text_input("Verified Serial", value=scanned_val)
        email = st.text_input("Your Email Address")

        if st.button("✅ Submit Data"):
            if not final_serial or not email:
                st.warning("Please scan and provide email.")
            else:
                sheet_serials.append_row([udise, school, device, final_serial, email])
                st.success("Successfully Saved!")
                st.balloons()
