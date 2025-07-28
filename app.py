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
import yagmail
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

# --- USER AUTHENTICATION DATABASE ---
conn = sqlite3.connect("users.db")
c = conn.cursor()
c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        email TEXT PRIMARY KEY,
        password TEXT NOT NULL
    )
""")
conn.commit()

def register_user(email, password):
    hashed_pw = bcrypt.hash(password)
    try:
        c.execute("INSERT INTO users (email, password) VALUES (?, ?)", (email, hashed_pw))
        conn.commit()
        return True
    except:
        return False  # agar email already exist hai

def login_user(email, password):
    c.execute("SELECT password FROM users WHERE email=?", (email,))
    row = c.fetchone()
    if row and bcrypt.verify(password, row[0]):
        return True
    return False

def reset_password(email, new_password):
    hashed_pw = bcrypt.hash(new_password)
    c.execute("UPDATE users SET password=? WHERE email=?", (hashed_pw, email))
    conn.commit()

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


# 🌈 Page Setup (MUST be first Streamlit command)
st.set_page_config(page_title="TrustHire - AI Resume Scanner", layout="wide")
theme = st.radio("Choose Theme:", ["Light", "Dark"], horizontal=True)


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
st.markdown(f"""
    <style>
    .stApp {{
        background-image: url("data:image/png;base64,{bg_base64}");
        background-size: cover;
        background-position: center;
        background-repeat: no-repeat;
        font-family: 'Segoe UI', sans-serif;
        color: white;
    }}
    .login-container {{
        width: 100%;
        max-width: 400px;
        margin: 10vh auto;
        padding: 40px;
        background-color: rgba(0, 0, 0, 0.6);
        border-radius: 12px;
        text-align: center;
    }}
    .login-title {{
        font-size: 36px;
        font-weight: bold;
        margin-bottom: 10px;
        color: white;
    }}
    .login-tagline {{
        font-size: 16px;
        color: #ccc;
        margin-bottom: 30px;
    }}
    .stTextInput input {{
        background-color: #222;
        color: white;
    }}
    .stButton>button {{
        width: 100%;
        padding: 10px;
        border-radius: 10px;
        background-color: #4B8BBE;
        color: white;
        border: none;
        font-weight: bold;
        margin-top: 20px;
    }}
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


# ✅ Authenticated - Actual App Logic Here
st.title("🎉 Welcome to TrustHire - AI Resume Scanner!")


st.markdown("### 🔐 Session Control")
if st.button("🚪 Logout"):
    st.session_state.authenticated = False
    st.rerun()


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
    lines = text.strip().split("\n")
    for line in lines[:5]:
        if line and "@" not in line and not re.search(r"\d", line):
            return line.strip()
    return "Not found"

def extract_email(text):
    match = re.search(r"[\w\.-]+@[\w\.-]+", text)
    return match.group(0) if match else "Not found"

def extract_phone(text):
    match = re.search(r"\+?\d[\d\s\-()]{8,15}", text)
    return match.group(0) if match else "Not found"

def extract_education(text):
    keywords = ["B.Tech", "B.E", "MCA", "BSc", "M.Tech", "BCA", "M.Sc", "PhD", "Bachelor", "Master", "Diploma"]
    found = [kw for kw in keywords if re.search(rf"\b{re.escape(kw)}\b", text, re.IGNORECASE)]
    return ", ".join(set(found)) if found else "Not Mentioned"

def extract_skills(text):
    keywords = ["Python", "Java", "C++", "Django", "Flask", "Pandas", "NumPy", "SQL", "HTML", "CSS", "JavaScript", "Git"]
    found = [kw for kw in keywords if re.search(rf"\b{re.escape(kw)}\b", text, re.IGNORECASE)]
    return ", ".join(found) if found else "Not Mentioned"

def extract_experience(text):
    match = re.search(r"(\d{1,2})\+?\s*(years|yrs|year|yr)", text, re.IGNORECASE)
    return int(match.group(1)) if match else None

def classify_experience(exp):
    if exp is None:
        return "Unspecified"
    elif exp <= 1:
        return "0–1 year"
    elif exp <= 3:
        return "1–3 years"
    elif exp <= 5:
        return "3–5 years"
    else:
        return "5+ years"

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


def interview_score(skills, exp):
    base = len(skills.split(", ")) * 5 if skills != "Not Mentioned" else 0
    exp_score = exp * 2 if exp else 0
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


def generate_pdf(candidate_name, role, suggestions):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(200, 10, f"Future Skills Roadmap for {candidate_name}", ln=True, align="C")
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, f"Target Role: {role}", ln=True)
    pdf.ln(10)
    for skill, demand in suggestions.items():
        pdf.multi_cell(0, 10, f"- {skill} ({demand}% Demand) - Learn here: https://www.coursera.org/search?query={skill}")
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf.output(temp_file.name)
    return temp_file.name

