import streamlit as st
import pandas as pd
import pytesseract
from gtts import gTTS
from io import BytesIO
import re
import fitz  # PyMuPDF
from pdf2image import convert_from_bytes
from fuzzywuzzy import process
from googletrans import Translator
from PIL import Image
import base64
from datetime import datetime
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
from streamlit_webrtc import webrtc_streamer, WebRtcMode
import speech_recognition as sr
import av
import numpy as np
import threading
from streamlit_webrtc import AudioProcessorBase
import sqlite3
import pyttsx3
import random
import webbrowser
import tempfile
from fpdf import FPDF
from passlib.hash import bcrypt   
import random, string  
import requests
import plotly.graph_objects as go
import os

# 🌈 Page Setup (MUST be first Streamlit command)
st.set_page_config(page_title="TrustHire - AI Resume Scanner", layout="wide")

# ------------------- PASTE CSS HERE -------------------
st.markdown("""
<style>
/* Top Navigation Radio Buttons - Button Style */
div[role="radiogroup"] {
    display: flex !important;
    justify-content: center !important;
    gap: 12px !important;
}

div[role="radiogroup"] label {
    background-color: #e0e0e0 !important;   
    color: #1f2d3d !important;             
    border-radius: 12px;
    padding: 10px 25px;
    font-weight: 600;   
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<style>
/* =======================
   Universal Light Theme
   ======================= */

/* App Background */
.stApp, body {
    background-color: #ffffff !important;
    color: #000000 !important;
    font-family: 'Segoe UI', sans-serif;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background-color: #f5f5f5 !important;
    color: #000000 !important;
}

/* Sidebar text */
section[data-testid="stSidebar"] * {
    color: #1f2d3d !important;
}

/* Cards, containers, tables */
.css-1d391kg, .css-1v3fvcr, .stBlock, .stDataFrame, .stAlert {
    background-color: #ffffff !important;
    color: #000000 !important;
    border-radius: 10px;
}

/* Buttons */
.stButton > button {
    background: linear-gradient(90deg, #5a9bd6, #4a86c5) !important;
    color: white !important;
    border-radius: 8px;
    font-weight: 600;
    height: 40px;
}

/* Navigation Radio Buttons */
div[role="radiogroup"] {
    display: flex !important;
    justify-content: center !important;
    gap: 12px !important;
}
div[role="radiogroup"] label {
    background-color: #f4f4f4 !important;
    color: #1f2d3d !important;
    border-radius: 10px;
    padding: 10px 25px;
    font-weight: 600;
    cursor: pointer;
    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    transition: all 0.2s ease;
}
div[role="radiogroup"] input:checked + label {
    background-color: #4a86c5 !important;
    color: white !important;
    box-shadow: 0 4px 12px rgba(0,0,0,0.2);
}

/* Text inputs */
.stTextInput > div > div > input {
    background-color: #ffffff !important;
    color: #000000 !important;
    border-radius: 8px;
    border: 1px solid #ccc;
    padding: 12px;
}

/* Dataframe tables */
.stDataFrame table {
    background-color: #ffffff !important;
    color: #000000 !important;
}

/* PDF iframe preview */
iframe {
    border: 1px solid #ccc;
    border-radius: 10px;
}

/* Skill Cards in future skill predictor */
.skill-card {
    background: #f8f9fa !important;
    color: #1f2d3d !important;
    padding: 20px;
    border-radius: 18px;
    box-shadow: 0 4px 15px rgba(0,0,0,0.1);
    margin-bottom: 20px;
}
.skill-title {
    color: #4a86c5 !important;
}
.demand-text {
    color: #555 !important;
}
.learn-btn {
    background-color: #4a86c5 !important;
    color: white !important;
}
</style>
""", unsafe_allow_html=True)


for key in ["df", "filtered", "chat_history", "voice_text"]:
    if key not in st.session_state:
        st.session_state[key] = pd.DataFrame() if key in ["df", "filtered"] else []


# --- USER AUTHENTICATION DATABASE ---
def get_connection():
    return sqlite3.connect("users.db", check_same_thread=False)

def create_table():
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            password TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

create_table()

def register_user(email, password):
    conn = get_connection()
    c = conn.cursor()
    hashed_pw = bcrypt.hash(password)

    try:
        c.execute("INSERT INTO users (email, password) VALUES (?, ?)", (email, hashed_pw))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False

def login_user(email, password):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT password FROM users WHERE email=?", (email,))
    row = c.fetchone()
    conn.close()

    if row and bcrypt.verify(password, row[0]):
        return True
    return False

def reset_password(email, new_password):
    conn = get_connection()
    c = conn.cursor()
    hashed_pw = bcrypt.hash(new_password)

    c.execute("UPDATE users SET password=? WHERE email=?", (hashed_pw, email))
    conn.commit()
    conn.close()


def generate_code(length=8):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

# --- Initialize Session State Variables ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "email" not in st.session_state:
    st.session_state.email = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []  # empty list for chat messages
if "last_question" not in st.session_state:
    st.session_state.last_question = ""
if "last_processed_question" not in st.session_state:
    st.session_state.last_processed_question = ""
if "voice_text" not in st.session_state:
    st.session_state.voice_text = ""
# ---- Navigation State ----
if "page" not in st.session_state:
    st.session_state.page = "Filter Resumes"




# 📍 Path Configuration
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
POPPLER_PATH = r"C:\Program Files (x86)\poppler-24.08.0\Library\bin"

