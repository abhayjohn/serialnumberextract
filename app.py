import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from PIL import Image, ImageOps
import pytesseract
import os
import pandas as pd

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
        
        # Load School Master
        master_sheet = ss.worksheet("school_master")
        df = pd.DataFrame(master_sheet.get_all_records())
        
        # Standardize Headers: Remove spaces, convert to title case
        df.columns = [str(c).strip() for c in df.columns]
        
        return df, ss.worksheet("smartboard_serials")
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return None, None

df_master, sheet_serials = load_master_data()

# 3. App UI
st.set_page_config(page_title="Serial Capture", layout="centered")
st.title("📟 Smartboard Serial Capture")

if df_master is not None:
    # SEARCH MODE TOGGLE
    search_mode = st.radio("Search Method", ["Browse by Location", "Search by UDISE"], horizontal=True)
    
    selected_school_row = None

    if search_mode == "Browse by Location":
        col1, col2 = st.columns(2)
        with col1:
            districts = sorted(df_master['District'].unique())
            selected_dist = st.selectbox("District", ["Select"] + districts)
        
        with col2:
            if selected_dist != "Select":
                blocks = sorted(df_master[df_master['District'] == selected_dist]['Block'].unique())
                selected_block = st.selectbox("Block", ["Select"] + blocks)
            else:
                st.selectbox("Block", ["Select"], disabled=True)

        if selected_dist != "Select" and selected_block != "Select":
            school_list = sorted(df_master[(df_master['District'] == selected_dist) & 
                                         (df_master['Block'] == selected_block)]['School'].unique())
            school_name = st.selectbox("Select School", [""] + school_list)
            if school_name:
                selected_school_row = df_master[df_master['School'] == school_name].iloc[0]

    else: # Search by UDISE
        udise_input = st.text_input("Enter 11-Digit UDISE Code")
        if udise_input:
            match = df_master[df_master['UDISE'].astype(str) == udise_input.strip()]
            if not match.empty:
                selected_school_row = match.iloc[0]
                st.success(f"✅ School Found: {selected_school_row['School']}")
            else:
                st.error("❌ UDISE not found.")

    # 4. Device and OCR Section
    if selected_school_row is not None:
        st.divider()
        udise_code = str(selected_school_row['UDISE'])
        school_name = selected_school_row['School']
        
        # Get devices for this specific UDISE
        devices = df_master[df_master['UDISE'].astype(str) == udise_code]['Device Name'].tolist()
        selected_device = st.selectbox("Select Device", devices)

        st.subheader("Step 2: Serial Capture")
        up_file = st.file_uploader("Upload Serial Photo", type=['png', 'jpg', 'jpeg'])
        
        if up_file:
            img = Image.open(up_file)
            # Basic Image Processing for OCR
            gray = ImageOps.grayscale(img)
            # Increase contrast
            gray = ImageOps.autocontrast(gray)
            st.image(gray, caption="Ready for OCR", width=300)
            
            if st.button("Extract Text"):
                # psm 6: Assume a single uniform block of text
                # psm 7: Treat the image as a single text line
                text = pytesseract.image_to_string(gray, config='--psm 6')
                st.session_state.serial = text.strip()

        # Final Verification
        serial_final = st.text_input("Verified Serial Number", value=st.session_state.get('serial', ""))
        email = st.text_input("Your Email")

        if st.button("Submit Data"):
            if not serial_final or not email:
                st.warning("Please complete all fields.")
            else:
                # Duplicate Check logic
                existing_serials = pd.DataFrame(sheet_serials.get_all_records())
                is_dup = False
                if not existing_serials.empty:
                    is_dup = ((existing_serials['UDISE'].astype(str) == udise_code) & 
                              (existing_serials['Device Name'] == selected_device)).any()
                
                if is_dup:
                    st.error(f"Entry already exists for {selected_device} at this school.")
                else:
                    sheet_serials.append_row([udise_code, school_name, selected_device, serial_final, email])
                    st.success("Successfully saved to Google Sheets!")
                    st.balloons()