def generate_summary(row):
    return f"{row['Name']} has {row['Experience']} of experience in {row['Skills']}. They graduated in {row['Graduation Year']} and expect {row['Expected Salary']} salary."

# =================== FUTURE SKILLS PREDICTOR BLOCK ===================
# ===================== NEXT-LEVEL FUTURE SKILLS PREDICTOR =====================


st.markdown("## 📈 Future Skills & Career Roadmap (Next‑Gen)")

if "df" in st.session_state and not st.session_state.df.empty:
    # Select candidate
    selected_name = st.selectbox("🔍 Select Candidate for Future Skills Prediction", st.session_state.df["Name"])
    selected_row = st.session_state.df[st.session_state.df["Name"] == selected_name].iloc[0]
    candidate_name = selected_row["Name"]
    candidate_role_text = selected_row["Job Role"]

    # --- Role detection
    extracted_role, role_confidence = extract_role(candidate_role_text)

    # --- LIVE + FALLBACK skill fetcher
    def fetch_trending_skills(role):
        try:
            url = f"https://api.mockjobdata.com/trends?role={role}"
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                return res.json()
        except:
            pass
        # Fallback static
        fallback = {
            "Web Developer": {
                "WebAssembly": 77,
                "PWAs": 80,
                "AI-driven UX": 85,
                "Edge Computing": 79
            },
            "Data Scientist": {
                "Generative AI": 90,
                "MLOps": 85,
                "Big Data Analytics": 80,
                "LLMs": 88
            },
            "Software Engineer": {
                "Cloud Native Development": 87,
                "DevOps": 82,
                "GraphQL": 75,
                "AI Automation": 89
            }
        }
        return fallback.get(role, {})
    
    trending_skills = fetch_trending_skills(extracted_role)

    # --- Skill explanations
    skill_info = {
        "WebAssembly": "Boosts web app performance by running code at near-native speed.",
        "PWAs": "Progressive Web Apps combine web and mobile experience for better UX.",
        "AI-driven UX": "Improves design by integrating AI for personalization and efficiency.",
        "Edge Computing": "Brings computation closer to users for low-latency apps.",
        "Generative AI": "AI that creates text, images, or code to enhance productivity.",
        "MLOps": "Streamlines ML model deployment & lifecycle management.",
        "Big Data Analytics": "Extracts insights from massive datasets for smarter decisions.",
        "LLMs": "Large Language Models enable advanced AI-powered applications."
    }
    def get_skill_explanation(skill):
        return skill_info.get(skill, "Emerging skill for this role, highly in-demand.")

    # --- Career path predictor
    role_paths = {
        "Web Developer": ["Frontend Lead", "Full Stack Architect", "Product Engineer"],
        "Data Scientist": ["ML Engineer", "AI Researcher", "Chief Data Officer"],
        "Software Engineer": ["Senior Developer", "Tech Lead", "Product Architect"]
    }
    career_path = role_paths.get(extracted_role, ["Specialist", "Team Lead", "Domain Expert"])

    # --- Skill suggestions: exclude already present
    current_skills = [s.strip().lower() for s in selected_row["Skills"].split(",")]
    future_suggestions = {skill: demand for skill, demand in trending_skills.items() if skill.lower() not in current_skills}

    # --- Debug mode
    if st.checkbox("Show Debug Info"):
        st.write("Detected Role:", extracted_role, f"(Confidence: {role_confidence}%)")
        st.write("Trending Skills:", trending_skills)
        st.write("Current Skills:", current_skills)
        st.write("Suggested Skills:", future_suggestions)
        st.write("Predicted Career Path:", career_path)

    if future_suggestions:
        st.markdown("### 💡 Suggested Skills for the Future:")
        cols = st.columns(2)
        for i, (skill, demand) in enumerate(future_suggestions.items()):
            explanation = get_skill_explanation(skill)
            with cols[i % 2]:
                st.markdown(f"""
                <div style='padding:15px; background:rgba(255,255,255,0.05); border-radius:15px; 
                box-shadow:0 3px 8px rgba(0,0,0,0.2); margin-bottom:15px;'>
                    <h4 style='color:#4B8BBE;'>{skill} - {demand}% Demand</h4>
                    <p style='color:#ccc; font-size:13px;'>{explanation}</p>
                    <a href='https://www.coursera.org/search?query={skill}' target='_blank'>
                        <button style='background:#4B8BBE;color:white;border:none;padding:8px 12px;border-radius:8px;cursor:pointer;'>
                            Learn More
                        </button>
                    </a>
                </div>
                """, unsafe_allow_html=True)

        # --- Interactive Skill Graph
        def generate_skill_tree(skills):
            fig = go.Figure(go.Bar(
                x=list(skills.values()),
                y=list(skills.keys()),
                orientation='h',
                marker=dict(color='#4B8BBE')
            ))
            fig.update_layout(
                title="Future Skills Demand",
                xaxis_title="Market Demand (%)",
                yaxis_title="Skills",
                template="plotly_dark" if theme == "Dark" else "plotly_white"
            )
            return fig

        st.markdown("### 📊 Interactive Skill Demand Chart:")
        st.plotly_chart(generate_skill_tree(future_suggestions), use_container_width=True)

        # --- PDF Roadmap
        from fpdf import FPDF
        import tempfile
        def generate_pdf(candidate, role, skills, career_path):
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", "B", 16)
            pdf.cell(200, 10, f"Future Skills Roadmap for {candidate}", ln=True, align="C")
            pdf.set_font("Arial", size=12)
            pdf.cell(200, 10, f"Target Role: {role}", ln=True)
            pdf.ln(10)
            for skill, demand in skills.items():
                pdf.multi_cell(0, 10, f"- {skill}: {demand}% demand.")
            pdf.ln(10)
            pdf.cell(200, 10, "Predicted Career Path:", ln=True)
            for step in career_path:
                pdf.multi_cell(0, 10, f"→ {step}")
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            pdf.output(temp_file.name)
            return temp_file.name

        pdf_path = generate_pdf(candidate_name, extracted_role, future_suggestions, career_path)
        with open(pdf_path, "rb") as f:
            st.download_button("📥 Download Personalized Roadmap PDF", f, file_name=f"{candidate_name}_roadmap.pdf")

    else:
        st.warning("⚠️ No matching future skills found for this role.")



