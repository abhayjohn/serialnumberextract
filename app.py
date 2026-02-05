import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from PIL import Image, ImageOps
import pytesseract
import os
import pandas as pd
from streamlit_cropper import st_cropper

# --- Page Config ---
st.set_page_config(page_title="Serial Capture", layout="wide")

# 1. Tesseract Path Handling
if os.name == 'nt': 
    pytesseract.pytesseract.tesseract_cmd = r"C:\Users\abhay_kssmart\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"

# 2. Data Loading
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

@st.cache_data(ttl=600)
def load_master_data():
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
        st.error(f"Error: {e}")
        return None, None

df_master, sheet_serials = load_master_data()

# --- App UI ---
st.title("📟 Serial Capture")

if df_master is not None:
    # --- STEP 1: FILTERS & SEARCH (Non-Mandatory) ---
    st.markdown("### 1. Select School")
    
    # Use columns for desktop; they stack on mobile automatically
    f_col1, f_col2 = st.columns(2)
    with f_col1:
        districts = sorted(df_master['District'].unique())
        sel_dist = st.selectbox("District Filter", ["All Districts"] + districts)
    with f_col2:
        if sel_dist != "All Districts":
            blocks = sorted(df_master[df_master['District'] == sel_dist]['Block'].unique())
            sel_block = st.selectbox("Block Filter", ["All Blocks"] + blocks)
        else:
            sel_block = st.selectbox("Block Filter", ["All Blocks"], disabled=True)

    # Filtering Logic (Invisible to user)
    filtered_df = df_master.copy()
    if sel_dist != "All Districts":
        filtered_df = filtered_df[filtered_df['District'] == sel_dist]
    if sel_block != "All Blocks":
        filtered_df = filtered_df[filtered_df['Block'] == sel_block]

    # The Primary Search Box
    filtered_df['search_display'] = filtered_df['UDISE'] + " - " + filtered_df['School']
    search_options = sorted(filtered_df['search_display'].unique())
    selected_option = st.selectbox("Search School Name or UDISE", [""] + search_options)

    # --- STEP 2: DEVICE & CAPTURE ---
    if selected_option:
        selected_udise = selected_option.split(" - ")[0]
        school_row = df_master[df_master['UDISE'] == selected_udise].iloc[0]
        
        st.success(f"📍 {school_row['School']}")
        
        # Select Device
        devices = df_master[df_master['UDISE'] == selected_udise]['Device Name'].tolist()
        selected_device = st.selectbox("Select Device", devices)

        st.divider()

        # Image Upload & Crop
        st.markdown("### 2. Capture Serial")
        up_file = st.file_uploader("Upload/Take Photo", type=['png', 'jpg', 'jpeg'])
        
        if up_file:
            img = Image.open(up_file)
            
            # The Cropper tool
            cropped_img = st_cropper(img, realtime_update=True, box_color='#FF0000', aspect_ratio=None)
            
            st.caption("Preview of Crop:")
            final_crop = cropped_img.convert('L') # Gray
            final_crop = ImageOps.autocontrast(final_crop)
            st.image(final_crop, use_container_width=True)

            if st.button("🚀 Scan Serial Number", use_container_width=True):
                with st.spinner("Processing OCR..."):
                    extracted_text = pytesseract.image_to_string(final_crop, config='--psm 7')
                    st.session_state.serial = extracted_text.strip()

        # --- STEP 3: SUBMIT ---
        st.divider()
        serial_final = st.text_input("Verified Serial Number", value=st.session_state.get('serial', ""))
        email = st.text_input("Your Email")

        sub_col1, sub_col2 = st.columns(2)
        with sub_col1:
            if st.button("✅ Submit", use_container_width=True):
                if not serial_final or not email:
                    st.warning("Enter Serial and Email.")
                else:
                    # Duplicate check
                    existing = pd.DataFrame(sheet_serials.get_all_records())
                    is_dup = False
                    if not existing.empty:
                        existing.columns = [str(c).strip() for c in existing.columns]
                        is_dup = ((existing['UDISE'].astype(str) == selected_udise) & 
                                  (existing['Device Name'] == selected_device)).any()
                    
                    if is_dup:
                        st.error("Submission already exists!")
                    else:
                        sheet_serials.append_row([selected_udise, school_row['School'], selected_device, serial_final, email])
                        st.success("Successfully Saved!")
                        st.balloons()
        
        with sub_col2:
            if st.button("🔄 Clear Form", use_container_width=True):
                for key in st.session_state.keys():
                    del st.session_state[key]
                st.rerun()