# ✅ Background image as base64
def get_base64_image(image_path):
    with open(image_path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode()

bg_base64 = get_base64_image("background_image.jpg")  # Make sure the file exists in same folder


# 🌐 Translator
translator = Translator()

# 💠 Custom CSS
st.markdown("""
<style>

.stApp {
    background-color: #f4f6f9;
    font-family: 'Segoe UI', sans-serif;
    color: black;
}

/* 🔹 Center Wrapper Fix */
.main .block-container {
    max-width: 1100px;
    padding-top: 2rem;
    padding-bottom: 2rem;
}

/* 🔹 Card Container */
.login-container {
    background: white;
    padding: 35px 40px;
    border-radius: 16px;
    border: 1px solid #e0e0e0;
    box-shadow: 0 4px 20px rgba(0,0,0,0.08);
}

/* 🔹 Title */
.login-title {
    font-size: 32px;
    font-weight: 700;
    text-align: center;
    margin-bottom: 8px;
    color: black;
}

/* 🔹 Tagline */
.login-tagline {
    font-size: 17px;
    text-align: center;
    margin-bottom: 30px;
    color: #555;
}

/* 🔹 Input Fields */
.stTextInput > div > div > input {
    background-color: white;
    color: black;
    border-radius: 8px;
    border: 1px solid #ccc;
    padding: 12px;
}

/* 🔹 Button */
.stButton > button {
    width: 100%;
    padding: 12px;
    border-radius: 10px;
    background: linear-gradient(90deg, #5a9bd6, #4a86c5);
    color: white;
    border: none;
    font-weight: 600;
    margin-top: 20px;
}

</style>
""", unsafe_allow_html=True)

# 👤 Modern Auth UI
if not st.session_state.get("authenticated", False):
    st.markdown("<div class='login-container'>", unsafe_allow_html=True)
    st.markdown("<h1 class='login-title'>Welcome to TrustHire</h1>", unsafe_allow_html=True)
    st.markdown("<p class='login-tagline'>Your AI-powered resume scanner</p>", unsafe_allow_html=True)

    auth_tabs = st.tabs(["🔑 Login", "📝 Register", "🔄 Forgot Password"])

    with auth_tabs[0]:  # Login
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_pass")
        if st.button("Login", key="login_btn"):
            if login_user(email, password):
                st.session_state.authenticated = True
                st.session_state.email = email
                st.success("Login successful!")
                st.rerun()
            else:
                st.error("Invalid credentials.")

    with auth_tabs[1]:  # Register
        new_email = st.text_input("Email", key="reg_email")
        new_password = st.text_input("Password", type="password", key="reg_pass")
        if st.button("Register", key="reg_btn"):
            if register_user(new_email, new_password):
                st.session_state.authenticated = True
                st.session_state.email = new_email
                st.success("Account created! Redirecting...")
                st.rerun()
            else:
                st.error("Email already registered.")

    with auth_tabs[2]:  # Forgot Password
        reset_email = st.text_input("Email", key="reset_email")
        new_pass = st.text_input("New Password", type="password", key="reset_pass")
        if st.button("Reset Password", key="reset_btn"):
            reset_password(reset_email, new_pass)
            st.success("Password updated! Now you can log in.")

    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()
def show_dashboard():

    st.header("📊 Dashboard Overview")

    # ------------------------------
    # SAFETY CHECK
    # ------------------------------
    if "df" not in st.session_state:
        st.warning("⚠️ Please upload and process resumes first.")
        return

    df = st.session_state.df.copy()

    if df is None or df.empty:
        st.warning("⚠️ No data available.")
        return

    # ------------------------------
    # SAFE COLUMN HANDLING
    # ------------------------------
    if "Interview Score" not in df.columns:
        df["Interview Score"] = 0

    if "Skills" not in df.columns:
        df["Skills"] = ""

    if "Job Role" not in df.columns:
        df["Job Role"] = "Unknown"

    if "Name" not in df.columns:
        df["Name"] = "Candidate"

    df["Interview Score"] = pd.to_numeric(
        df["Interview Score"],
        errors="coerce"
    ).fillna(0)

    # ------------------------------
    # KPI CALCULATIONS
    # ------------------------------
    total_candidates = len(df)
    avg_score = round(df["Interview Score"].mean(), 1)
    shortlisted = len(df[df["Interview Score"] >= 70])

    try:
        top_candidate = df.loc[
            df["Interview Score"].idxmax()
        ]["Name"]
    except:
        top_candidate = "N/A"

    # ------------------------------
    # KPI CARDS
    # ------------------------------
    col1, col2, col3, col4 = st.columns(4)

    col1.metric("👥 Total Candidates", total_candidates)
    col2.metric("⭐ Avg Score", f"{avg_score}%")
    col3.metric("🎯 Shortlisted (70%+)", shortlisted)
    col4.metric("🏆 Top Candidate", top_candidate)

    st.markdown("---")

    # ==================================================
    # 📊 2x2 ANALYTICS GRID
    # ==================================================

    col1, col2 = st.columns(2)
    col3, col4 = st.columns(2)

    # ------------------------------
    # 1️⃣ Score Distribution
    # ------------------------------
    with col1:

        score_bins = {
            "90-100": 0,
            "70-89": 0,
            "50-69": 0,
            "Below 50": 0
        }

        for score in df["Interview Score"]:
            if score >= 90:
                score_bins["90-100"] += 1
            elif score >= 70:
                score_bins["70-89"] += 1
            elif score >= 50:
                score_bins["50-69"] += 1
            else:
                score_bins["Below 50"] += 1

        fig_bar = go.Figure(go.Bar(
            x=list(score_bins.keys()),
            y=list(score_bins.values())
        ))

        fig_bar.update_layout(
            title="📈 Match Score Distribution",
            template="plotly_white",
            paper_bgcolor="white",      # background of container
            plot_bgcolor="white",       # background of plot area
            font=dict(color="black") 

        )

        st.plotly_chart(fig_bar, use_container_width=True)

    # ------------------------------
    # 2️⃣ Score Trend
    # ------------------------------
    with col2:

        sorted_df = df.sort_values("Interview Score")

        fig_line = go.Figure()

        fig_line.add_trace(go.Scatter(
            x=sorted_df["Name"],
            y=sorted_df["Interview Score"],
            mode="lines+markers"
        ))

        fig_line.update_layout(
            title="📊 Candidate Score Trend",
            template="plotly_white",
            paper_bgcolor="white",      # background of container
            plot_bgcolor="white",       # background of plot area
            font=dict(color="black") 

        )

        st.plotly_chart(fig_line, use_container_width=True)

    # ------------------------------
    # 3️⃣ Missing Skills
    # ------------------------------
    with col3:

        all_skills = [
            "Python", "SQL", "Docker", "Kubernetes",
            "Machine Learning", "AWS", "React", "Git"
        ]

        skill_missing = {}

        for skill in all_skills:
            missing = df["Skills"].apply(
                lambda x: skill.lower() not in str(x).lower()
            ).sum()
            skill_missing[skill] = missing

        sorted_missing = sorted(
            skill_missing.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]

        skill_names = [x[0] for x in sorted_missing]
        skill_counts = [x[1] for x in sorted_missing]

        fig_skills = go.Figure(go.Bar(
            x=skill_counts,
            y=skill_names,
            orientation="h"
        ))

        fig_skills.update_layout(
            title="🔥 Top Missing Skills",
            template="plotly_white",
            paper_bgcolor="white",      # background of container
            plot_bgcolor="white",       # background of plot area
            font=dict(color="black") 

        )

        st.plotly_chart(fig_skills, use_container_width=True)

    # ------------------------------
    # 4️⃣ Role Distribution
    # ------------------------------
    with col4:

        role_counts = df["Job Role"].value_counts()

        fig_pie = go.Figure(data=[go.Pie(
            labels=role_counts.index,
            values=role_counts.values,
            hole=0.6
        )])

        fig_pie.update_layout(
            title="📊 Candidate Distribution by Role",
            template="plotly_white",
            paper_bgcolor="white",      # background of container
            plot_bgcolor="white",       # background of plot area
            font=dict(color="black") 
        )

        st.plotly_chart(fig_pie, use_container_width=True)


def show_filter_resumes():

    st.header("📂 Resume Upload & Filtering")

    # -------------------- Upload --------------------
    uploaded_files = st.file_uploader(
        "📤 Upload Resumes (PDF)",
        type=["pdf"],
        accept_multiple_files=True
    )

    if not uploaded_files:
        st.info("📥 Please upload resumes to begin filtering and email features.")
        return

    # -------------------- Process only new files --------------------
    if "processed_files" not in st.session_state:
        st.session_state.processed_files = []

    new_files = [
        f for f in uploaded_files
        if f.name not in st.session_state.processed_files
    ]

    if new_files:

        new_df = process_resumes(new_files)

        if "df" in st.session_state and not st.session_state.df.empty:
            st.session_state.df = pd.concat(
                [st.session_state.df, new_df],
                ignore_index=True
            )
        else:
            st.session_state.df = new_df

        st.session_state.processed_files.extend(
            [f.name for f in new_files]
        )

    # -------------------- Clean columns --------------------
    df = clean_columns(st.session_state.df)
    df.index += 1

    st.session_state.df = df

    # -------------------- Display --------------------
    st.success(f"✅ {len(df)} resumes processed successfully.")
    st.dataframe(df, use_container_width=True)
    
    # -------------------- Filters --------------------
    st.subheader("🔎 Filter Resumes")

    col1, col2, col3 = st.columns(3)

    with col1:
        name_filter = st.text_input("Filter by Name")

        all_skills = sorted(
            set(", ".join(df["Skills"].dropna()).split(", "))
        )
        skill_filter = st.multiselect("Filter by Skills", options=all_skills)

    with col2:
        edu_filter = st.multiselect(
            "Education",
            sorted(df["Education"].dropna().unique())
        )

        exp_filter = st.multiselect(
            "Experience Level",
            sorted(df["Experience Level"].dropna().unique())
        )

    with col3:
        loc_filter = st.multiselect(
            "Location",
            sorted(df["Location"].dropna().unique())
        )

        grad_filter = st.multiselect(
            "Graduation Year",
            sorted(df["Graduation Year"].dropna().unique())
        )

        date_filter = st.multiselect(
            "Date Uploaded",
            sorted(df["Date Uploaded"].dropna().unique())
        )

    # -------------------- Apply Filters --------------------
    filtered = df.copy()

    if name_filter:
        filtered = filtered[
            filtered["Name"].str.contains(name_filter, case=False, na=False)
        ]

    if skill_filter:
        filtered = filtered[
            filtered["Skills"].apply(
                lambda x: all(skill in x for skill in skill_filter)
            )
        ]

    if edu_filter:
        filtered = filtered[filtered["Education"].isin(edu_filter)]

    if exp_filter:
        filtered = filtered[filtered["Experience Level"].isin(exp_filter)]

    if loc_filter:
        filtered = filtered[filtered["Location"].isin(loc_filter)]

    if grad_filter:
        filtered = filtered[filtered["Graduation Year"].isin(grad_filter)]

    if date_filter:
        filtered = filtered[filtered["Date Uploaded"].isin(date_filter)]

    st.session_state.filtered = filtered

    # -------------------- Display Table --------------------
    st.subheader("📊 Filtered Results")

    display_df = filtered.drop(columns=["Full Text"], errors="ignore")
    st.dataframe(display_df, use_container_width=True)

    # -------------------- Downloads --------------------
    colA, colB = st.columns(2)

    with colA:
        csv = display_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 Download CSV",
            data=csv,
            file_name="filtered_resumes.csv",
            mime="text/csv"
        )

    with colB:

    # Create safe copy
        safe_df = display_df.copy()

    # Safe text cleaning without breaking encoding
        for col in safe_df.columns:
            if safe_df[col].dtype == "object":

                safe_df[col] = safe_df[col].apply(
                    lambda x: (
                        str(x).encode("utf-8", "ignore").decode("utf-8")
                        if pd.notna(x)
                        else ""
                    )
                )

    # Replace invalid numeric values
        safe_df = safe_df.replace([np.inf, -np.inf], None)
        safe_df = safe_df.fillna("")

    # Convert safely to JSON
        json_data = safe_df.to_json(
            orient="records",
            indent=2,
            force_ascii=False
        )

        st.download_button(
            label="🧾 Download JSON",
            data=json_data,
            file_name="filtered_resumes.json",
            mime="application/json"
        )

