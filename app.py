import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from streamlit_camera_qr_code import m_camera_qr_code

# --- Page Config for Mobile ---
st.set_page_config(
    page_title="Serial Barcode Capture",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 1. Data Loading Logic
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

@st.cache_data(ttl=600)
def load_master_data():
    try:
        # Pulling credentials from Streamlit Secrets
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        client = gspread.authorize(creds)
        ss = client.open("School_Master_Serial_Number_Capture")
        
        # Load School Master
        df = pd.DataFrame(ss.worksheet("school_master").get_all_records())
        df.columns = [str(c).strip() for c in df.columns]
        df['UDISE'] = df['UDISE'].astype(str)
        
        return df, ss.worksheet("smartboard_serials")
    except Exception as e:
        st.error(f"Failed to connect to Google Sheets: {e}")
        return None, None

df_master, sheet_serials = load_master_data()

# --- Main UI ---
st.title("🚀 Smartboard Barcode Scanner")

if df_master is not None:
    # --- Step 1: Search & Filter ---
    st.markdown("### 1. Identify School")
    
    # Filters stack automatically on mobile
    f_col1, f_col2 = st.columns(2)
    with f_col1:
        districts = sorted(df_master['District'].unique())
        sel_dist = st.selectbox("District", ["All Districts"] + districts)
    with f_col2:
        if sel_dist != "All Districts":
            blocks = sorted(df_master[df_master['District'] == sel_dist]['Block'].unique())
            sel_block = st.selectbox("Block", ["All Blocks"] + blocks)
        else:
            sel_block = st.selectbox("Block", ["All Blocks"], disabled=True)

    # Filter Logic
    filtered_df = df_master.copy()
    if sel_dist != "All Districts":
        filtered_df = filtered_df[filtered_df['District'] == sel_dist]
    if sel_block != "All Blocks":
        filtered_df = filtered_df[filtered_df['Block'] == sel_block]

    # Unified Search Box
    filtered_df['search_display'] = filtered_df['UDISE'] + " - " + filtered_df['School']
    search_options = sorted(filtered_df['search_display'].unique())
    selected_option = st.selectbox("Type UDISE or School Name", [""] + search_options)

    if selected_option:
        # Extract School Data
        selected_udise = selected_option.split(" - ")[0]
        school_row = df_master[df_master['UDISE'] == selected_udise].iloc[0]
        
        st.success(f"📍 {school_row['School']}")
        
        # Device Selection
        devices = df_master[df_master['UDISE'] == selected_udise]['Device Name'].tolist()
        selected_device = st.selectbox("Select Device", devices)

        st.divider()

        # --- Step 2: Barcode Scanner ---
        st.markdown("### 2. Scan Barcode")
        st.info("Point your camera at the barcode on the back of the smartboard.")
        
        # This component uses the device camera directly in the browser
        # It works for Barcodes and QR codes
        scanned_val = m_camera_qr_code(key='barcode_scanner')
        
        if scanned_val:
            st.success(f"**Scanned Value:** {scanned_val}")
            st.session_state.barcode_result = scanned_val

        # --- Step 3: Verification & Submit ---
        st.divider()
        serial_final = st.text_input(
            "Final Serial Number", 
            value=st.session_state.get('barcode_result', ""),
            help="You can manually edit if the scan was slightly off."
        )
        email = st.text_input("Installer Email Address")

        # Mobile-friendly full-width buttons
        sub_col1, sub_col2 = st.columns(2)
        
        with sub_col1:
            if st.button("✅ Submit Data", use_container_width=True):
                if not serial_final or not email:
                    st.warning("Please scan a barcode and enter your email.")
                else:
                    with st.spinner("Checking duplicates and saving..."):
                        # Duplicate check in 'smartboard_serials' sheet
                        existing = pd.DataFrame(sheet_serials.get_all_records())
                        is_dup = False
                        if not existing.empty:
                            existing.columns = [str(c).strip() for c in existing.columns]
                            is_dup = ((existing['UDISE'].astype(str) == selected_udise) & 
                                      (existing['Device Name'] == selected_device)).any()
                        
                        if is_dup:
                            st.error("Duplicate: This device already has a serial number recorded.")
                        else:
                            sheet_serials.append_row([
                                selected_udise, 
                                school_row['School'], 
                                selected_device, 
                                serial_final, 
                                email
                            ])
                            st.success("Successfully saved to Google Sheets!")
                            st.balloons()
        
        with sub_col2:
            if st.button("🔄 Clear & Restart", use_container_width=True):
                if 'barcode_result' in st.session_state:
                    del st.session_state['barcode_result']
                st.rerun()

else:
    st.warning("Please check your Google Sheet configuration and Streamlit Secrets.")
