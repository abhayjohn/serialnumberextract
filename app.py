import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from PIL import Image, ImageOps, ImageEnhance
import pytesseract
from streamlit_cropper import st_cropper

# --- 1. Page Config ---
st.set_page_config(page_title="Pro OCR Serial Capture", layout="wide")

st.markdown("""
    <style>
    .stApp { max-width: 100%; padding: 0px; }
    .stButton>button { width: 100%; height: 3.5em; font-weight: bold; border-radius: 12px; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. Robust Data Loading ---
@st.cache_resource
def get_client():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_info = st.secrets["gcp_service_account"]
        credentials = Credentials.from_service_account_info(creds_info, scopes=scopes)
        client = gspread.authorize(credentials)
        client.set_timeout(120) # Increase timeout for mobile stability
        return client
    except Exception as e:
        st.error(f"Auth Error: {e}")
        return None

@st.cache_data(ttl=3600)
def load_data():
    client = get_client()
    if client:
        try:
            ss = client.open("School_Master_Serial_Number_Capture")
            df = pd.DataFrame(ss.worksheet("school_master").get_all_records())
            df['UDISE'] = df['UDISE'].astype(str)
            return df
        except Exception as e:
            st.error(f"Data Load Error: {e}")
    return None

df_master = load_data()

# --- 3. App UI ---
st.title("📟 OCR Serial Capture")

if df_master is not None:
    st.markdown("### 1. Identify School")
    
    # District and Block Filters
    col1, col2 = st.columns(2)
    with col1:
        dists = sorted(df_master['District'].unique())
        sel_dist = st.selectbox("Select District", ["All"] + dists)
    with col2:
        blocks = ["All"]
        if sel_dist != "All":
            blocks = sorted(df_master[df_master['District'] == sel_dist]['Block'].unique())
        sel_block = st.selectbox("Select Block", blocks)

    # Filter Data based on selection
    f_df = df_master.copy()
    if sel_dist != "All": f_df = f_df[f_df['District'] == sel_dist]
    if sel_block != "All": f_df = f_df[f_df['Block'] == sel_block]

    f_df['search'] = f_df['UDISE'] + " - " + f_df['School']
    selected_option = st.selectbox("Search School/UDISE", [""] + sorted(f_df['search'].unique()))

    if selected_option:
        udise = selected_option.split(" - ")[0]
        school_data = df_master[df_master['UDISE'] == udise].iloc[0]
        st.success(f"📍 {school_data['School']} ({school_data['District']} - {school_data['Block']})")
        device = st.selectbox("Select Device", df_master[df_master['UDISE'] == udise]['Device Name'].tolist())

        st.divider()
        st.markdown("### 2. Capture & OCR")
        img_file = st.file_uploader("📸 Take Photo of Serial Text", type=['jpg', 'jpeg', 'png'])

        if img_file:
            raw_img = Image.open(img_file)
            st.info("✂️ CROP: Focus tightly on the serial number text.")
            
            # Cropper
            cropped = st_cropper(raw_img, realtime_update=True, box_color='#00FF00', aspect_ratio=None)
            
            # --- OCR Enhancement Pipeline ---
            # 1. Upscale for better character recognition
            w, h = cropped.size
            zoom_img = cropped.resize((w*3, h*3), Image.Resampling.LANCZOS)
            
            # 2. Grayscale & Contrast
            proc = ImageOps.grayscale(zoom_img)
            proc = ImageEnhance.Contrast(proc).enhance(5.0)
            
            # 3. Thresholding slider for varying light
            threshold = st.slider("Text Thickness Adjustment", 50, 220, 140)
            proc = proc.point(lambda x: 0 if x < threshold else 255, '1')
            
            st.image(proc, caption="OCR Optimized View", use_container_width=True)

            if st.button("🚀 READ SERIAL (OCR)"):
                with st.spinner("Analyzing text..."):
                    # PSM 6 is best for a single line of uniform text
                    custom_config = r'--oem 3 --psm 6'
                    text_out = pytesseract.image_to_string(proc, config=custom_config)
                    
                    # Clean common prefixes found on labels
                    extracted = text_out.replace("S/N:", "").replace("SN:", "").replace("Serial", "").strip()
                    st.session_state.result = extracted
                    st.success(f"Extracted: {extracted}")

        # --- Step 4: Submission ---
        st.divider()
        final_serial = st.text_input("Verified Serial Number", value=st.session_state.get('result', ""))
        email = st.text_input("Your Email")

        if st.button("✅ Submit Final Data"):
            if final_serial and email:
                try:
                    client = get_client()
                    ss = client.open("School_Master_Serial_Number_Capture")
                    sheet = ss.worksheet("smartboard_serials")
                    
                    # Log District and Block along with the serial data
                    sheet.append_row([
                        school_data['District'], 
                        school_data['Block'], 
                        udise, 
                        school_data['School'], 
                        device, 
                        final_serial, 
                        email
                    ])
                    
                    st.success("Successfully Saved to Google Sheets!")
                    st.balloons()
                    if 'result' in st.session_state: del st.session_state['result']
                except Exception as e:
                    st.error(f"Submission Error: {e}")
            else:
                st.warning("Please verify the serial and enter your email.")
