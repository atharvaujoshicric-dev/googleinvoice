import streamlit as st
import pandas as pd
import re
import time
from duckduckgo_search import DDGS

st.set_page_config(page_title="Free Lead Profiler", page_icon="🔎", layout="wide")

st.title("🔎 Free LinkedIn Lead Profiler")
st.write("Extract LinkedIn profiles, current titles, and companies directly from public search indices with zero API keys.")

def parse_linkedin_title(title_str: str) -> tuple:
    """
    LinkedIn SERP titles typically follow:
    'Full Name - Job Title - Company | LinkedIn' or 'Full Name - Title at Company'
    """
    cleaned = re.sub(r"\s*\|\s*LinkedIn.*$", "", title_str, flags=re.IGNORECASE)
    parts = [p.strip() for p in cleaned.split(" - ") if p.strip()]
    
    name = parts[0] if len(parts) > 0 else "N/A"
    title = parts[1] if len(parts) > 1 else "N/A"
    company = parts[2] if len(parts) > 2 else "N/A"
    
    # Check for 'at' pattern if company wasn't separated by dash
    if company == "N/A" and " at " in title:
        sub = title.split(" at ")
        title = sub[0].strip()
        company = sub[1].strip()
        
    return name, title, company

def extract_name_and_domain(email: str) -> tuple:
    """Derives a guess of name and company domain from standard email formats."""
    local, domain = email.split("@")
    clean_domain = domain.split(".")[0]
    
    # Strip dots/underscores to derive candidate name (e.g. john.doe -> John Doe)
    clean_name = re.sub(r"[._-]", " ", local).title()
    return clean_name, clean_domain

def find_profile_free(email: str, ddgs: DDGS) -> dict:
    email = email.strip()
    if "@" not in email:
        return {"Email": email, "Name": "Invalid", "Title": "Invalid", "Company": "Invalid", "LinkedIn": "N/A", "Status": "Invalid Email"}

    # Strategy 1: Exact search for the email on LinkedIn profile pages
    query = f'site:linkedin.com/in/ "{email}"'
    try:
        results = list(ddgs.text(query, max_results=1))
        
        # Strategy 2: If exact email is not indexed, search for derived name + company domain
        if not results:
            name_guess, domain_guess = extract_name_and_domain(email)
            query = f'site:linkedin.com/in/ "{name_guess}" "{domain_guess}"'
            results = list(ddgs.text(query, max_results=1))
            
        if results:
            item = results[0]
            link = item.get("href", "")
            raw_title = item.get("title", "")
            snippet = item.get("body", "")
            
            name, title, company = parse_linkedin_title(raw_title)
            
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
        return {"Email": email, "Name": "N/A", "Title": "N/A", "Company": "N/A", "LinkedIn": "N/A", "Status": f"Error: {str(e)[:40]}"}

# Input Form
tab1, tab2 = st.tabs(["Paste Emails", "Upload CSV"])
emails_to_process = []

with tab1:
    raw_emails = st.text_area("Enter email addresses (one per line):", height=150, placeholder="satya.nadella@microsoft.com\nsundar@google.com")
    if raw_emails:
        emails_to_process = [e.strip() for e in raw_emails.split("\n") if e.strip()]

with tab2:
    uploaded_file = st.file_uploader("Upload CSV containing an 'email' column", type=["csv"])
    if uploaded_file:
        df_uploaded = pd.read_csv(uploaded_file)
        email_col = next((c for c in df_uploaded.columns if "email" in c.lower()), None)
        if email_col:
            emails_to_process = df_uploaded[email_col].dropna().astype(str).tolist()
            st.success(f"Detected column `{email_col}` with {len(emails_to_process)} emails.")
        else:
            st.error("No column with 'email' in its name found in the CSV.")

if st.button("Start Profiling", type="primary"):
    if not emails_to_process:
        st.warning("Please provide at least one email address.")
    else:
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        with DDGS() as ddgs:
            for idx, email in enumerate(emails_to_process):
                status_text.text(f"Searching ({idx + 1}/{len(emails_to_process)}): {email}")
                res = find_profile_free(email, ddgs)
                results.append(res)
                progress_bar.progress((idx + 1) / len(emails_to_process))
                
                # Crucial: Introduce a 1.5-2.0s delay to avoid search throttle
                time.sleep(1.5)

        status_text.text("Finished processing all emails!")
        df_results = pd.DataFrame(results)

        st.subheader("Results")
        st.dataframe(
            df_results,
            column_config={
                "LinkedIn": st.column_config.LinkColumn("LinkedIn Profile")
            },
            use_container_width=True
        )

        csv_data = df_results.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download Results (CSV)",
            data=csv_data,
            file_name="linkedin_leads_free.csv",
            mime="text/csv"
        )