# =================== STREAMLIT DISPLAY ===================


def process_resumes(uploaded_files):
    rows = []

    for file in uploaded_files:
        text = extract_text_from_pdf(file)
        name = extract_name(text)
        email = extract_email(text)
        phone = extract_phone(text)
        edu = extract_education(text)
        grad = extract_graduation_year(text)
        skills = extract_skills(text)
        exp = extract_experience(text)
        exp_lvl = classify_experience(exp)
        location = extract_location(text)
        salary = extract_salary(text)
        role, role_confidence = extract_role(text)  # <-- Correct indentation
        score = interview_score(skills, exp)
        summary = generate_summary({
            "Name": name,
            "Skills": skills,
            "Experience": f"{exp} years" if exp else "Unspecified",
            "Graduation Year": grad,
            "Expected Salary": salary
        })

        rows.append({
            "Name": name,
            "Email": email,
            "Phone": phone,
            "Education": edu,
            "Graduation Year": grad,
            "Skills": skills,
            "Experience": f"{exp} years" if exp else "Unspecified",
            "Experience Level": exp_lvl,
            "Expected Salary": salary,
            "Job Role": role,  # <-- Only the role string
            "Location": location,
            "Interview Score": score,
            "Rating": get_rating(score),
            "Summary": summary,
            "Full Text": text,
            "Date Uploaded": datetime.now().strftime("%Y-%m-%d")
        })

    return pd.DataFrame(rows)



# -------------------- Upload Resumes --------------------
uploaded_files = st.file_uploader("📤 Upload Resumes (PDF)", type=["pdf"], accept_multiple_files=True)

if not uploaded_files:
    st.info("📥 Please upload resumes to begin filtering and email features.")
else:
    df = process_resumes(uploaded_files)
    df = clean_columns(df)
    df.index += 1
    st.session_state.df = df

    st.subheader("📎 Filter Resumes")
    col1, col2, col3 = st.columns(3)

    with col1:
        name_filter = st.text_input("Filter by Name")
        skill_filter = st.multiselect("Filter by Skills", options=sorted(set(", ".join(df["Skills"]).split(", "))))

    with col2:
        edu_filter = st.multiselect("Education", sorted(set(df["Education"])))
        exp_filter = st.multiselect("Experience Level", sorted(df["Experience Level"].unique()))

    with col3:
        loc_filter = st.multiselect("Location", sorted(df["Location"].unique()))
        grad_filter = st.multiselect("Graduation Year", sorted(df["Graduation Year"].unique()))
        date_filter = st.multiselect("Date Uploaded", sorted(df["Date Uploaded"].unique()))

    filtered = df.copy()
    if name_filter:
        filtered = filtered[filtered["Name"].str.contains(name_filter, case=False, na=False)]
    if skill_filter:
        filtered = filtered[filtered["Skills"].apply(lambda x: all(skill in x for skill in skill_filter))]
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

    # 👁️ Show filtered table
    if "Full Text" in filtered.columns:
        st.dataframe(filtered.drop(columns=["Full Text"]), use_container_width=True)
    else:
        st.dataframe(filtered, use_container_width=True)

    # 📥 CSV Download
    csv = filtered.drop(columns=["Full Text"], errors="ignore").to_csv(index=False).encode("utf-8")
    st.download_button(
        "📥 Download Filtered Data (CSV)",
        data=csv,
        file_name="filtered_resumes.csv",
        mime="text/csv",
        key="filtered_csv_download"
    )

    # 📥 JSON Download
    json_data = filtered.drop(columns=["Full Text"], errors="ignore").to_json(orient="records", indent=2)
    st.download_button(
        label="🧾 Download Filtered Data (JSON)",
        data=json_data,
        file_name="filtered_resumes.json",
        mime="application/json",
        key="filtered_json_download"
    )
