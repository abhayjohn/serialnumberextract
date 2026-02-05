import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from PIL import Image, ImageOps, ImageEnhance
from pyzbar.pyzbar import decode
from streamlit_cropper import st_cropper

# --- 1. Page Config & CSS Fixes ---
st.set_page_config(page_title="Ultra-Accurate Scanner", layout="wide")

# This CSS forces the cropper and images to be full-screen width on mobile
st.markdown("""
    <style>
    .stApp { max-width: 100%; padding: 0px; }
    /* Force Cropper to be responsive and visible */
    .stCropper { width: 100% !important; max-width: 100% !important; }
    /* Ensure the container width is used */
    div[data-testid="stImage"] img {
        width: 100% !important;
        height: auto !important;
    }
    /* Large buttons for mobile */
    .stButton>button { 
        width: 100%; 
        height: 3.8em; 
        font-weight: bold; 
        font-size: 18px !important;
        border-radius: 12px;
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
    # --- Step 1: School Selection ---
    st.markdown("### 1. Identify School")
    
    col1, col2 = st.columns(2)
    with col1:
        dists = sorted(df_master['District'].unique())
        sel_dist = st.selectbox("District", ["All"] + dists)
    with col2:
        blocks = sorted(df_master[df_master['District'] == sel_dist]['Block'].unique()) if sel_dist != "All" else ["All"]
        sel_block = st.selectbox("Block", blocks)

    f_df = df_master.copy()
    if sel_dist != "All": f_df = f_df[f_df['District'] == sel_dist]
    if sel_block != "All": f_df = f_df[f_df['Block'] == sel_block]

    f_df['search_display'] = f_df['UDISE'] + " - " + f_df['School']
    selected_option = st.selectbox("Search School/UDISE", [""] + sorted(f_df['search_display'].unique()))

    if selected_option:
        udise = selected_option.split(" - ")[0]
        school = df_master[df_master['UDISE'] == udise].iloc[0]['School']
        device = st.selectbox("Select Device", df_master[df_master['UDISE'] == udise]['Device Name'].tolist())

        st.divider()

        # --- Step 2: Full-Screen Capture ---
        st.markdown("### 2. Capture Barcode")
        st.info("📸 Tap 'Browse' -> 'Camera' to use your phone's native FULL-SCREEN camera.")
        
        # Native camera trigger via file_uploader
        img_file = st.file_uploader("Capture Photo", type=['jpg', 'jpeg', 'png'])

        if img_file:
            raw_img = Image.open(img_file)
            
            # --- Step 3: FULL-WIDTH CROP ---
            st.markdown("### ✂️ Manual Crop")
            st.caption("Drag the box to isolate the barcode. The view below is resized to fit your screen.")
            
            # Use cropper with high-res handling
            # aspect_ratio=None allows for long horizontal barcodes
            cropped_img = st_cropper(
                raw_img, 
                realtime_update=True, 
                box_color='#00FF00', 
                aspect_ratio=None,
                should_resize_landscape=True # Helps mobile browsers handle wide images
            )
            
            # High-Accuracy Enhancement
            proc = ImageOps.grayscale(cropped_img)
            proc = ImageEnhance.Contrast(proc).enhance(5.0) 
            # Binarization for absolute clarity
            proc = proc.point(lambda x: 0 if x < 128 else 255, '1') 
            
            st.write("Optimized Scan Preview:")
            st.image(proc, use_container_width=True)

            if st.button("🚀 Run Accuracy Scan", use_container_width=True):
                with st.spinner("Decoding..."):
                    barcodes = decode(proc)
                    if barcodes:
                        st.session_state.barcode_result = barcodes[0].data.decode('utf-8')
                        st.success(f"✅ Extracted: {st.session_state.barcode_result}")
                    else:
                        st.error("Scan Failed. Try cropping slightly wider.")

        # --- Step 4: Submission ---
        st.divider()
        final_serial = st.text_input("Verified Serial Number", value=st.session_state.get('barcode_result', ""))
        email = st.text_input("Installer Email")

        if st.button("✅ Submit Final Data", use_container_width=True):
            if final_serial and email:
                sheet_serials.append_row([udise, school, device, final_serial, email])
                st.success("Successfully Saved!")
                st.balloons()
                if 'barcode_result' in st.session_state:
                    del st.session_state['barcode_result']
            else:
                st.warning("Please scan a barcode and enter email.")
