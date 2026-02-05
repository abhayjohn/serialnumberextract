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

@st.cache_data(ttl=600) # Cache data for 10 minutes
def load_master_data():
    try:
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        client = gspread.authorize(creds)
        ss = client.open("School_Master_Serial_Number_Capture")
        sheet = ss.worksheet("school_master")
        df = pd.DataFrame(sheet.get_all_records())
        return df, ss.worksheet("smartboard_serials")
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return None, None

df_master, sheet_serials = load_master_data()

# 3. App UI
st.title("📟 Smartboard Serial Capture")

if df_master is not None:
    # Filter Logic
    st.sidebar.header("School Selection")
    
    # District Filter
    districts = sorted(df_master['District'].unique())
    selected_dist = st.sidebar.selectbox("Select District", ["All"] + districts)
    
    filtered_df = df_master.copy()
    if selected_dist != "All":
        filtered_df = filtered_df[filtered_df['District'] == selected_dist]
    
    # Block Filter
    blocks = sorted(filtered_df['Block'].unique())
    selected_block = st.sidebar.selectbox("Select Block", ["All"] + blocks)
    
    if selected_block != "All":
        filtered_df = filtered_df[filtered_df['Block'] == selected_block]
        
    # School Search / Select (with Searchable UI)
    school_list = sorted(filtered_df['School'].unique())
    selected_school = st.selectbox("Search/Select School Name", [""] + school_list)

    if selected_school:
        # Auto-fill UDISE based on school
        school_row = filtered_df[filtered_df['School'] == selected_school].iloc[0]
        udise_code = str(school_row['UDISE'])
        st.info(f"**UDISE Code:** {udise_code}")
        
        # Get devices for this school
        devices = filtered_df[filtered_df['School'] == selected_school]['Device Name'].tolist()
        device = st.selectbox("Select Device", devices)

        st.divider()
        
        # Step 2: OCR Logic
        st.subheader("Step 2: Serial Number Capture")
        up_file = st.file_uploader("Upload Serial Image", type=['png', 'jpg', 'jpeg'])
        
        if up_file:
            img = Image.open(up_file)
            # Pre-processing for better OCR
            gray_img = ImageOps.grayscale(img)
            st.image(gray_img, caption="Processed Image", width=300)
            
            if st.button("Extract Serial"):
                with st.spinner("Processing..."):
                    text = pytesseract.image_to_string(gray_img, config='--psm 6')
                    st.session_state.serial = text.strip()

        # Step 3: Manual Confirmation
        serial_final = st.text_input("Verified Serial Number", 
                                     value=st.session_state.get('serial', ""))
        email = st.text_input("Your Email Address")

        if st.button("Submit to Sheet"):
            if not serial_final or not email:
                st.warning("Please fill all details.")
            else:
                # Duplicate Check
                existing_serials = pd.DataFrame(sheet_serials.get_all_records())
                is_dup = False
                if not existing_serials.empty:
                    is_dup = ((existing_serials['UDISE'].astype(str) == udise_code) & 
                              (existing_serials['Device Name'] == device)).any()
                
                if is_dup:
                    st.error("Submission already exists for this device.")
                else:
                    sheet_serials.append_row([udise_code, selected_school, device, serial_final, email])
                    st.success("Data Saved Successfully!")
                    st.balloons()