# -------------------- Future Skills Predictor (Smart + Debug Info) --------------------
st.markdown("## 📈 Future Skills Predictor")

if "df" in st.session_state and not st.session_state.df.empty:
    # Select candidate
    selected_name = st.selectbox(
    "🔍 Select Candidate for Future Skills Prediction",
    st.session_state.df["Name"],
    key="future_skills_selectbox"
    )
    selected_row = st.session_state.df[st.session_state.df["Name"] == selected_name].iloc[0]
    candidate_name = selected_row["Name"]
    candidate_role_text = selected_row["Job Role"]

    # Extract role with confidence
    extracted_role, role_confidence = extract_role(candidate_role_text)

    # Get trending skills with matched role
    trending_skills, matched_role, match_confidence = fetch_trending_skills_from_api(extracted_role)

    # Normalize skills for comparison
    current_skills = [s.strip().lower() for s in selected_row["Skills"].split(",")]
    future_suggestions = {skill: demand for skill, demand in trending_skills.items() if skill.lower() not in current_skills}

    # Debug mode toggle
    if st.checkbox("Show Debug Info", key="future_skills_debug"):
        st.write("Detected Role from Resume:", extracted_role, f"(Confidence: {role_confidence}%)")
        st.write("Matched Role for Trending Skills:", matched_role, f"(Confidence: {match_confidence}%)")
        st.write("Trending Skills for this Role:", trending_skills)
        st.write("Current Skills:", current_skills)
        st.write("Suggested Skills:", future_suggestions)

    if future_suggestions:
        st.markdown("### 💡 Suggested Skills for the Future:")
        cols = st.columns(2)
        for i, (skill, demand) in enumerate(future_suggestions.items()):
            with cols[i % 2]:
                st.markdown(f"""
                <div style='padding:15px; background:rgba(255,255,255,0.05); border-radius:15px; 
                box-shadow:0 3px 8px rgba(0,0,0,0.2); margin-bottom:15px;'>
                    <h4 style='color:#4B8BBE;'>{skill}</h4>
                    <div style='margin:8px 0;'>
                        <div style='background:#dee2e6; border-radius:10px; height:20px;'>
                            <div style='width:{demand}%; background:#4B8BBE; height:20px; border-radius:10px;'></div>
                        </div>
                        <p style='color:#ccc; font-size:12px; margin-top:4px;'>{demand}% Demand in {matched_role or extracted_role}</p>
                    </div>
                    <a href='https://www.coursera.org/search?query={skill}' target='_blank'>
                        <button style='background:#4B8BBE;color:white;border:none;padding:8px 12px;border-radius:8px;cursor:pointer;'>
                            Learn More
                        </button>
                    </a>
                </div>
                """, unsafe_allow_html=True)

        # 📥 Download Roadmap PDF
        pdf_path = generate_pdf(candidate_name, matched_role or extracted_role, future_suggestions)
        with open(pdf_path, "rb") as f:
            st.download_button("📥 Download Personalized Roadmap PDF", f, file_name="Future_Skills_Roadmap.pdf")

    else:
        st.warning("⚠️ No matching future skills found. Try updating role extraction or adding more skills to resume.")
    # -------------------- Email Section --------------------
    EMAIL_SENDER = "your_email@gmail.com"
    EMAIL_PASSWORD = "your_app_password"  # use your Gmail App Password

    def generate_email_html(name, role, date, time):
        return f"""
        <html><body style='font-family: Arial;'>
        <h2 style='color: green;'>🎉 Interview Invitation</h2>
        <p>Hello <b>{name}</b>,</p>
        <p>You are shortlisted for the <b>{role}</b> role.</p>
        <p><b>Date:</b> {date}<br><b>Time:</b> {time}</p>
        <p>Best of luck!<br><i>- TrustHire Team</i></p>
        </body></html>"""

    def send_batch_emails(df, selected_names, date, time):
        import yagmail
        yag = yagmail.SMTP(EMAIL_SENDER, EMAIL_PASSWORD)
        for _, row in df[df['Name'].isin(selected_names)].iterrows():
            name = row["Name"]
            email = row["Email"]
            role = row["Job Role"]
            html = generate_email_html(name, role, date, time)
            try:
                yag.send(to=email, subject=f"Interview Invitation for {role}", contents=html)
                st.success(f"✅ Sent to {name} ({email})")
            except Exception as e:
                st.error(f"❌ Failed for {email}: {e}")

    st.markdown("## 📧 Send Interview Emails")
    selected_names = st.multiselect("👥 Select Candidates", filtered["Name"].unique())
    interview_date = st.date_input("📅 Interview Date", value=datetime.now())
    interview_time = st.time_input("⏰ Time", value=datetime.now().time())

    if st.button("📨 Send Emails"):
        if selected_names:
            send_batch_emails(filtered, selected_names, interview_date.strftime('%d %B %Y'), interview_time.strftime('%I:%M %p'))
        else:
            st.warning("⚠️ Select at least one candidate.")