# ---------------- Future Skill Prediction ----------------
def show_future_skills():

    st.markdown("## 📈 Future Skills Predictor")

    # ---------- Data Source ----------
    data_source = st.session_state.get("filtered")

    if data_source is None or data_source.empty:
        data_source = st.session_state.get("df")

    if data_source is None or data_source.empty:
        st.warning("⚠️ Please upload and process resumes first.")
        return

    # ---------- Candidate Selection ----------
    selected_name = st.selectbox(
        "🔍 Select Candidate for Future Skills Prediction",
        data_source["Name"].unique()
    )

    selected_row = data_source[data_source["Name"] == selected_name].iloc[0]
    candidate_name = selected_row["Name"]
    candidate_role_text = selected_row.get("Job Role", "Software Engineer")

    # ---------- Extract Role ----------
    extracted_role, role_confidence = extract_role(candidate_role_text)
    trending_skills, matched_role, match_confidence = fetch_trending_skills_from_api(extracted_role)

    if not trending_skills:
        st.warning("⚠️ No trending skills available for this role.")
        return

    # ---------- Current Skills ----------
    current_skills = []
    if pd.notna(selected_row.get("Skills")) and selected_row["Skills"] != "Not Mentioned":
        current_skills = [
            s.strip().lower()
            for s in str(selected_row["Skills"]).split(",")
        ]

    # ---------- Future Suggestions ----------
    future_suggestions = {
        skill: demand
        for skill, demand in trending_skills.items()
        if skill.lower() not in current_skills
    }

    # ---------- Debug ----------
    if st.checkbox("Show Debug Info"):
        st.write("Detected Role:", extracted_role)
        st.write("Matched Role:", matched_role)
        st.write("Current Skills:", current_skills)
        st.write("Suggestions:", future_suggestions)

    # ---------- UI Styling ----------
    st.markdown("""
        <style>
        .skill-card {
            background: #0f172a;
            padding: 25px;
            border-radius: 18px;
            box-shadow: 0 8px 20px rgba(0,0,0,0.25);
            margin-bottom: 20px;
        }
        .skill-title {
            font-size: 22px;
            font-weight: 700;
            color: #60a5fa;
            margin-bottom: 10px;
        }
        .demand-text {
            color: #e2e8f0;
            font-size: 14px;
            margin-top: 6px;
        }
        .learn-btn {
            margin-top: 12px;
            background-color: #3b82f6;
            color: white;
            border: none;
            padding: 8px 14px;
            border-radius: 8px;
            cursor: pointer;
            text-decoration: none;
        }
        </style>
    """, unsafe_allow_html=True)

        # ---------- Display Cards ----------
    if future_suggestions:

        st.markdown("### 💡 Suggested Skills for the Future:")

        cols = st.columns(2)

        for i, (skill, demand) in enumerate(future_suggestions.items()):
            with cols[i % 2]:

                st.markdown(f"""
                    <div class="skill-card">
                        <div class="skill-title">{skill}</div>
                        <div style="background:#334155; border-radius:10px; height:18px;">
                            <div style="width:{demand}%; background:#3b82f6; height:18px; border-radius:10px;"></div>
                        </div>
                        <div class="demand-text">
                            {demand}% Demand in {matched_role or extracted_role}
                        </div>
                        <br>
                        <a href="https://www.coursera.org/search?query={skill}" target="_blank">
                            <button class="learn-btn">Learn More</button>
                        </a>
                    </div>
                """, unsafe_allow_html=True)

        # ---------- PDF Generation ----------
        pdf_path = generate_pdf(
            candidate_name,
            matched_role or extracted_role,
            future_suggestions
        )

        with open(pdf_path, "rb") as f:
            st.download_button(
                "📥 Download Personalized Roadmap PDF",
                f,
                file_name=f"{candidate_name}_roadmap.pdf",
                use_container_width=True
            )

    else:
        st.warning("⚠️ No matching future skills found. Try updating role extraction or adding more skills to resume.")

