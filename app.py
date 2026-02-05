import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from streamlit_zxing import st_zxing # Stable Scanner

# --- Page Config ---
st.set_page_config(page_title="Barcode Serial Capture", layout="wide")

# 1. Data Loading Logic
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
        st.error(f"Failed to connect to Google Sheets: {e}")
        return None, None

df_master, sheet_serials = load_master_data()

st.title("🚀 Smartboard Barcode Scanner")

if df_master is not None:
    # --- Step 1: Identify School ---
    st.markdown("### 1. Identify School")
    
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

    filtered_df = df_master.copy()
    if sel_dist != "All Districts": filtered_df = filtered_df[filtered_df['District'] == sel_dist]
    if sel_block != "All Blocks": filtered_df = filtered_df[filtered_df['Block'] == sel_block]

    filtered_df['search_display'] = filtered_df['UDISE'] + " - " + filtered_df['School']
    search_options = sorted(filtered_df['search_display'].unique())
    selected_option = st.selectbox("Type UDISE or School Name", [""] + search_options)

    if selected_option:
        selected_udise = selected_option.split(" - ")[0]
        school_row = df_master[df_master['UDISE'] == selected_udise].iloc[0]
        st.success(f"📍 {school_row['School']}")
        
        devices = df_master[df_master['UDISE'] == selected_udise]['Device Name'].tolist()
        selected_device = st.selectbox("Select Device", devices)

        st.divider()

        # --- Step 2: Barcode Scanner ---
        st.markdown("### 2. Scan Barcode")
        st.info("Center the barcode in the camera view below.")
        
        # st_zxing is a very reliable browser-based scanner
        barcode_result = st_zxing(key='scanner')
        
        if barcode_result:
            # barcode_result usually returns a dictionary or string
            scanned_value = barcode_result.get('text') if isinstance(barcode_result, dict) else barcode_result
            st.success(f"**Detected Serial:** {scanned_value}")
            st.session_state.barcode_result = scanned_value

        # --- Step 3: Submission ---
        st.divider()
        serial_final = st.text_input(
            "Final Serial Number", 
            value=st.session_state.get('barcode_result', "")
        )
        email = st.text_input("Installer Email")

        sub_col1, sub_col2 = st.columns(2)
        with sub_col1:
            if st.button("✅ Submit Data", use_container_width=True):
                if not serial_final or not email:
                    st.warning("Please scan/enter serial and email.")
                else:
                    existing = pd.DataFrame(sheet_serials.get_all_records())
                    is_dup = False
                    if not existing.empty:
                        existing.columns = [str(c).strip() for c in existing.columns]
                        is_dup = ((existing['UDISE'].astype(str) == selected_udise) & 
                                  (existing['Device Name'] == selected_device)).any()
                    
                    if is_dup:
                        st.error("Duplicate: Device already registered.")
                    else:
                        sheet_serials.append_row([selected_udise, school_row['School'], selected_device, serial_final, email])
                        st.success("Saved Successfully!")
                        st.balloons()
        
        with sub_col2:
            if st.button("🔄 Clear", use_container_width=True):
                if 'barcode_result' in st.session_state:
                    del st.session_state['barcode_result']
                st.rerun()
