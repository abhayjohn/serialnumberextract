import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from PIL import Image, ImageOps, ImageEnhance
from pyzbar.pyzbar import decode
import os

# --- Page Config ---
st.set_page_config(page_title="Smart Scanner", layout="wide")

# 1. Data Loading
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

@st.cache_data(ttl=600)
def load_data():
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
        st.error(f"Setup Error: {e}")
        return None, None

df_master, sheet_serials = load_data()

st.title("📟 Smartboard Barcode Scanner")

if df_master is not None:
    # --- Step 1: Search & Filter (Unified) ---
    st.markdown("### 1. Find School")
    
    col1, col2 = st.columns(2)
    with col1:
        dists = sorted(df_master['District'].unique())
        sel_dist = st.selectbox("Filter District", ["All"] + dists)
    with col2:
        blocks = ["All"]
        if sel_dist != "All":
            blocks = sorted(df_master[df_master['District'] == sel_dist]['Block'].unique())
        sel_block = st.selectbox("Filter Block", blocks)

    # Filtering logic
    f_df = df_master.copy()
    if sel_dist != "All": f_df = f_df[f_df['District'] == sel_dist]
    if sel_block != "All": f_df = f_df[f_df['Block'] == sel_block]

    f_df['search_display'] = f_df['UDISE'] + " - " + f_df['School']
    search_list = sorted(f_df['search_display'].unique())
    selected_option = st.selectbox("Search School Name or UDISE", [""] + search_list)

    if selected_option:
        udise_code = selected_option.split(" - ")[0]
        school_row = df_master[df_master['UDISE'] == udise_code].iloc[0]
        st.success(f"📍 {school_row['School']}")
        
        devices = df_master[df_master['UDISE'] == udise_code]['Device Name'].tolist()
        device = st.selectbox("Select Device", devices)

        st.divider()

        # --- Step 2: Barcode Scanner ---
        st.markdown("### 2. Scan Barcode")
        
        # Use camera_input but with instruction to make it full screen
        img_file = st.camera_input("Place barcode in center of frame")
        
        scanned_val = ""
        if img_file:
            with st.spinner("Decoding..."):
                # Image Pre-processing for better clarity
                raw_img = Image.open(img_file)
                
                # 1. Grayscale
                proc_img = ImageOps.grayscale(raw_img)
                # 2. Contrast Boost (Makes black bars sharper)
                enhancer = ImageEnhance.Contrast(proc_img)
                proc_img = enhancer.enhance(2.5) 
                
                # Decode
                barcodes = decode(proc_img)
                
                if barcodes:
                    scanned_val = barcodes[0].data.decode('utf-8')
                    st.success(f"✅ Scanned: **{scanned_val}**")
                else:
                    st.error("Could not read barcode. Try again from a different distance or angle.")
                    # Show the processed image to the user for feedback
                    st.image(proc_img, caption="What the scanner sees", use_container_width=True)

        # --- Step 3: Submission ---
        st.divider()
        final_serial = st.text_input("Verified Serial", value=scanned_val)
        email = st.text_input("Installer Email")

        if st.button("✅ Submit Data", use_container_width=True):
            if not final_serial or not email:
                st.warning("Enter Serial and Email.")
            else:
                existing = pd.DataFrame(sheet_serials.get_all_records())
                is_dup = False
                if not existing.empty:
                    existing.columns = [str(c).strip() for c in existing.columns]
                    is_dup = ((existing['UDISE'].astype(str) == udise_code) & 
                              (existing['Device Name'] == device)).any()
                
                if is_dup:
                    st.error("Duplicate Entry!")
                else:
                    sheet_serials.append_row([udise_code, school_row['School'], device, final_serial, email])
                    st.success("Successfully Saved!")
                    st.balloons()