# -------------------- Email Section (Production Safe) --------------------


def send_email_with_optional_attachment(to_email, subject, html_content, attachment_path=None):

    api_key = os.getenv("SENDGRID_API_KEY", "").strip()
    sender_email = os.getenv("SENDER_EMAIL", "").strip()

    if not api_key:
        raise Exception("SENDGRID_API_KEY not found in environment variables.")

    if not sender_email:
        raise Exception("SENDER_EMAIL not found in environment variables.")

    message = Mail(
        from_email=sender_email,
        to_emails=to_email,
        subject=subject,
        html_content=html_content
    )

    # Attach Resume (Optional)
    if attachment_path and os.path.exists(attachment_path):
        with open(attachment_path, "rb") as f:
            file_data = f.read()
            encoded_file = base64.b64encode(file_data).decode()

        attachment = Attachment(
            FileContent(encoded_file),
            FileName(os.path.basename(attachment_path)),
            FileType("application/pdf"),
            Disposition("attachment")
        )

        message.attachment = attachment

    sg = SendGridAPIClient(api_key)
    response = sg.send(message)

    return response.status_code


def show_send_emails():

    st.markdown("## 📧 Send Interview Emails")

    # ---------------- Safe Data Source ----------------
    data_source = st.session_state.get("filtered")

    if data_source is None or data_source.empty:
        data_source = st.session_state.get("df")

    if data_source is None or data_source.empty:
        st.warning("⚠️ Please upload and process resumes first.")
        return

    # ---------------- Candidate Selection ----------------
    selected_names = st.multiselect(
        "👥 Select Candidates",
        data_source["Name"].unique()
    )

    interview_date = st.date_input("📅 Interview Date", value=datetime.now())
    interview_time = st.time_input("⏰ Interview Time", value=datetime.now().time())

    email_subject = st.text_input(
        "📌 Email Subject",
        "Interview Invitation - TrustHire"
    )

    email_body_template = st.text_area(
        "📄 Email Body (Use {name}, {role}, {date}, {time})",
        """Dear {name},

We are pleased to invite you for an interview for the {role} position.

📅 Date: {date}
⏰ Time: {time}

Best Regards,
TrustHire Team"""
    )

    attach_resume = st.checkbox("📎 Attach Resume PDF (if available)")

    # ---------------- Send Emails ----------------
    if st.button("📤 Send Emails"):

        if not selected_names:
            st.warning("⚠️ Please select at least one candidate.")
            return

        success_count = 0

        for name in selected_names:

            row = data_source[data_source["Name"] == name]

            if row.empty:
                continue

            email = row.iloc[0]["Email"]
            role = row.iloc[0]["Job Role"]

            if not email or email == "Not found" or "@" not in email:
                st.warning(f"⚠️ Invalid email for {name}. Skipping.")
                continue

            body = email_body_template.format(
                name=name,
                role=role,
                date=interview_date.strftime("%d-%m-%Y"),
                time=interview_time.strftime("%I:%M %p")
            )

            html_body = body.replace("\n", "<br>")

            # Optional Resume Path (if your dataframe has Resume_Path column)
            resume_path = None
            if attach_resume and "Resume_Path" in row.columns:
                resume_path = row.iloc[0].get("Resume_Path")

            try:
                status_code = send_email_with_optional_attachment(
                    to_email=email,
                    subject=email_subject,
                    html_content=html_body,
                    attachment_path=resume_path
                )

                if status_code in [200, 202]:
                    success_count += 1
                    st.success(f"✅ Email sent to {name}")
                else:
                    st.error(f"❌ Failed for {name} (Status Code: {status_code})")

            except Exception as e:
                st.error(f"❌ Failed for {name}: {str(e)}")

        st.info(f"📊 {success_count} emails sent successfully.")


