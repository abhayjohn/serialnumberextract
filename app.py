import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from PIL import Image, ImageOps
import pytesseract
import os
import pandas as pd
from streamlit_cropper import st_cropper

# --- Page Config for Mobile ---
st.set_page_config(
    page_title="Serial Capture", 
    layout="wide",  # "wide" helps elements use the full mobile screen width
    initial_sidebar_state="collapsed" # Hide sidebar by default on mobile to save space
)

# 1. Tesseract Path Handling
if os.name == 'nt': 
    pytesseract.pytesseract.tesseract_cmd = r"C:\Users\abhay_kssmart\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"

# 2. Secure Credentials & Data Loading
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

@st.cache_data(ttl=600)
def load_master_data():
    try:
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        client = gspread.authorize(creds)
        ss = client.open("School_Master_Serial_Number_Capture")
        master_sheet = ss.worksheet("school_master")
        df = pd.DataFrame(master_sheet.get_all_records())
        df.columns = [str(c).strip() for c in df.columns]
        df['UDISE'] = df['UDISE'].astype(str)
        return df, ss.worksheet("smartboard_serials")
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return None, None

df_master, sheet_serials = load_master_data()

# --- App UI ---
st.title("📟 Serial Capture")

if df_master is not None:
    # --- Step 1: Search & Filter ---
    with st.expander("🔍 Filter by Location (Optional)", expanded=False):
        # On mobile, these will stack automatically
        districts = sorted(df_master['District'].unique())
        sel_dist = st.selectbox("District", ["All"] + districts)
        
        if sel_dist != "All":
            blocks = sorted(df_master[df_master['District'] == sel_dist]['Block'].unique())
            sel_block = st.selectbox("Block", ["All"] + blocks)
        else:
            sel_block = st.selectbox("Block", ["All"], disabled=True)

    # Filtered logic
    filtered_df = df_master.copy()
    if sel_dist != "All": filtered_df = filtered_df[filtered_df['District'] == sel_dist]
    if sel_block != "All": filtered_df = filtered_df[filtered_df['Block'] == sel_block]

    filtered_df['search_display'] = filtered_df['UDISE'] + " - " + filtered_df['School']
    search_options = sorted(filtered_df['search_display'].unique())
    
    st.markdown("### 1. Select School")
    selected_option = st.selectbox("Type UDISE or School Name", [""] + search_options)

    if selected_option:
        selected_udise = selected_option.split(" - ")[0]
        selected_school_row = df_master[df_master['UDISE'] == selected_udise].iloc[0]
        
        # --- Step 2: Device Selection ---
        st.info(f"📍 {selected_school_row['School']}")
        udise_code = selected_school_row['UDISE']
        devices = df_master[df_master['UDISE'] == udise_code]['Device Name'].tolist()
        selected_device = st.selectbox("Select Device", devices)

        st.divider()

        # --- Step 3: Image Upload & Crop ---
        st.markdown("### 2. Capture Serial")
        # 'use_camera' parameter helps mobile browsers trigger the camera directly
        up_file = st.file_uploader("Take Photo or Upload", type=['png', 'jpg', 'jpeg'])
        
        if up_file:
            img = Image.open(up_file)
            
            st.caption("✂️ Crop the Serial Number for accuracy:")
            # Set a smaller stroke width for mobile visibility
            cropped_img = st_cropper(
                img, 
                realtime_update=True, 
                box_color='#FF0000', 
                aspect_ratio=None,
                should_resize_landscape=True # Helps with landscape mobile photos
            )
            
            # Preview and Scan
            st.markdown("#### Crop Preview")
            final_crop = cropped_img.convert('L')
            st.image(final_crop, use_container_width=True) # Mobile responsive image

            if st.button("🚀 Run OCR Scan", use_container_width=True):
                with st.spinner("Reading..."):
                    text = pytesseract.image_to_string(final_crop, config='--psm 7')
                    st.session_state.serial = text.strip()

        # --- Step 4: Submission ---
        st.divider()
        serial_final = st.text_input("Confirm Serial Number", value=st.session_state.get('serial', ""))
        email = st.text_input("Your Email Address")

        # use_container_width=True makes the button full-width on mobile
        if st.button("✅ Submit Data", use_container_width=True):
            if not serial_final or not email:
                st.warning("Please enter Serial and Email.")
            else:
                existing_serials = pd.DataFrame(sheet_serials.get_all_records())
                is_dup = False
                if not existing_serials.empty:
                    existing_serials.columns = [str(c).strip() for c in existing_serials.columns]
                    is_dup = ((existing_serials['UDISE'].astype(str) == udise_code) & 
                              (existing_serials['Device Name'] == selected_device)).any()
                
                if is_dup:
                    st.error("Already submitted for this device.")
                else:
                    sheet_serials.append_row([udise_code, selected_school_row['School'], selected_device, serial_final, email])
                    st.success("Successfully Saved!")
                    st.balloons()
