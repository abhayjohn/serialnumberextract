import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from PIL import Image
import pytesseract
from io import BytesIO
pytesseract.pytesseract.tesseract_cmd = r"C:\Users\abhay_kssmart\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
# -----------------------
# Google Sheets Setup
# -----------------------
SCOPE = ['https://spreadsheets.google.com/feeds',
         'https://www.googleapis.com/auth/drive']

CREDS_FILE = "service_account.json"  # Your Service Account JSON
GSHEET_NAME = "School_Master_Serial_Number_Capture"

creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPE)
client = gspread.authorize(creds)
sheet_master = client.open(GSHEET_NAME).worksheet("school_master")
sheet_serials = client.open(GSHEET_NAME).worksheet("smartboard_serials")

# -----------------------
# Streamlit UI
# -----------------------
st.title("Smartboard Serial Number Collection (Tesseract OCR)")

# Initialize session state
for key in ["udise", "school", "devices", "selected_device",
            "uploaded_image", "serial_number", "user_email"]:
    if key not in st.session_state:
        st.session_state[key] = None

# Step 1: Search School
udise_input = st.text_input("Enter UDISE", st.session_state.udise or "")
if st.button("Search School"):
    st.session_state.udise = udise_input.strip()
    # Load devices from master sheet
    master_data = sheet_master.get_all_records()
    devices = []
    school_name = ""
    for row in master_data:
        if str(row["UDISE"]) == st.session_state.udise and row["Status"] != "Inactive":
            devices.append(row["Device Name"])
            school_name = row["School"]
    st.session_state.devices = devices
    st.session_state.school = school_name
    st.session_state.selected_device = None
    st.session_state.uploaded_image = None
    st.session_state.serial_number = ""

# Step 2: Show school + devices
if st.session_state.school:
    st.write(f"**School:** {st.session_state.school}")
    if st.session_state.devices:
        selected_device = st.selectbox(
            "Select Device",
            st.session_state.devices,
            index=st.session_state.devices.index(st.session_state.selected_device)
            if st.session_state.selected_device in st.session_state.devices else 0
        )
        st.session_state.selected_device = selected_device

        # Step 3: Upload image for serial (optional)
        uploaded_file = st.file_uploader("Upload Image of Serial (optional)", type=["jpg", "png"])
        if uploaded_file:
            st.session_state.uploaded_image = uploaded_file
            image = Image.open(uploaded_file)
            st.image(image, caption="Uploaded Image", width=200)

            # Tesseract OCR
            text = pytesseract.image_to_string(image)
            st.session_state.serial_number = text.strip()

        # Step 4: Enter Serial manually
        serial_input = st.text_input("Serial Number", st.session_state.serial_number or "")
        st.session_state.serial_number = serial_input.strip()

        # Step 5: Enter Email
        email_input = st.text_input("Enter Your Email", st.session_state.user_email or "")
        st.session_state.user_email = email_input.strip()

        # Step 6: Submit serial
        if st.button("Submit"):
            if not st.session_state.serial_number:
                st.warning("Please enter or extract serial number")
            elif not st.session_state.user_email:
                st.warning("Please enter your email")
            else:
                # Check duplicate
                existing = sheet_serials.get_all_records()
                duplicate = False
                for row in existing:
                    if (str(row["UDISE"]) == st.session_state.udise
                        and row["Device Name"] == st.session_state.selected_device):
                        duplicate = True
                        break
                if duplicate:
                    st.error("Serial already submitted for this device")
                else:
                    sheet_serials.append_row([
                        st.session_state.udise,
                        st.session_state.school,
                        st.session_state.selected_device,
                        st.session_state.serial_number,
                        st.session_state.user_email
                    ])
                    st.success(f"Serial '{st.session_state.serial_number}' saved for {st.session_state.selected_device}")
                    # Reset device-specific state
                    st.session_state.selected_device = None
                    st.session_state.uploaded_image = None
                    st.session_state.serial_number = ""
