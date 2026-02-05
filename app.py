import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from PIL import Image, ImageOps, ImageEnhance
import pytesseract
from streamlit_cropper import st_cropper

# --- 1. Page Config ---
st.set_page_config(page_title="Easy OCR Capture", layout="wide")

st.markdown("""
    <style>
    .stApp { max-width: 100%; padding: 0px; }
    /* Make buttons huge for field workers */
    .stButton>button { 
        width: 100%; 
        height: 4em; 
        font-size: 20px !important; 
        font-weight: bold; 
        border-radius: 15px; 
        background-color: #28a745; 
        color: white; 
    }
    /* Style the file uploader */
    div[data-testid="stFileUploader"] { border: 2px dashed #28a745; border-radius: 10px; padding: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. Robust Data Loading ---
@st.cache_resource
def get_client():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_info = st.secrets["gcp_service_account"]
        credentials = Credentials.from_service_account_info(creds_info, scopes=scopes)
        client = gspread.authorize(credentials)
        client.set_timeout(120)
        return client
    except Exception as e:
        st.error(f"Auth Error: {e}")
        return None

@st.cache_data(ttl=3600)
def load_data():
    client = get_client()
    if client:
        try:
            ss = client.open("School_Master_Serial_Number_Capture")
            df = pd.DataFrame(ss.worksheet("school_master").get_all_records())
            df['UDISE'] = df['UDISE'].astype(str)
            return df
        except Exception as e:
            st.error(f"Quota Error: {e}")
    return None

df_master = load_data()

# --- 3. App UI ---
st.title("📟 Easy-Snap OCR")

if df_master is not None:
    # --- Step 1: School Selection (District/Block) ---
    col1, col2 = st.columns(2)
    with col1:
        sel_dist = st.selectbox("1. District", ["All"] + sorted(df_master['District'].unique()))
    with col2:
        blocks = ["All"]
        if sel_dist != "All":
            blocks = sorted(df_master[df_master['District'] == sel_dist]['Block'].unique())
        sel_block = st.selectbox("2. Block", blocks)

    f_df = df_master.copy()
    if sel_dist != "All": f_df = f_df[f_df['District'] == sel_dist]
    if sel_block != "All": f_df = f_df[f_df['Block'] == sel_block]

    f_df['search'] = f_df['UDISE'] + " - " + f_df['School']
    selected_option = st.selectbox("3. Find School", [""] + sorted(f_df['search'].unique()))

    if selected_option:
        udise = selected_option.split(" - ")[0]
        school_data = df_master[df_master['UDISE'] == udise].iloc[0]
        device = st.selectbox("4. Device", df_master[df_master['UDISE'] == udise]['Device Name'].tolist())

        st.divider()
        
        # --- Step 2: Simplified Snapping ---
        st.markdown("### 📸 Take Photo")
        img_file = st.file_uploader("Capture Side Panel", type=['jpg', 'jpeg', 'png'])

        if img_file:
            raw_img = Image.open(img_file)
            
            st.markdown("### ✂️ Center the Serial Number")
            st.info("Move the box over the text. Don't worry about the size; it's set to a wide horizontal strip for you.")
            
            # FIXED ASPECT RATIO: Makes it easy to just slide the box over the text
            # Users don't have to fight with the corners.
            cropped = st_cropper(
                raw_img, 
                realtime_update=True, 
                box_color='#00FF00', 
                aspect_ratio=(5, 1) # Forced long horizontal shape
            )
            
            # --- Auto-Clarity Engine ---
            # 1. Zoom in
            w, h = cropped.size
            zoom_img = cropped.resize((w*3, h*3), Image.Resampling.LANCZOS)
            
            # 2. Binarize
            proc = ImageOps.grayscale(zoom_img)
            proc = ImageEnhance.Contrast(proc).enhance(5.0)
            
            # 3. Dynamic Clarity Slider
            threshold = st.slider("Adjust until text is dark black", 50, 220, 140)
            proc = proc.point(lambda x: 0 if x < threshold else 255, '1')
            
            st.image(proc, caption="What the AI sees", use_container_width=True)

            if st.button("🚀 READ SERIAL NOW"):
                with st.spinner("Processing..."):
                    # OEM 3 = Standard Tesseract, PSM 7 = Single Line of Text
                    custom_config = r'--oem 3 --psm 7'
                    text_out = pytesseract.image_to_string(proc, config=custom_config)
                    
                    # Auto-clean common noise
                    extracted = text_out.replace("S/N:", "").replace("SN:", "").replace("Serial", "").strip()
                    # Remove non-alphanumeric noise at start/end
                    extracted = ''.join(e for e in extracted if e.isalnum())
                    
                    st.session_state.result = extracted
                    st.success(f"Extracted: {extracted}")

        # --- Step 3: Submission ---
        st.divider()
        final_serial = st.text_input("Verified Serial", value=st.session_state.get('result', ""))
        email = st.text_input("Your Email")

        if st.button("✅ SAVE TO GOOGLE SHEET"):
            if final_serial and email:
                try:
                    client = get_client()
                    ss = client.open("School_Master_Serial_Number_Capture")
                    sheet = ss.worksheet("smartboard_serials")
                    sheet.append_row([
                        school_data['District'], school_data['Block'], udise, 
                        school_data['School'], device, final_serial, email
                    ])
                    st.success("Saved Successfully!")
                    st.balloons()
                    if 'result' in st.session_state: del st.session_state['result']
                except Exception as e:
                    st.error(f"Error: {e}")
            else:
                st.warning("Please verify the serial and enter email.")
