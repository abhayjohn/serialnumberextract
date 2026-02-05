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
        
        # Standardize Headers & ensure UDISE is string for searching
        df.columns = [str(c).strip() for c in df.columns]
        df['UDISE'] = df['UDISE'].astype(str)
        
        return df, ss.worksheet("smartboard_serials")
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return None, None

df_master, sheet_serials = load_master_data()

# 3. App UI
st.set_page_config(page_title="Serial Capture", layout="centered")
st.title("📟 Smartboard Serial Capture")

if df_master is not None:
    st.markdown("### Step 1: Find School")
    
    # Optional Filters in columns
    col1, col2 = st.columns(2)
    with col1:
        districts = sorted(df_master['District'].unique())
        sel_dist = st.selectbox("Filter by District", ["All"] + districts)
    with col2:
        if sel_dist != "All":
            blocks = sorted(df_master[df_master['District'] == sel_dist]['Block'].unique())
            sel_block = st.selectbox("Filter by Block", ["All"] + blocks)
        else:
            sel_block = st.selectbox("Filter by Block", ["All"], disabled=True)

    # Apply Filters to the dataframe
    filtered_df = df_master.copy()
    if sel_dist != "All":
        filtered_df = filtered_df[filtered_df['District'] == sel_dist]
    if sel_block != "All":
        filtered_df = filtered_df[filtered_df['Block'] == sel_block]

    # UNIFIED SEARCH: Display "UDISE - School Name"
    # This allows users to type either the UDISE or the Name into the same box
    filtered_df['search_display'] = filtered_df['UDISE'] + " - " + filtered_df['School']
    
    search_options = sorted(filtered_df['search_display'].unique())
    selected_option = st.selectbox("Type UDISE or School Name", [""] + search_options)

    if selected_option:
        # Extract the UDISE from the selection (it's the first part before the " - ")
        selected_udise = selected_option.split(" - ")[0]
        selected_school_row = df_master[df_master['UDISE'] == selected_udise].iloc[0]
        
        st.success(f"Selected: {selected_school_row['School']} ({selected_udise})")
        st.divider()

        # 4. Device and OCR Section
        udise_code = selected_school_row['UDISE']
        school_name = selected_school_row['School']
        
        # Get devices for this school
        # (Handling cases where 'Device Name' column might have slight variations)
        dev_col = next((c for c in df_master.columns if "device" in c.lower()), "Device Name")
        devices = df_master[df_master['UDISE'] == udise_code][dev_col].tolist()
        selected_device = st.selectbox("Select Device", devices)

        st.subheader("Step 2: Serial Capture")
        up_file = st.file_uploader("Upload Serial Photo", type=['png', 'jpg', 'jpeg'])
        
        if up_file:
            img = Image.open(up_file)
            gray = ImageOps.grayscale(img)
            gray = ImageOps.autocontrast(gray)
            st.image(gray, caption="OCR Preview", width=300)
            
            if st.button("Extract Text from Image"):
                with st.spinner("Reading Serial..."):
                    text = pytesseract.image_to_string(gray, config='--psm 6')
                    st.session_state.serial = text.strip()

        # Final Verification
        serial_final = st.text_input("Verified Serial Number", value=st.session_state.get('serial', ""))
        email = st.text_input("Your Email")

        if st.button("Submit Data"):
            if not serial_final or not email:
                st.warning("Please complete all fields.")
            else:
                # Duplicate Check
                existing_serials = pd.DataFrame(sheet_serials.get_all_records())
                is_dup = False
                if not existing_serials.empty:
                    # Clean headers of existing_serials too
                    existing_serials.columns = [str(c).strip() for c in existing_serials.columns]
                    is_dup = ((existing_serials['UDISE'].astype(str) == udise_code) & 
                              (existing_serials['Device Name'] == selected_device)).any()
                
                if is_dup:
                    st.error(f"Entry already exists for {selected_device} at this school.")
                else:
                    sheet_serials.append_row([udise_code, school_name, selected_device, serial_final, email])
                    st.success("Successfully saved to Google Sheets!")
                    st.balloons()
