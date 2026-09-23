import streamlit as st
import pandas as pd
import requests
import re
import time

st.set_page_config(page_title="Free Lead Profiler", page_icon="🔎", layout="wide")

st.title("🔎 Free LinkedIn Lead Profiler")
st.caption("Powered by Google Custom Search API (Free 100 queries/day — No credit card required)")

# Sidebar for credentials
with st.sidebar:
    st.header("Free API Settings")
    api_key = st.text_input(
        "Google API Key", 
        value=st.secrets.get("GOOGLE_API_KEY", ""), 
        type="password"
    )
    search_engine_id = st.text_input(
        "Search Engine ID (cx)", 
        value=st.secrets.get("SEARCH_ENGINE_ID", "")
    )
    st.markdown("""
    **How to get them for free:**
    1. [Google API Key](https://console.cloud.google.com/apis/credentials)
    2. [Programmable Search Engine ID](https://programmablesearchengine.google.com/)
    """)

def parse_metadata(item: dict) -> tuple:
    """Extracts Name, Title, and Company from Google's indexed LinkedIn snippet."""
    raw_title = item.get("title", "")
    snippet = item.get("snippet", "")
    
    # Clean LinkedIn branding
    cleaned = re.sub(r"\s*-\s*LinkedIn.*$", "", raw_title, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*\|\s*LinkedIn.*$", "", cleaned, flags=re.IGNORECASE)
    
    parts = [p.strip() for p in cleaned.split(" - ") if p.strip()]
    
    name = parts[0] if len(parts) > 0 else "N/A"
    title = parts[1] if len(parts) > 1 else "N/A"
    company = parts[2] if len(parts) > 2 else "N/A"
    
    # Handle "Title at Company" format
    if company == "N/A" and " at " in title:
        sub = title.split(" at ")
        title = sub[0].strip()
        company = sub[1].strip()
        
    return name, title, company

def extract_name_domain(email: str) -> tuple:
    local, domain = email.split("@")
    clean_domain = domain.split(".")[0]
    clean_name = re.sub(r"[._-]", " ", local).title()
    return clean_name, clean_domain

def search_lead(email: str, api_key: str, cx: str) -> dict:
    email = email.strip()
    if "@" not in email:
        return {"Email": email, "Name": "Invalid", "Title": "Invalid", "Company": "Invalid", "LinkedIn": "N/A", "Status": "Invalid Email"}

    url = "https://www.googleapis.com/customsearch/v1"
    
    # Query 1: Exact search for email associated with a LinkedIn profile
    query = f'site:linkedin.com/in/ "{email}"'
    params = {"key": api_key, "cx": cx, "q": query, "num": 1}
    
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        
        # Check for errors (e.g. quota exceeded or bad key)
        if "error" in data:
            error_msg = data["error"].get("message", "API Error")
            return {"Email": email, "Name": "N/A", "Title": "N/A", "Company": "N/A", "LinkedIn": "N/A", "Status": error_msg}

        items = data.get("items", [])
        
        # Query 2: Fallback using name & domain heuristic if exact email isn't on public bio
        if not items:
            name_guess, domain_guess = extract_name_domain(email)
            query_fb = f'site:linkedin.com/in/ "{name_guess}" "{domain_guess}"'
            params["q"] = query_fb
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            items = data.get("items", [])

        if items:
            top_hit = items[0]
            link = top_hit.get("link", "")
            name, title, company = parse_metadata(top_hit)
            return {
                "Email": email,
                "Name": name,
                "Title": title,
                "Company": company,
                "LinkedIn": link,
                "Status": "Found"
            }
        else:
            return {"Email": email, "Name": "N/A", "Title": "N/A", "Company": "N/A", "LinkedIn": "N/A", "Status": "Not Found"}

    except Exception as e:
        return {"Email": email, "Name": "N/A", "Title": "N/A", "Company": "N/A", "LinkedIn": "N/A", "Status": f"Failed: {str(e)[:30]}"}

# Input Form
tab1, tab2 = st.tabs(["Paste Emails", "Upload CSV"])
emails_to_process = []

with tab1:
    raw_emails = st.text_area("Paste emails (one per line):", height=140, placeholder="john.doe@stripe.com\nsundar@google.com")
    if raw_emails:
        emails_to_process = [e.strip() for e in raw_emails.split("\n") if e.strip()]

with tab2:
    uploaded_file = st.file_uploader("Upload CSV", type=["csv"])
    if uploaded_file:
        df_uploaded = pd.read_csv(uploaded_file)
        email_col = next((c for c in df_uploaded.columns if "email" in c.lower()), None)
        if email_col:
            emails_to_process = df_uploaded[email_col].dropna().astype(str).tolist()
            st.success(f"Found column `{email_col}` ({len(emails_to_process)} emails)")
        else:
            st.error("No column containing 'email' found.")

# Process
if st.button("Enrich Leads", type="primary"):
    if not api_key or not search_engine_id:
        st.error("Please enter both your Google API Key and Search Engine ID in the sidebar.")
    elif not emails_to_process:
        st.warning("Please provide at least one email address.")
    else:
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()

        for idx, email in enumerate(emails_to_process):
            status_text.text(f"Looking up ({idx + 1}/{len(emails_to_process)}): {email}")
            data = search_lead(email, api_key, search_engine_id)
            results.append(data)
            progress_bar.progress((idx + 1) / len(emails_to_process))
            time.sleep(0.2)

        status_text.text("Done!")
        df_results = pd.DataFrame(results)

        st.subheader("Results")
        st.dataframe(
            df_results,
            column_config={
                "LinkedIn": st.column_config.LinkColumn("Profile Link")
            },
            use_container_width=True
        )

        st.download_button(
            label="Download CSV",
            data=df_results.to_csv(index=False).encode("utf-8"),
            file_name="profiled_leads.csv",
            mime="text/csv"
        )