# 👁️ Resume Viewer
if "df" in st.session_state and not st.session_state.df.empty:
    df = st.session_state.df
    name_lookup = st.text_input("🔎 Enter Candidate Name to View Resume & Summary")

    if name_lookup:
        match = df[df["Name"].str.contains(name_lookup, case=False, na=False)]
        if not match.empty:
            for _, row in match.iterrows():
                st.markdown(f"### 📌 Resume: {row['Name']} {row.get('Rating', '')}")
                st.markdown(f"**Summary:** {row.get('Summary', 'No summary available.')}")

                st.text_area("📝 Full Resume Text", row.get("Full Text", ""), height=200)

                # 🗂 Show PDF Viewer
                resume_file = row.get("Resume File", None)
                if resume_file:
                    b64_pdf = base64.b64encode(resume_file).decode("utf-8")
                    pdf_display = f'<iframe src="data:application/pdf;base64,{b64_pdf}" width="700" height="500" type="application/pdf"></iframe>'
                    st.markdown("📄 **Resume Preview**")
                    st.markdown(pdf_display, unsafe_allow_html=True)

                # 📥 Download button
                st.download_button(
                    "📥 Download Resume Text",
                    data=row.get("Full Text", "").encode(),
                    file_name=f"{row['Name']}_resume.txt",
                    mime="text/plain",
                    key=f"download_resume_{row['Name']}"
                )
        else:
            st.error("No matching candidate found.")

# 🧠 Resume Ranking by Job Role Fit
st.subheader("🎯 Resume Ranking by Job Role Fit")

job_roles = {
    "Data Scientist": ["Python", "Pandas", "NumPy", "Machine Learning", "SQL"],
    "Backend Developer": ["Python", "Django", "Flask", "SQL", "Git"],
    "Frontend Developer": ["HTML", "CSS", "JavaScript", "React", "Git"],
    "ML Engineer": ["Python", "TensorFlow", "Keras", "ML", "Data Preprocessing"],
    "Software Engineer": ["Java", "C++", "Git", "SQL", "Problem Solving"]
}

selected_role = st.selectbox("Select Job Role to Match", list(job_roles.keys()))

if selected_role and "df" in st.session_state and not st.session_state.df.empty:
    role_skills = job_roles[selected_role]
    result_df = st.session_state.df.copy()

    def match_score(resume_skills):
        if resume_skills == "Not Mentioned":
            return 0, []
        skill_list = [s.strip().lower() for s in resume_skills.split(",")]
        matches = [s for s in role_skills if s.lower() in skill_list]
        score = int((len(matches) / len(role_skills)) * 100)
        return score, matches

    result_df[["Match %", "Matched Skills"]] = result_df["Skills"].apply(
        lambda s: pd.Series(match_score(s))
    )

    ranked = result_df.sort_values(by="Match %", ascending=False)

    # Handle missing columns safely
    display_cols = ["Name", "Skills", "Matched Skills", "Match %"]
    for col in ["Experience", "Education"]:
        if col in ranked.columns:
            display_cols.append(col)

    st.markdown(f"### 📋 Ranked Candidates for Role: `{selected_role}`")
    st.dataframe(ranked[display_cols].head(5), use_container_width=True)


            

    # 🧠 Chatbot

# 🧠 Chatbot