# -------------------- Resume Viewer --------------------
def show_resume_viewer():

    st.markdown("## 👁️ Resume Viewer")

    if "df" not in st.session_state or st.session_state.df.empty:
        st.warning("⚠️ Please upload and process resumes first.")
        return

    df = st.session_state.df

    name_lookup = st.text_input(
        "🔎 Enter Candidate Name",
        placeholder="Type full or partial name..."
    )

    if not name_lookup:
        return

    match = df[df["Name"].str.contains(name_lookup, case=False, na=False)]

    if match.empty:
        st.error("❌ No matching candidate found.")
        return

    for _, row in match.iterrows():

        st.markdown("---")
        st.markdown(f"### 📌 {row['Name']} {row.get('Rating', '')}")

        # 🔹 Summary
        st.markdown("**🧠 Summary**")
        st.info(row.get("Summary", "No summary available."))

        # 🔹 Full Resume Text
        st.markdown("**📝 Resume Text**")
        st.text_area(
            "Full Resume Content",
            value=row.get("Full Text", ""),
            height=250,
            key=f"text_{row['Name']}"
        )

        # 🔹 PDF Preview
        resume_file = row.get("Resume_Path")

        
        if resume_file:

            st.markdown("**📄 Resume Preview**")

            try:
                if os.path.exists(resume_file):

                    with open(resume_file, "rb") as f:
                        b64_pdf = base64.b64encode(f.read()).decode("utf-8")

                    pdf_display = f"""
                        <iframe 
                            src="data:application/pdf;base64,{b64_pdf}" 
                            width="100%" 
                            height="500" 
                            type="application/pdf">
                        </iframe>
                    """

                    st.markdown(pdf_display, unsafe_allow_html=True)

                else:
                    st.warning("⚠️ Resume file not found.")

            except Exception as e:
                st.warning(f"⚠️ Unable to preview PDF: {e}")

        # 🔹 Download Button
        st.download_button(
            label="📥 Download Resume Text",
            data=row.get("Full Text", "").encode(),
            file_name=f"{row['Name']}_resume.txt",
            mime="text/plain",
            key=f"download_{row['Name']}"
        )

# -------------------- Resume Ranking by Job Role Fit --------------------
def show_resume_ranking():

    st.subheader("🎯 Resume Ranking by Job Role Fit")

    if "df" not in st.session_state or st.session_state.df.empty:
        st.warning("⚠️ Please upload and process resumes first.")
        return

    job_roles = {
        "Data Scientist": ["Python", "Pandas", "NumPy", "Machine Learning", "SQL"],
        "Backend Developer": ["Python", "Django", "Flask", "SQL", "Git"],
        "Frontend Developer": ["HTML", "CSS", "JavaScript", "React", "Git"],
        "ML Engineer": ["Python", "TensorFlow", "Keras", "Machine Learning", "Data Preprocessing"],
        "Software Engineer": ["Java", "C++", "Git", "SQL", "Problem Solving"]
    }

    selected_role = st.selectbox(
        "Select Job Role to Match",
        list(job_roles.keys())
    )

    df = st.session_state.df.copy()
    role_skills = job_roles[selected_role]

    # -------------------- Match Score Logic --------------------

    def match_score(resume_skills):

        if not resume_skills or resume_skills == "Not Mentioned":
            return 0, []

        skill_list = [s.strip().lower() for s in resume_skills.split(",")]

        matched = []
        for skill in role_skills:
            if skill.lower() in skill_list:
                matched.append(skill)

        score = int((len(matched) / len(role_skills)) * 100)
        return score, ", ".join(matched)

    df[["Match %", "Matched Skills"]] = df["Skills"].apply(
        lambda s: pd.Series(match_score(s))
    )

    ranked = df.sort_values(by="Match %", ascending=False)

    # -------------------- Display --------------------

    display_cols = ["Name", "Skills", "Matched Skills", "Match %"]

    for optional in ["Experience", "Education"]:
        if optional in ranked.columns:
            display_cols.append(optional)

    st.markdown(f"### 📋 Top Candidates for: `{selected_role}`")

    top_candidates = ranked[display_cols].head(5)

    st.dataframe(top_candidates, use_container_width=True)

    # -------------------- Visual Score Bar --------------------

    st.markdown("### 📊 Match Visualization")

    for _, row in top_candidates.iterrows():
        st.markdown(f"**{row['Name']} — {row['Match %']}% Match**")
        st.progress(int(row["Match %"]))


