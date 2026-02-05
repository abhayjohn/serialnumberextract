import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from PIL import Image, ImageOps, ImageEnhance
from pyzbar.pyzbar import decode

# --- 1. Page Config & Mobile Responsive CSS ---
st.set_page_config(page_title="Serial Scanner", layout="wide")

st.markdown("""
    <style>
    /* Force the camera to use 100% of the mobile screen width */
    [data-testid="stCameraInput"] {
        width: 100% !important;
    }
    /* Force the video stream to be larger and clearer on phones */
    [data-testid="stCameraInput"] video {
        width: 100% !important;
        height: auto !important;
        border: 3px solid #00FF00;
        border-radius: 15px;
    }
    /* Make the 'Take Photo' button larger for thumbs */
    button[data-testid="stBaseButton-secondary"] {
        height: 3em !important;
        width: 100% !important;
        font-weight: bold !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. Data Loading (Google Sheets) ---
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
    # --- Step 1: Selection ---
    st.markdown("### 1. Select School & Device")
    
    col1, col2 = st.columns(2)
    with col1:
        dists = sorted(df_master['District'].unique())
        sel_dist = st.selectbox("District", ["All"] + dists)
    with col2:
        blocks = ["All"]
        if sel_dist != "All":
            blocks = sorted(df_master[df_master['District'] == sel_dist]['Block'].unique())
        sel_block = st.selectbox("Block", blocks)

    f_df = df_master.copy()
    if sel_dist != "All": f_df = f_df[f_df['District'] == sel_dist]
    if sel_block != "All": f_df = f_df[f_df['Block'] == sel_block]

    f_df['search_display'] = f_df['UDISE'] + " - " + f_df['School']
    selected_option = st.selectbox("Search School/UDISE", [""] + sorted(f_df['search_display'].unique()))

    if selected_option:
        udise = selected_option.split(" - ")[0]
        school = df_master[df_master['UDISE'] == udise].iloc[0]['School']
        devices = df_master[df_master['UDISE'] == udise]['Device Name'].tolist()
        device = st.selectbox("Select Device", devices)

        st.divider()

        # --- Step 2: Full-Width Barcode Scanner ---
        st.markdown("### 2. Scan Barcode")
        st.info("💡 Tip: Align the barcode HORIZONTALLY. Hold steady for 1 second.")
        
        # The CSS above ensures this takes the full mobile width
        img_file = st.camera_input("Place barcode in center of frame")
        
        scanned_val = ""
        if img_file:
            with st.spinner("Processing..."):
                raw_img = Image.open(img_file)
                
                # ENHANCEMENT PIPELINE for thin barcodes
                # 1. Grayscale
                proc = ImageOps.grayscale(raw_img)
                # 2. Sharpen & Contrast (Makes the thin lines stand out)
                proc = ImageEnhance.Contrast(proc).enhance(3.0)
                proc = ImageEnhance.Sharpness(proc).enhance(2.0)
                
                # Decode using the ZBar engine
                barcodes = decode(proc)
                
                if barcodes:
                    scanned_val = barcodes[0].data.decode('utf-8')
                    st.success(f"✅ Found: **{scanned_val}**")
                else:
                    st.error("❌ Barcode not clear. Try holding the phone further back (6-10 inches).")
                    with st.expander("See Scan Preview"):
                        st.image(proc, caption="Processed Image", use_container_width=True)

        # --- Step 3: Verification & Submit ---
        st.divider()
        final_serial = st.text_input("Verified Serial", value=scanned_val)
        email = st.text_input("Installer Email")

        if st.button("✅ Submit Data", use_container_width=True):
            if not final_serial or not email:
                st.warning("Please scan barcode and provide email.")
            else:
                sheet_serials.append_row([udise, school, device, final_serial, email])
                st.success("Successfully Saved!")
                st.balloons()