# 🌟 Enhanced Chatbot UI with Better Layouts
st.markdown("""
<style>
.chat-container {
    background: rgba(255, 255, 255, 0.05);
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 20px;
    max-height: 500px;
    overflow-y: auto;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}
.user-message {
    background: linear-gradient(135deg, #4B8BBE, #306998);
    color: white;
    padding: 12px 16px;
    border-radius: 18px 18px 0 18px;
    margin: 10px 0;
    max-width: 80%;
    margin-left: auto;
    word-wrap: break-word;
    font-size: 15px;
}
.bot-message {
    background: rgba(40, 40, 40, 0.8);
    color: white;
    padding: 12px 16px;
    border-radius: 18px 18px 18px 0;
    margin: 10px 0;
    max-width: 80%;
    margin-right: auto;
    word-wrap: break-word;
    font-size: 15px;
}
.data-table {
    width: 100%;
    border-collapse: collapse;
    margin: 10px 0;
    font-size: 14px;
}
.data-table th {
    background-color: #4B8BBE;
    color: white;
    padding: 10px;
    text-align: left;
}
.data-table td {
    padding: 10px;
    border-bottom: 1px solid #444;
}
.data-table tr:nth-child(even) {
    background-color: rgba(255, 255, 255, 0.05);
}
.suggested-question {
    margin: 5px;
    padding: 10px 15px;
    border-radius: 25px;
    background: rgba(74, 144, 226, 0.2);
    color: white;
    border: 1px solid #4B8BBE;
    cursor: pointer;
    transition: all 0.3s;
    font-size: 14px;
    text-align: center;
}
.suggested-question:hover {
    background: rgba(74, 144, 226, 0.4);
    transform: translateY(-2px);
}
.clear-btn {
    background: #FF4B4B !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 10px 20px !important;
    font-weight: bold !important;
}
.chat-input {
    background: rgba(255, 255, 255, 0.1);
    border-radius: 8px;
    padding: 12px;
    border: 1px solid #444;
}
</style>
""", unsafe_allow_html=True)
# Chatbot Header with improved layout
col1, col2 = st.columns([1, 8])
with col1:
    st.image("https://cdn-icons-png.flaticon.com/512/4712/4712027.png", width=60)
with col2:
    st.subheader("Resume Query Assistant")
    st.caption("Ask about candidates' skills, experience, or education")

# Suggested Questions with better layout
st.markdown("**Quick queries:**")
suggested_questions = [
    "Python developers",
    "3-5 years experience",
    "Data scientists",
    "SQL skills",
    "Recent graduates"
]

cols = st.columns(5)
for i, question in enumerate(suggested_questions):
    with cols[i % 5]:
        if st.button(question, key=f"suggest_q_{i}"):
            st.session_state.last_question = question
            st.rerun()

# Text Input with improved styling
question = st.text_input(
    "Type your question about candidates...",
    value=st.session_state.get('last_question', ''),
    key="chat_input",
    placeholder="e.g. 'Show me Java developers with 5+ years experience'"
)

# Enhanced show function with error handling
def show(df_filtered, cols):
    try:
        if df_filtered.empty:
            return "No matching candidates found."
            
        # Verify columns exist in dataframe
        available_cols = [col for col in cols if col in df_filtered.columns]
        if not available_cols:
            return "Requested data not available."
            
        if len(available_cols) == 1:
            return "\n".join([f"• {row[available_cols[0]]}" for _, row in df_filtered[available_cols].iterrows()])
        else:
            # Create HTML table for better formatting
            table_html = f"""
            <table class="data-table">
                <tr>
                    {''.join(f'<th>{col}</th>' for col in available_cols)}
                </tr>
                {''.join(
                    f'<tr>{"".join(f"<td>{row[col]}</td>" for col in available_cols)}</tr>'
                    for _, row in df_filtered[available_cols].iterrows()
                )}
            </table>
            """
            return table_html
    except Exception as e:
        return f"Error displaying results: {str(e)}"