# -------------------- AI Resume Chatbot (Smart NLP Version) --------------------
def show_chatbot():

    import pandas as pd
    import re
    import numpy as np

    st.header("🤖 Smart Resume AI Assistant")

    # -------------------- Session State Init --------------------
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    if "last_processed_question" not in st.session_state:
        st.session_state.last_processed_question = ""

    # -------------------- Check Data --------------------
    if "df" not in st.session_state or st.session_state.df.empty:
        st.warning("Please upload resumes first.")
        return

    df = st.session_state.df.copy()

    # -------------------- Recommended Questions --------------------
    st.markdown("### 💡 Try asking:")

    sample_questions = [
        "Who has the highest interview score?",
        "Show candidates with Python and SQL skills",
        "Who has more than 3 years experience?",
        "Rank candidates by interview score",
        "Show candidates from Mumbai"
    ]

    cols = st.columns(5)
    for i, q in enumerate(sample_questions):
        if cols[i].button(q):
            st.session_state.chat_input = q

    # -------------------- Chat Input --------------------
    question = st.text_input(
        "Ask anything about the uploaded resumes:",
        key="chat_input"
    )

    # -------------------- Process Question --------------------
    if question and question != st.session_state.last_processed_question:

        st.session_state.last_processed_question = question
        st.session_state.chat_history.append(("You", question))

        try:
            q = question.lower().strip()
            answer = ""

            # -------------------- Extract Numbers --------------------
            numbers = list(map(int, re.findall(r"\d+", q)))

            # -------------------- Collect Skills Dynamically --------------------
            all_skills = set()
            if "Skills" in df.columns:
                for skills in df["Skills"].dropna():
                    for skill in str(skills).split(","):
                        all_skills.add(skill.strip().lower())

            detected_skills = [skill for skill in all_skills if skill in q]

            # -------------------- Detect Location Dynamically --------------------
            detected_locations = []
            if "Location" in df.columns:
                for loc in df["Location"].dropna().astype(str).unique():
                    if loc.lower() in q:
                        detected_locations.append(loc)

            # -------------------- Highest / Top --------------------
            if any(word in q for word in ["highest", "top", "best", "maximum"]):

                if "Interview Score" in df.columns:
                    sorted_df = df.sort_values("Interview Score", ascending=False)
                    answer = sorted_df.head(5).to_string(index=False)
                else:
                    answer = "Interview Score column not found."

            # -------------------- Lowest --------------------
            elif any(word in q for word in ["lowest", "minimum", "worst"]):

                if "Interview Score" in df.columns:
                    sorted_df = df.sort_values("Interview Score")
                    answer = sorted_df.head(5).to_string(index=False)
                else:
                    answer = "Interview Score column not found."

            # -------------------- Ranking --------------------
            elif "rank" in q or "sort" in q:

                if "Interview Score" in df.columns:
                    sorted_df = df.sort_values("Interview Score", ascending=False)
                    answer = sorted_df.to_string(index=False)
                else:
                    answer = "Interview Score column not found."

            # -------------------- Experience Comparison --------------------
            elif "experience" in q:

                if "Experience" not in df.columns:
                    answer = "Experience column not found."

                else:
                    if "more than" in q or "greater than" in q:
                        if numbers:
                            filtered = df[df["Experience"] > numbers[0]]
                            answer = filtered.to_string(index=False)
                        else:
                            answer = "Please specify years."

                    elif "less than" in q:
                        if numbers:
                            filtered = df[df["Experience"] < numbers[0]]
                            answer = filtered.to_string(index=False)
                        else:
                            answer = "Please specify years."

                    elif "between" in q and len(numbers) >= 2:
                        filtered = df[
                            (df["Experience"] >= numbers[0]) &
                            (df["Experience"] <= numbers[1])
                        ]
                        answer = filtered.to_string(index=False)

                    else:
                        answer = df[["Name", "Experience"]].to_string(index=False)

            # -------------------- Skill Filtering --------------------
            elif detected_skills:

                pattern = "|".join(map(re.escape, detected_skills))
                filtered = df[df["Skills"].str.contains(pattern, case=False, na=False)]

                if not filtered.empty:
                    answer = filtered.to_string(index=False)
                else:
                    answer = "No candidates found with that skill."

            # -------------------- Location Filtering --------------------
            elif detected_locations:

                filtered = df[df["Location"].isin(detected_locations)]
                answer = filtered.to_string(index=False)

            # -------------------- Score Queries --------------------
            elif "score" in q:

                if "Interview Score" in df.columns:
                    answer = df[["Name", "Interview Score"]].to_string(index=False)
                else:
                    answer = "Interview Score column not found."

            # -------------------- Email / Contact --------------------
            elif "email" in q or "contact" in q or "phone" in q:

                columns = ["Name"]
                for col in ["Email", "Phone"]:
                    if col in df.columns:
                        columns.append(col)

                answer = df[columns].to_string(index=False)

            # -------------------- Education --------------------
            elif "education" in q or "qualification" in q:

                if "Education" in df.columns:
                    answer = df[["Name", "Education"]].to_string(index=False)
                else:
                    answer = "Education column not found."

            # -------------------- Total Count --------------------
            elif "total" in q or "how many" in q:

                answer = f"Total candidates: {len(df)}"

            # -------------------- Default --------------------
            else:
                answer = (
                    "I can help with:\n"
                    "• Skills filtering\n"
                    "• Experience comparison\n"
                    "• Ranking candidates\n"
                    "• Interview scores\n"
                    "• Location search\n"
                    "• Contact details\n"
                    "• Education\n"
                    "• Candidate statistics\n"
                )

        except Exception as e:
            answer = f"Error occurred: {str(e)}"

        st.session_state.chat_history.append(("Bot", answer))

    # -------------------- Display Chat (Recent First Below Input) --------------------
    if st.session_state.chat_history:

        st.markdown("### 💬 Chat History")

        for sender, message in reversed(st.session_state.chat_history):
            if sender == "You":
                st.markdown(f"**🧑 You:** {message}")
            else:
                st.markdown("**🤖 Bot:**")
                st.text(message)

    # -------------------- Clear Chat --------------------
    if st.button("🧹 Clear Chat"):
        st.session_state.chat_history = []
        st.session_state.last_processed_question = ""
        st.rerun()


