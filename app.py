import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from PIL import Image, ImageOps, ImageEnhance
from pyzbar.pyzbar import decode
from streamlit_cropper import st_cropper

st.set_page_config(page_title="Master Serial Scanner", layout="wide")

# --- Optimized Data Loading ---
@st.cache_resource
def get_gspread_client():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_info = st.secrets["gcp_service_account"]
        credentials = Credentials.from_service_account_info(creds_info, scopes=scopes)
        client = gspread.authorize(credentials)
        client.set_timeout(120)
        return client
    except Exception as e:
        st.error(f"Auth Error: {e}")
        return None

@st.cache_data(ttl=3600) 
def load_master():
    client = get_gspread_client()
    if client:
        try:
            ss = client.open("School_Master_Serial_Number_Capture")
            df = pd.DataFrame(ss.worksheet("school_master").get_all_records())
            df['UDISE'] = df['UDISE'].astype(str)
            return df
        except Exception as e:
            st.error(f"Quota Error: {e}")
    return None

df_master = load_master()

# --- UI Layout ---
st.title("📟 Pro Thin-Panel Scanner")

if df_master is not None:
    # Unified Search
    f_df = df_master.copy()
    f_df['search'] = f_df['UDISE'] + " - " + f_df['School']
    selected = st.selectbox("1. Find School", [""] + sorted(f_df['search'].unique()))

    if selected:
        udise = selected.split(" - ")[0]
        school = df_master[df_master['UDISE'] == udise].iloc[0]['School']
        device = st.selectbox("2. Select Device", df_master[df_master['UDISE'] == udise]['Device Name'].tolist())

        st.divider()
        
        # Capture Logic
        img_file = st.file_uploader("3. Capture Photo (Landscape Recommended)", type=['jpg', 'jpeg', 'png'])

        if img_file:
            raw_img = Image.open(img_file)
            st.warning("✂️ CROP: Focus tightly on the barcode only.")
            
            # The Cropper
            cropped = st_cropper(raw_img, realtime_update=True, box_color='#00FF00', aspect_ratio=None)
            
            # Processing Pipeline
            proc = ImageOps.grayscale(cropped)
            proc = ImageEnhance.Contrast(proc).enhance(5.0)
            # Binary Thresholding for 20-digit accuracy
            proc = proc.point(lambda x: 0 if x < 150 else 255, '1')
            
            st.image(proc, caption="Optimized Preview", use_container_width=True)

            if st.button("🚀 SCAN NOW"):
                barcodes = decode(proc)
                if barcodes:
                    st.session_state.result = barcodes[0].data.decode('utf-8')
                    st.success(f"Successfully Decoded: {st.session_state.result}")
                else:
                    st.error("No code found. Try a wider crop or better lighting.")

        # Verification & Submit
        st.divider()
        final_val = st.text_input("4. Verified Serial", value=st.session_state.get('result', ""))
        email = st.text_input("5. Your Email")

        if st.button("✅ Submit to Google Sheet"):
            if final_val and email:
                client = get_gspread_client()
                ss = client.open("School_Master_Serial_Number_Capture")
                ss.worksheet("smartboard_serials").append_row([udise, school, device, final_val, email])
                st.success("Data Saved!")
                st.balloons()