# Process question with proper error handling
# Process question with proper error handling
if question and question != st.session_state.get('last_processed_question', ''):
    st.session_state.last_processed_question = question
    st.session_state.chat_history.append(("You", question))
    
    try:
        q = question.lower()
        df = st.session_state.df
        
        # Skill-based
        if "python" in q and "django" in q:
            answer = show(df[df["Skills"].str.contains("python", case=False) & 
                         df["Skills"].str.contains("django", case=False)], 
                        ["Name", "Skills"])
        elif "python" in q:
            answer = show(df[df["Skills"].str.contains("python", case=False)], 
                        ["Name", "Skills"])
        elif "django" in q:
            answer = show(df[df["Skills"].str.contains("django", case=False)], 
                        ["Name", "Skills"])
        elif "flask" in q:
            answer = show(df[df["Skills"].str.contains("flask", case=False)], 
                        ["Name", "Skills"])
        elif "machine learning" in q:
            answer = show(df[df["Skills"].str.contains("machine learning", case=False)], 
                        ["Name", "Skills"])
        elif "sql" in q:
            answer = show(df[df["Skills"].str.contains("sql", case=False)], 
                        ["Name", "Skills"])
        elif "power bi" in q:
            answer = show(df[df["Skills"].str.contains("power bi", case=False)], 
                        ["Name", "Skills"])
        elif "tensorflow" in q and "keras" in q:
            answer = show(df[df["Skills"].str.contains("tensorflow", case=False) & 
                             df["Skills"].str.contains("keras", case=False)], 
                        ["Name", "Skills"])
        elif "html" in q:
            answer = show(df[df["Skills"].str.contains("html", case=False)], 
                        ["Name", "Skills"])
        elif "visualization" in q:
            answer = show(df[df["Skills"].str.contains("visualization|power bi|matplotlib|seaborn", case=False)], 
                        ["Name", "Skills"])

        # Education
        elif "b.tech" in q:
            answer = show(df[df["Education"].str.contains("b.tech", case=False)], 
                        ["Name", "Education"])
        elif "diploma" in q:
            answer = show(df[df["Education"].str.contains("diploma", case=False)], 
                        ["Name", "Education"])
        elif "m.sc" in q:
            answer = show(df[df["Education"].str.contains("m.sc", case=False)], 
                        ["Name", "Education"])
        elif "graduated in 2022" in q:
            answer = show(df[df["Graduation Year"] == "2022"], 
                        ["Name", "Graduation Year"])
        elif "education not mentioned" in q:
            answer = show(df[df["Education"] == "No"], 
                        ["Name", "Education"])
        elif "bachelor" in q:
            answer = show(df[df["Education"].str.contains("bachelor", case=False)], 
                        ["Name", "Education"])
        elif "after 2020" in q:
            answer = show(df[df["Graduation Year"].apply(lambda x: x.isdigit() and int(x) > 2020)], 
                        ["Name", "Graduation Year"])
        elif "masters" in q:
            answer = show(df[df["Education"].str.contains("m.sc|m.tech|master", case=False)], 
                        ["Name", "Education"])
        elif "education levels" in q:
            answer = ", ".join(df["Education"].unique())
        elif "computer science" in q:
            answer = show(df[df["Education"].str.contains("computer science", case=False)], 
                        ["Name", "Education"])

        # Experience
        elif "more than 5" in q:
            answer = show(df[df["Exp Level"] == "5+ years"], 
                        ["Name", "Experience"])
        elif "0-1 year" in q:
            answer = show(df[df["Exp Level"] == "0-1 year"], 
                        ["Name", "Experience"])
        elif "3-5 years" in q:
            answer = show(df[df["Exp Level"] == "3-5 years"], 
                        ["Name", "Experience"])
        elif "unspecified experience" in q:
            answer = show(df[df["Exp Level"] == "Unspecified"], 
                        ["Name", "Experience"])
        elif "2 years experience" in q:
            answer = show(df[df["Experience"].str.contains("2", case=False)], 
                        ["Name", "Experience"])
        elif "less than 3" in q:
            answer = show(df[df["Exp Level"].isin(["0-1 year", "1-3 years"])], 
                        ["Name", "Experience"])
        elif "most experienced" in q:
            df["Years"] = df["Experience"].str.extract(r'(\d+)').astype(float)
            top_exp = df.sort_values(by="Years", ascending=False).head(3)
            answer = show(top_exp, ["Name", "Experience"])
        elif "experience and python" in q:
            answer = show(df[df["Experience"].str.contains("year", case=False) & 
                             df["Skills"].str.contains("python", case=False)], 
                        ["Name", "Experience", "Skills"])
        elif "how many resumes mention experience" in q:
            answer = str(df[df["Experience"] != "Not Mentioned"].shape[0])
        elif "invalid experience" in q:
            answer = show(df[df["Experience"].str.contains("fake|invalid", case=False)], 
                        ["Name", "Experience"])

        # Job Role and Location
        elif "software engineer" in q:
            answer = show(df[df["Job Role"].str.contains("software engineer", case=False)], 
                        ["Name", "Job Role"])
        elif "ai engineer" in q:
            answer = show(df[df["Job Role"].str.contains("ai engineer", case=False)], 
                        ["Name", "Job Role"])
        elif "data scientist" in q:
            answer = show(df[df["Job Role"].str.contains("data scientist", case=False)], 
                        ["Name", "Job Role"])
        elif "mumbai" in q:
            answer = show(df[df["Location"].str.contains("mumbai", case=False)], 
                        ["Name", "Location"])
        elif "hyderabad" in q:
            answer = show(df[df["Location"].str.contains("hyderabad", case=False)], 
                        ["Name", "Location"])
        elif "location not mentioned" in q:
            answer = show(df[df["Location"] == "Not Mentioned"], 
                        ["Name", "Location"])
        elif "backend developer" in q:
            answer = show(df[df["Job Role"].str.contains("backend", case=False)], 
                        ["Name", "Job Role"])
        elif "pune" in q:
            answer = show(df[df["Location"].str.contains("pune", case=False)], 
                        ["Name", "Location"])
        elif "list all job roles" in q:
            answer = ", ".join(df["Job Role"].unique())
        elif "delhi" in q:
            answer = str(df[df["Location"].str.contains("delhi", case=False)].shape[0]) + " resumes are from Delhi."

        # Resume Insights
        elif "highest interview score" in q:
            answer = show(df[df["Interview Score"] == df["Interview Score"].max()], 
                        ["Name", "Interview Score"])
        elif "most number of skills" in q:
            df["Skill Count"] = df["Skills"].apply(lambda x: len(x.split(",")))
            answer = show(df[df["Skill Count"] == df["Skill Count"].max()], 
                        ["Name", "Skills"])
        elif "summary of best" in q:
            best = df[df["Interview Score"] == df["Interview Score"].max()]
            answer = best["Summary"].values[0]
        elif "least experience" in q:
            answer = show(df[df["Exp Level"] == "0-1 year"], 
                        ["Name", "Experience"])
        elif "over ₹100 lpa" in q:
            answer = show(df[df["Expected Salary"].str.contains("100", case=False)], 
                        ["Name", "Expected Salary"])
        elif "didn't mention salary" in q or "not mention salary" in q:
            answer = show(df[df["Expected Salary"] == "Not Mentioned"], 
                        ["Name", "Expected Salary"])
        elif "contact number" in q:
            answer = str(df[df["Phone"] != "Not found"].shape[0]) + " resumes have phone numbers."
        elif "john doe" in q:
            answer = show(df[df["Name"].str.contains("john doe", case=False)], 
                        df.columns.drop("Full Text"))
        elif "aditi sharma" in q:
            answer = "Use the candidate name box to preview and download Aditi Sharma's resume."
        elif "data analyst" in q:
            answer = show(df[df["Job Role"].str.contains("data analyst", case=False)], 
                        ["Name", "Job Role"])

        else:
            answer = "I can help with skills, experience, education or location queries. Try being more specific."

    except Exception as e:
        answer = f"Error processing your question: {str(e)}"
    
    st.session_state.chat_history.append(("Bot", answer))
    st.rerun()
    
