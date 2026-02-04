import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from PIL import Image
import pytesseract
import os

# -----------------------
# 1. Tesseract OCR Setup
# -----------------------
# On Streamlit Cloud, Tesseract is installed via packages.txt and is in the PATH.
# We only manually set the path if running locally on Windows.
if os.name == 'nt': 
    pytesseract.pytesseract.tesseract_cmd = r"C:\Users\abhay_kssmart\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"

# -----------------------
# 2. Google Sheets Setup
# -----------------------
SCOPE = ['https://spreadsheets.google.com/feeds',
         'https://www.googleapis.com/auth/drive']

@st.cache_resource
def get_gspread_client():
    # Use Streamlit Secrets for security (stored in the dashboard, not GitHub)
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
    return gspread.authorize(creds)

try:
    client = get_gspread_client()
    GSHEET_NAME = "School_Master_Serial_Number_Capture"
    sheet_master = client.open(GSHEET_NAME).worksheet("school_master")
    sheet_serials = client.open(GSHEET_NAME).worksheet("smartboard_serials")
except Exception as e:
    st.error(f"Configuration Error: {e}")
    st.info("Check if secrets are added in Streamlit Dashboard and the Sheet is shared with the Service Account email.")
    st.stop()

# -----------------------
# 3. App UI & Logic
# -----------------------
st.set_page_config(page_title="Serial Capture", page_icon="📝")
st.title("📟 Smartboard Serial Number Capture")

# Initialize session state for all variables
for key in ["udise", "school", "devices", "selected_device", "serial_number", "user_email"]:
    if key not in st.session_state:
        st.session_state[key] = None

# --- Step 1: Search School ---
st.subheader("Step 1: Locate School")
udise_input = st.text_input("Enter UDISE Code", value=st.session_state.udise or "")

if st.button("Search School"):
    if udise_input:
        with st.spinner("Fetching school data..."):
            st.session_state.udise = udise_input.strip()
            master_data = sheet_master.get_all_records()
            
            devices = []
            school_name = ""
            for row in master_data:
                if str(row["UDISE"]) == st.session_state.udise and row["Status"] != "Inactive":
                    devices.append(row["Device Name"])
                    school_name = row["School"]
            
            if school_name:
                st.session_state.devices = devices
                st.session_state.school = school_name
                st.session_state.selected_device = None
                st.session_state.serial_number = ""
                st.success(f"Found: {school_name}")
            else:
                st.error("UDISE not found or Inactive.")
    else:
        st.warning("Please enter a UDISE code.")

# --- Step 2: Device & OCR ---
if st.session_state.school:
    st.divider()
    st.subheader(f"School: {st.session_state.school}")
    
    selected_device = st.selectbox(
        "Select Device to update",
        st.session_state.devices
    )
    st.session_state.selected_device = selected_device

    # Image Upload & OCR
    st.write("---")
    st.markdown("### Step 2: Extract Serial Number")
    uploaded_file = st.file_uploader("Upload Serial Number Photo", type=["jpg", "jpeg", "png"])
    
    if uploaded_file:
        img = Image.open(uploaded_file)
        st.image(img, caption="Uploaded Image", width=300)
        
        if st.button("Run OCR"):
            with st.spinner("Reading image..."):
                try:
                    text = pytesseract.image_to_string(img)
                    st.session_state.serial_number = text.strip()
                except Exception as ocr_err:
                    st.error("OCR Error. Is Tesseract installed?")

    # Manual Correction & Email
    serial_input = st.text_input("Confirm/Edit Serial Number", value=st.session_state.serial_number or "")
    email_input = st.text_input("Your Email Address", value=st.session_state.user_email or "")

    # --- Step 3: Submit ---
    if st.button("Submit to Database"):
        if not serial_input or not email_input:
            st.warning("Please provide both the Serial Number and your Email.")
        else:
            with st.spinner("Checking for duplicates and saving..."):
                st.session_state.serial_number = serial_input.strip()
                st.session_state.user_email = email_input.strip()
                
                # Check duplicate (UDISE + Device Name)
                existing = sheet_serials.get_all_records()
                duplicate = any(
                    str(row["UDISE"]) == st.session_state.udise and 
                    str(row["Device Name"]) == st.session_state.selected_device 
                    for row in existing
                )
                
                if duplicate:
                    st.error(f"Error: A serial number has already been submitted for {st.session_state.selected_device} at this school.")
                else:
                    sheet_serials.append_row([
                        st.session_state.udise,
                        st.session_state.school,
                        st.session_state.selected_device,
                        st.session_state.serial_number,
                        st.session_state.user_email
                    ])
                    st.success("✅ Submission Successful!")
                    st.balloons()
