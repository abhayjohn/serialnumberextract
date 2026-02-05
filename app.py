import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from PIL import Image, ImageOps, ImageEnhance
from pyzbar.pyzbar import decode
from streamlit_cropper import st_cropper

# --- 1. Page Config & Mobile UI Enhancement ---
st.set_page_config(page_title="Serial Capture", layout="wide")

# CSS to make the camera full width and buttons thumb-friendly
st.markdown("""
    <style>
    /* Force camera to use full mobile screen width */
    div[data-testid="stCameraInput"] { 
        width: 100% !important; 
    }
    div[data-testid="stCameraInput"] video { 
        width: 100% !important; 
        height: auto !important; 
        border-radius: 12px;
        border: 2px solid #00FF00;
    }
    /* Larger buttons for mobile installers */
    .stButton>button { 
        width: 100%; 
        height: 3.5em; 
        font-size: 18px !important; 
        font-weight: bold; 
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
        st.error(f"Data Load Error: {e}")
        return None, None

df_master, sheet_serials = load_data()

# --- 3. App Logic ---
st.title("📟 Smartboard Serial Capture")

if df_master is not None:
    # --- STEP 1: All Search Features Preserved ---
    st.markdown("### 1. Identify School")
    
    col1, col2 = st.columns(2)
    with col1:
        districts = sorted(df_master['District'].unique())
        sel_dist = st.selectbox("District Filter", ["All"] + districts)
    with col2:
        blocks = ["All"]
        if sel_dist != "All":
            blocks = sorted(df_master[df_master['District'] == sel_dist]['Block'].unique())
        sel_block = st.selectbox("Block Filter", blocks)

    f_df = df_master.copy()
    if sel_dist != "All": f_df = f_df[f_df['District'] == sel_dist]
    if sel_block != "All": f_df = f_df[f_df['Block'] == sel_block]

    f_df['search_display'] = f_df['UDISE'] + " - " + f_df['School']
    selected_option = st.selectbox("Search School Name or UDISE", [""] + sorted(f_df['search_display'].unique()))

    if selected_option:
        udise = selected_option.split(" - ")[0]
        school_row = df_master[df_master['UDISE'] == udise].iloc[0]
        st.success(f"📍 {school_row['School']}")
        
        device = st.selectbox("Select Device", df_master[df_master['UDISE'] == udise]['Device Name'].tolist())

        st.divider()

        # --- STEP 2: Capture & Sequential Crop (WhatsApp Style) ---
        st.markdown("### 2. Capture Barcode")
        
        # camera_input uses the browser's default camera. 
        # Most mobile browsers provide a 'switch camera' button on screen.
        img_file = st.camera_input("Take a clear photo of the barcode")

        scanned_val = ""
        
        if img_file:
            # Step A: Image is captured
            raw_img = Image.open(img_file)
            
            # Step B: Sequential Cropping Window (Expander)
            st.info("💡 WhatsApp Style: Crop the photo below to focus on the barcode.")
            with st.expander("✂️ CROP IMAGE", expanded=True):
                # aspect_ratio=None allows for long thin barcodes
                cropped_img = st_cropper(raw_img, realtime_update=True, box_color='#00FF00', aspect_ratio=None)
                
                # Pre-processing for the scanner
                proc = ImageOps.grayscale(cropped_img)
                proc = ImageEnhance.Contrast(proc).enhance(3.0)
                st.image(proc, caption="Ready to Scan", use_container_width=True)

                if st.button("🚀 Scan Cropped Barcode", use_container_width=True):
                    with st.spinner("Decoding..."):
                        barcodes = decode(proc)
                        if barcodes:
                            scanned_val = barcodes[0].data.decode('utf-8')
                            st.session_state.barcode_result = scanned_val
                            st.success(f"✅ Extracted: {scanned_val}")
                        else:
                            st.error("No barcode detected. Try cropping tighter or retaking the photo.")

        # --- STEP 3: Final Verification & Submit ---
        st.divider()
        final_serial = st.text_input("Verified Serial Number", value=st.session_state.get('barcode_result', ""))
        email = st.text_input("Your Email Address")

        if st.button("✅ Submit Data to Sheet", use_container_width=True):
            if not final_serial or not email:
                st.warning("Please scan a barcode and enter your email.")
            else:
                with st.spinner("Saving..."):
                    sheet_serials.append_row([udise, school_row['School'], device, final_serial, email])
                    st.success("Successfully Saved!")
                    st.balloons()
                    # Clear session state for next entry
                    if 'barcode_result' in st.session_state:
                        del st.session_state['barcode_result']