#Display Chat History
with st.container():
    st.markdown('<div class="chat-container">', unsafe_allow_html=True)
    for sender, msg in st.session_state.chat_history:
        if sender == "🧑 You":
            st.markdown(f'<div class="user-message"><b>{sender}:</b> {msg}</div>', unsafe_allow_html=True)
        else:
            if "Name |" in msg:  # Table detection
                st.markdown(f'<div class="bot-message"><b>{sender}:</b></div>', unsafe_allow_html=True)
                st.markdown(msg)
            else:
                st.markdown(f'<div class="bot-message"><b>{sender}:</b> {msg}</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)


# Clear Chat Button with Confirmation
if st.button("🗑️ Clear Chat History", key="clear_chat"):
    st.session_state.chat_history = []
    st.session_state.last_question = ""
    st.session_state.last_processed_question = ""
    st.session_state.voice_text = ""
    st.rerun()




# 🔈 Final Voice Summary Section (Modern Layout with Language Toggle)
if "df" in st.session_state and not st.session_state.df.empty:
    df = st.session_state.df

    st.markdown("""<style>
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
    </style>""", unsafe_allow_html=True)

    st.subheader("🎤 Voice Summary of Best Resume")

    top = df.loc[df["Interview Score"].idxmax()]
    name = top["Name"]
    skills = top["Skills"]
    edu = top["Education"]
    exp = top.get("Experience Level", "Unspecified")
    loc = top["Location"]
    salary = top["Expected Salary"]
    score = top["Interview Score"]

    eng_summary = (
        f"Candidate {name} has skills in {skills} and completed education in {edu}. "
        f"Experience level is {exp}, based in {loc}, with an expected salary of {salary}. "
        f"Their interview score is {score}."
    )

    # 🌐 Language toggle
    lang = st.radio("🌐 Select language for voice output:", ["English", "Hindi"], horizontal=True)

    try:
        final_summary = eng_summary
        if lang == "Hindi":
            from googletrans import Translator
            translator = Translator()
            final_summary = translator.translate(eng_summary, dest="hi").text
    except Exception as e:
        final_summary = eng_summary
        st.warning("⚠️ Translation failed, using English summary.")

    st.markdown('<div class="summary-box">', unsafe_allow_html=True)
    st.markdown('<div class="summary-header">📜 Resume Summary</div>', unsafe_allow_html=True)
    st.text_area("Summary", value=final_summary, height=180, label_visibility="collapsed")
    st.markdown('</div>', unsafe_allow_html=True)

    # 🎧 In-browser Voice Playback
    def speak_text(text, lang_code):
        tts = gTTS(text, lang=lang_code)
        mp3_fp = BytesIO()
        tts.write_to_fp(mp3_fp)
        mp3_fp.seek(0)
        b64_audio = base64.b64encode(mp3_fp.read()).decode()
        st.markdown(f"""
        <audio controls autoplay>
            <source src="data:audio/mp3;base64,{b64_audio}" type="audio/mp3">
        </audio>
        """, unsafe_allow_html=True)

    if st.button("🔊 Read Resume Summary"):
        lang_code = "hi" if lang == "Hindi" else "en"
        speak_text(final_summary, lang_code)

    # 💾 Download summary
    st.download_button(
        "🗅️ Download Summary",
        data=final_summary.encode("utf-8"),
        file_name=f"{name}_summary_{lang.lower()}.txt",
        use_container_width=True
    )
