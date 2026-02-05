import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from PIL import Image, ImageOps, ImageEnhance
from pyzbar.pyzbar import decode
from streamlit_cropper import st_cropper

# --- 1. Page Config ---
st.set_page_config(page_title="Serial Capture", layout="wide")

# CSS for better mobile button sizing
st.markdown("""
    <style>
    .stButton>button { width: 100%; height: 3.5em; font-weight: bold; border-radius: 10px; }
    div[data-testid="stFileUploader"] { width: 100% !important; }
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
st.title("📟 Full-Screen Serial Capture")

if df_master is not None:
    # --- Step 1: Search Logic ---
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

        # --- Step 2: Capture (Native Full Screen) ---
        st.markdown("### 2. Capture Barcode")
        st.info("📸 Click below and choose 'Take Photo' to open your FULL-SCREEN camera.")
        
        # Using file_uploader triggers the native mobile camera app
        img_file = st.file_uploader("Tap to open Camera", type=['jpg', 'jpeg', 'png'])

        if img_file:
            raw_img = Image.open(img_file)
            
            # --- Step 3: WhatsApp Style Crop ---
            st.markdown("### ✂️ Crop & Scan")
            # Cropper helps isolate the barcode from the full-sized photo
            cropped_img = st_cropper(raw_img, realtime_update=True, box_color='#00FF00', aspect_ratio=None)
            
            # Enhancement for scan accuracy
            proc = ImageOps.grayscale(cropped_img)
            proc = ImageEnhance.Contrast(proc).enhance(3.0)
            
            st.image(proc, caption="Ready for Scan", use_container_width=True)

            if st.button("🚀 Scan Barcode", use_container_width=True):
                with st.spinner("Decoding..."):
                    barcodes = decode(proc)
                    if barcodes:
                        st.session_state.barcode_result = barcodes[0].data.decode('utf-8')
                        st.success(f"✅ Found: {st.session_state.barcode_result}")
                    else:
                        st.error("No barcode detected. Ensure you cropped ONLY the barcode lines.")

        # --- Step 4: Verification & Submit ---
        st.divider()
        final_serial = st.text_input("Verified Serial Number", value=st.session_state.get('barcode_result', ""))
        email = st.text_input("Installer Email")

        if st.button("✅ Submit Final Data", use_container_width=True):
            if not (final_serial and email):
                st.warning("Please complete all fields.")
            else:
                sheet_serials.append_row([udise, school, device, final_serial, email])
                st.success("Successfully Saved!")
                st.balloons()
                if 'barcode_result' in st.session_state:
                    del st.session_state['barcode_result']
