import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from PIL import Image, ImageOps, ImageEnhance
from pyzbar.pyzbar import decode

# --- 1. Page Config & Mobile CSS Fix ---
st.set_page_config(page_title="Serial Scanner", layout="wide")

st.markdown("""
    <style>
    /* Force camera input to be full width on mobile */
    div[data-testid="stCameraInput"] {
        width: 100% !important;
    }
    /* Expand video height and maintain aspect ratio */
    div[data-testid="stCameraInput"] video {
        width: 100% !important;
        height: auto !important;
        border-radius: 8px;
        border: 2px solid #ff4b4b;
    }
    /* Make buttons bigger for easier mobile tapping */
    .stButton>button {
        width: 100%;
        height: 3em;
        font-size: 18px !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. Data Loading (Cached) ---
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

@st.cache_data(ttl=600)
def load_data():
    try:
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        client = gspread.authorize(creds)
        ss = client.open("School_Master_Serial_Number_Capture")
        
        # Load School Master
        df = pd.DataFrame(ss.worksheet("school_master").get_all_records())
        df.columns = [str(c).strip() for c in df.columns]
        df['UDISE'] = df['UDISE'].astype(str)
        
        return df, ss.worksheet("smartboard_serials")
    except Exception as e:
        st.error(f"Configuration Error: {e}")
        return None, None

df_master, sheet_serials = load_data()

# --- 3. App UI Flow ---
st.title("📟 Smartboard Serial Capture")

if df_master is not None:
    # --- Step 1: Identify School ---
    st.markdown("### 1. Select School")
    
    # Filter Columns (Stack automatically on mobile)
    col1, col2 = st.columns(2)
    with col1:
        dists = sorted(df_master['District'].unique())
        sel_dist = st.selectbox("District Filter", ["All"] + dists)
    with col2:
        blocks = ["All"]
        if sel_dist != "All":
            blocks = sorted(df_master[df_master['District'] == sel_dist]['Block'].unique())
        sel_block = st.selectbox("Block Filter", blocks)

    # Filtered List
    f_df = df_master.copy()
    if sel_dist != "All": f_df = f_df[f_df['District'] == sel_dist]
    if sel_block != "All": f_df = f_df[f_df['Block'] == sel_block]

    f_df['search_display'] = f_df['UDISE'] + " - " + f_df['School']
    search_list = sorted(f_df['search_display'].unique())
    selected_option = st.selectbox("Search School Name or UDISE", [""] + search_list)

    if selected_option:
        udise_code = selected_option.split(" - ")[0]
        school_row = df_master[df_master['UDISE'] == udise_code].iloc[0]
        st.success(f"📍 {school_row['School']}")
        
        devices = df_master[df_master['UDISE'] == udise_code]['Device Name'].tolist()
        device = st.selectbox("Select Device", devices)

        st.divider()

        # --- Step 2: Barcode Scanner ---
        st.markdown("### 2. Scan Barcode")
        st.info("💡 Position the barcode in the center. Avoid shadows and glare.")
        
        # This will now be full-width due to the CSS fix
        img_file = st.camera_input("Scan Barcode")
        
        scanned_val = ""
        if img_file:
            with st.spinner("Decoding..."):
                # Image processing for clarity
                raw_img = Image.open(img_file)
                proc_img = ImageOps.grayscale(raw_img)
                enhancer = ImageEnhance.Contrast(proc_img)
                proc_img = enhancer.enhance(2.0) # Boost contrast for sharp lines
                
                # Scan
                barcodes = decode(proc_img)
                
                if barcodes:
                    scanned_val = barcodes[0].data.decode('utf-8')
                    st.success(f"✅ Scanned: **{scanned_val}**")
                else:
                    st.error("Could not read barcode. Try moving slightly further away.")
                    # Show the processed image so user can check focus
                    with st.expander("Show Scan Preview"):
                        st.image(proc_img, use_container_width=True)

        # --- Step 3: Submission ---
        st.divider()
        final_serial = st.text_input("Verified Serial", value=scanned_val)
        email = st.text_input("Your Email Address")

        if st.button("✅ Submit Data", use_container_width=True):
            if not final_serial or not email:
                st.warning("Please scan a barcode and enter your email.")
            else:
                with st.spinner("Checking for duplicates..."):
                    existing = pd.DataFrame(sheet_serials.get_all_records())
                    is_dup = False
                    if not existing.empty:
                        existing.columns = [str(c).strip() for c in existing.columns]
                        is_dup = ((existing['UDISE'].astype(str) == udise_code) & 
                                  (existing['Device Name'] == device)).any()
                    
                    if is_dup:
                        st.error("Duplicate Entry: This device already has a serial recorded.")
                    else:
                        sheet_serials.append_row([udise_code, school_row['School'], device, final_serial, email])
                        st.success("Successfully Saved!")
                        st.balloons()