# -------------------- Voice Summary Function --------------------
def show_voice_summary():

    # -------------------- Check Data --------------------
    if "df" not in st.session_state or st.session_state.df.empty:
        st.warning("No resumes available for summary.")
        return

    df = st.session_state.df

    # -------------------- Styling --------------------
    st.markdown("""
    <style>
    .summary-box {
        background-color: #1e1e2f;
        padding: 1.5rem;
        border-radius: 12px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.2);
        margin-bottom: 20px;
        color: #ffffff;
    }
    .summary-header {
        font-size: 22px;
        font-weight: bold;
        color: #f39c12;
        margin-bottom: 10px;
    }
    .summary-textarea textarea {
        background-color: #2c2c3e !important;
        color: white !important;
        font-size: 15px !important;
        line-height: 1.6 !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.subheader("🎤 Voice Summary of Best Resume")

    # -------------------- Get Best Candidate --------------------
    try:

        top = df.loc[df["Interview Score"].idxmax()]

        name = str(top.get("Name", "Not Mentioned"))
        skills = str(top.get("Skills", "Not Mentioned"))
        edu = str(top.get("Education", "Not Mentioned"))
        exp = str(top.get("Experience", "Not Mentioned"))
        loc = str(top.get("Location", "Not Mentioned"))
        salary = str(top.get("Expected Salary", "Not Mentioned"))
        score = str(top.get("Interview Score", "Not Mentioned"))

    except Exception as e:
        st.error(f"Error finding best candidate: {e}")
        return

    # -------------------- English Summary --------------------
    eng_summary = (
        f"Candidate {name} has skills in {skills}. "
        f"They completed their education in {edu}. "
        f"Their experience level is {exp}. "
        f"They are located in {loc}. "
        f"The expected salary is {salary}. "
        f"The interview score is {score}."
    )

    # -------------------- Language Toggle --------------------
    lang = st.radio(
        "🌐 Select language for voice output:",
        ["English", "Hindi"],
        horizontal=True
    )

    # -------------------- Translate if Hindi --------------------
    try:

        final_summary = eng_summary

        if lang == "Hindi":

            from googletrans import Translator

            translator = Translator()

            final_summary = translator.translate(
                eng_summary,
                dest="hi"
            ).text

    except Exception:
        final_summary = eng_summary
        st.warning("⚠ Translation failed, using English summary.")

    # -------------------- Display Summary --------------------
    st.markdown('<div class="summary-box">', unsafe_allow_html=True)

    st.markdown(
        '<div class="summary-header">📜 Resume Summary</div>',
        unsafe_allow_html=True
    )

    st.text_area(
        "Summary",
        value=final_summary,
        height=180,
        label_visibility="collapsed"
    )

    st.markdown('</div>', unsafe_allow_html=True)

    # -------------------- Voice Function --------------------
    def speak_text(text, lang_code):

        try:

            tts = gTTS(text=text, lang=lang_code)

            mp3_fp = BytesIO()

            tts.write_to_fp(mp3_fp)

            mp3_fp.seek(0)

            b64_audio = base64.b64encode(
                mp3_fp.read()
            ).decode()

            st.markdown(f"""
                <audio controls autoplay>
                    <source src="data:audio/mp3;base64,{b64_audio}" type="audio/mp3">
                </audio>
            """, unsafe_allow_html=True)

        except Exception as e:

            st.error(f"Voice generation failed: {e}")

    # -------------------- Voice Button --------------------
    if st.button("🔊 Read Resume Summary"):

        lang_code = "hi" if lang == "Hindi" else "en"

        speak_text(final_summary, lang_code)

    # -------------------- Download Button --------------------
    st.download_button(

        label="🗅️ Download Summary",

        data=final_summary.encode("utf-8"),

        file_name=f"{name}_summary_{lang.lower()}.txt",

        mime="text/plain",

        use_container_width=True
    )
def clean_columns(df):
    df.dropna(axis=1, how="all", inplace=True)
    df.dropna(axis=0, how="all", inplace=True)
    return df

def extract_text_from_pdf(file):
    text = ""
    try:
        with fitz.open(stream=file.read(), filetype="pdf") as doc:
            for page in doc:
                text += page.get_text()
        if not text.strip():
            raise Exception("Empty text, switching to OCR")
    except:
        file.seek(0)
        images = convert_from_bytes(file.read(), poppler_path=POPPLER_PATH)
        for img in images:
            text += pytesseract.image_to_string(img)
    return text

def extract_name(text):
    # 🔹 Try regex pattern first
    match = re.search(r"\b[A-Z][a-z]+ [A-Z][a-z]+\b", text)

    if match:
        name = match.group(0)
        blacklist = ["Resume", "Curriculum", "Vitae", "Email", "Phone"]

        if any(b.lower() in name.lower() for b in blacklist):
            return "Not found"

        return name

    # 🔹 If regex fails, try checking first few lines
    lines = text.split("\n")

    for line in lines[:10]:
        line = line.strip()

        if re.match(r"^[A-Z][a-z]+ [A-Z][a-z]+$", line):
            return line

    return "Not found"



def extract_email(text):
    match = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)
    return match.group(0) if match else "Not Mentioned"


def extract_phone(text):
    match = re.search(r"(\+91[\-\s]?)?[6-9]\d{9}", text)
    return match.group(0) if match else "Not Mentioned"


def extract_education(text):
    patterns = [
        r"b\.?tech",
        r"b\.?e",
        r"bachelor",
        r"m\.?tech",
        r"mca",
        r"bca",
        r"m\.?sc",
        r"b\.?sc",
        r"phd",
        r"diploma"
    ]

    found = []
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            found.append(pattern.replace("\\.?", "").upper())

    return ", ".join(set(found)) if found else "Not Mentioned"

def extract_skills(text):
    keywords = [
        "Python", "Java", "C++", "Django", "Flask", "Pandas",
        "NumPy", "SQL", "HTML", "CSS", "JavaScript", "Git",
        "Machine Learning", "Deep Learning", "TensorFlow",
        "React", "Node.js", "MongoDB", "AWS", "Docker"
    ]

    found = []
    for skill in keywords:
        if re.search(rf"\b{re.escape(skill)}\b", text, re.IGNORECASE):
            found.append(skill)

    return ", ".join(found) if found else "Not Mentioned"


def extract_experience(text):
    text_lower = text.lower()

    if "fresher" in text_lower:
        return {"type": "fresher", "value": "Fresher"}

    year_match = re.search(r"(\d+)\+?\s*(year|years|yr|yrs)", text_lower)
    if year_match:
        years = int(year_match.group(1))
        return {"type": "fulltime", "value": f"{years} years"}

    month_match = re.search(r"(\d+)\s*(month|months)", text_lower)
    if month_match:
        months = int(month_match.group(1))
        return {"type": "internship", "value": f"{months} months"}

    return {"type": "fresher", "value": "Fresher"}


def classify_experience(exp_obj):
    if exp_obj["type"] == "fresher":
        return "Fresher"
    elif exp_obj["type"] == "internship":
        return "Internship"
    elif exp_obj["type"] == "fulltime":
        years = int(re.search(r"\d+", exp_obj["value"]).group())
        if years <= 1:
            return "0–1 year"
        elif years <= 3:
            return "1–3 years"
        elif years <= 5:
            return "3–5 years"
        else:
            return "5+ years"
    return "Unspecified"

def extract_graduation_year(text):
    match = re.findall(r"\b(19\d{2}|20\d{2})\b", text)
    years = [int(y) for y in match if 1980 <= int(y) <= 2030]
    return str(max(years)) if years else "No"

def extract_location(text):
    cities = ["Mumbai", "Pune", "Delhi", "Bangalore", "Hyderabad", "Noida"]
    for city in cities:
        if city.lower() in text.lower():
            return city
    return "Not Mentioned"

def extract_salary(text):
    match = re.search(r"₹?\s?\d{2,3}[,\d]*(\.\d+)?\s*(LPA|CTC|per annum|lakhs)?", text, re.IGNORECASE)
    return match.group(0).strip() if match else "Not Mentioned"

def extract_role(text):
    roles = [
        "Data Scientist", "Backend Developer", "Frontend Developer",
        "ML Engineer", "Software Engineer", "AI/ML Engineer",
        "Web Developer", "Cybersecurity Engineer", "Django Developer",
        "Full Stack Developer", "DevOps Engineer"
    ]
    best_match, score = process.extractOne(text, roles)
    return (best_match if score >= 50 else "Software Engineer", score if score >= 50 else 0)

def safe_exp_to_number(exp):
    """
    Converts experience string to numeric years.
    Returns 0 if Fresher or cannot parse.
    """
    if not exp:
        return 0
    exp = str(exp).lower()
    if "fresher" in exp:
        return 0
    num_match = re.search(r"\d+", exp)
    if num_match:
        num = int(num_match.group())
        if "month" in exp:
            return round(num / 12, 2)
        return num
    return 0

def interview_score(skills, exp):
    base = len(skills.split(", ")) * 5 if skills != "Not Mentioned" else 0
    exp_num = safe_exp_to_number(exp)
    exp_score = exp_num * 2
    return base + exp_score


def get_rating(score):
    stars = min(5, score // 10)
    return "⭐" * stars
# --- Trending Skills (Fallback if API fails) ---
local_trending_skills = {
    "Data Scientist": {"Generative AI": 90, "MLOps": 85, "Big Data Analytics": 80, "LLMs": 88},
    "Software Engineer": {"Cloud Native Development": 87, "DevOps": 82, "GraphQL": 75, "AI Automation": 89},
    "Web Developer": {"WebAssembly": 77, "PWAs": 80, "AI-driven UX": 85, "Edge Computing": 79},
    "AI/ML Engineer": {"Reinforcement Learning": 88, "AutoML": 84, "Generative AI": 91, "AI Ethics": 83},
    "Cybersecurity": {"Zero Trust Security": 88, "Cloud Security": 90, "AI Threat Detection": 85}
}

# --- Smart Trending Skills Fetcher ---
def fetch_trending_skills_from_api(role):
    try:
        # Fuzzy match role to trending skill keys
        choices = list(local_trending_skills.keys())
        match, score = process.extractOne(role, choices)
        if score >= 50:  # Only use if it's a decent match
            return local_trending_skills[match], match, score
        return {}, None, 0
    except:
        return {}, None, 0

def suggest_future_skills(current_skills, role):
    skills_data = fetch_trending_skills_from_api(role) or local_trending_skills.get(role, {})
    # Normalize resume skills
    current = [s.strip().lower() for s in current_skills.split(",")]
    # Only suggest those not already present
    return {skill: demand for skill, demand in skills_data.items() if skill.lower() not in current}


def generate_pdf(candidate, role, skills):
    pdf = FPDF()
    pdf.add_page()
    pdf.add_font("DejaVu", "", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", uni=True)
    pdf.set_font("DejaVu", "", 14)
    pdf.cell(0, 10, f"Future Skills Roadmap for {candidate}", ln=True, align="C")
    pdf.set_font("DejaVu", "", 12)
    pdf.cell(0, 10, f"Target Role: {role}", ln=True)
    pdf.ln(10)

    max_width = pdf.w - 20  # page width - margins
    for skill, demand in skills.items():
        safe_text = f"- {skill} ({demand}% Demand)"
        # agar text bahut lamba hai, break karo
        while len(safe_text) > 80:
            pdf.multi_cell(max_width, 10, safe_text[:80])
            safe_text = safe_text[80:]
        pdf.multi_cell(max_width, 10, safe_text)
    pdf.ln(10)
    pdf.multi_cell(max_width, 10, "For more details, visit Coursera and search these skills.")
    
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf.output(temp_file.name)
    return temp_file.name



def generate_summary(row):
    return f"{row['Name']} has {row['Experience']} of experience in {row['Skills']}. They graduated in {row['Graduation Year']} and expect {row['Expected Salary']} salary."

# -------------------- Resume Processing Engine --------------------
def process_resumes(uploaded_files):

    data = []

    for file in uploaded_files:

        try:

            file.seek(0)

            text = extract_text_from_pdf(file)

            name = extract_name(text)
            email = extract_email(text)
            phone = extract_phone(text)
            education = extract_education(text)
            skills = extract_skills(text)

            exp_obj = extract_experience(text)
            experience = exp_obj["value"]
            experience_level = classify_experience(exp_obj)

            grad_year = extract_graduation_year(text)
            location = extract_location(text)
            salary = extract_salary(text)

            role, role_conf = extract_role(text)

            score = interview_score(skills, experience)
            rating = get_rating(score)

            summary = generate_summary({
                "Name": name,
                "Experience": experience,
                "Skills": skills,
                "Graduation Year": grad_year,
                "Expected Salary": salary
            })

            os.makedirs("resumes", exist_ok=True)

            file_path = os.path.join("resumes", file.name)

            with open(file_path, "wb") as f:
                f.write(file.getbuffer())

            data.append({

                "Name": name,
                "Email": email,
                "Phone": phone,
                "Education": education,
                "Skills": skills,
                "Experience": experience,
                "Experience Level": experience_level,
                "Graduation Year": grad_year,
                "Location": location,
                "Expected Salary": salary,
                "Job Role": role,
                "Interview Score": score,
                "Rating": rating,
                "Summary": summary,
                "Full Text": text,
                "Resume_Path": file_path,
                "Date Uploaded": datetime.now().strftime("%Y-%m-%d")

            })

        except Exception as e:

            st.warning(f"Failed to process file: {file.name} — {e}")

    return pd.DataFrame(data)

# ✅ Authenticated - Actual App Logic Here
st.title("🎉 Welcome to TrustHire - AI Resume Scanner!")
st.markdown("<h3 style='text-align:center;'>Navigation</h3>", unsafe_allow_html=True)


page = st.radio(
    "",
    [
        "Dashboard",
        "Filter Resumes",
        "Future Skills",
        "Send Emails",
        "Candidate View",
        "Ranking",
        "Chatbot",
        "Voice Summary"
    ],
    horizontal=True
)

# ---------------- ROUTING ----------------

if page == "Dashboard":
    show_dashboard()

elif page == "Filter Resumes":
    show_filter_resumes()

elif page == "Future Skills":
    show_future_skills()

elif page == "Send Emails":
    show_send_emails()

elif page == "Candidate View":
    show_resume_viewer()

elif page == "Ranking":
    show_resume_ranking()

elif page == "Chatbot":
    show_chatbot()

elif page == "Voice Summary":
    show_voice_summary()






















