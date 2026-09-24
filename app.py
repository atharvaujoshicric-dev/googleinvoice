import io
import re
import zipfile
import pandas as pd
import pdfplumber
import streamlit as st

st.set_page_config(page_title="Google Ads Invoice Extractor", layout="wide")

st.title("Google Ads Invoice Parser")
st.write("Upload a `.zip` archive containing Google Ads invoice PDFs to extract structured billing data into Excel.")


def clean_currency(val: str) -> str:
    """Removes currency symbols and extra whitespace."""
    if not val:
        return ""
    val = val.replace("₹", "").replace("INR", "").strip()
    return val


def parse_invoice_pdf(pdf_bytes: bytes, filename: str) -> dict:
    """Extracts required invoice fields from Google Ads PDF bytes."""
    full_text = ""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                full_text += "\n" + page_text

    # 1. Invoice Number
    inv_num_match = re.search(r"Invoice\s*number[:\s]+(\d+)", full_text, re.IGNORECASE)
    invoice_number = inv_num_match.group(1).strip() if inv_num_match else ""

    # 2. Account Name
    account_match = re.search(r"Account[:\s]+([^\n\r]+)", full_text, re.IGNORECASE)
    account_name = ""
    if account_match:
        # Ignore lines like 'Account ID:'
        raw_account = account_match.group(1).strip()
        if not raw_account.lower().startswith("id"):
            account_name = raw_account

    # 3. Description
    # Matches the item row between 'Description' headers and the subtotal section
    desc_match = re.search(
        r"Description\s*\n\s*([^\n\r]+?)(?:\s+\d+\s+Clicks|\s+\d+\s+Impressions|\s+\d+\s+Units|\n)",
        full_text,
        re.IGNORECASE,
    )
    description = ""
    if desc_match:
        description = desc_match.group(1).strip()
    else:
        # Fallback regex for common campaign description placement
        fallback_desc = re.search(
            r"([A-Za-z0-9_\-]+)\s+\d+\s+(?:Clicks|Units|Impressions)", full_text
        )
        if fallback_desc:
            description = fallback_desc.group(1).strip()

    # 4. Subtotal INR
    subtotal_match = re.search(
        r"Subtotal\s*(?:in\s*INR)?[\s|:]*[₹\s]*([\d,]+(?:\.\d{2})?)",
        full_text,
        re.IGNORECASE,
    )
    subtotal = clean_currency(subtotal_match.group(1)) if subtotal_match else ""

    # 5. Integrated GST
    igst_match = re.search(
        r"Integrated\s*GST[^\n\r\d]*[\s|:]*[₹\s]*([\d,]+(?:\.\d{2})?)",
        full_text,
        re.IGNORECASE,
    )
    igst = clean_currency(igst_match.group(1)) if igst_match else ""

    # 6. Total INR
    total_match = re.search(
        r"Total\s*(?:in\s*INR)?[\s|:]*[₹\s]*([\d,]+(?:\.\d{2})?)",
        full_text,
        re.IGNORECASE,
    )
    total = clean_currency(total_match.group(1)) if total_match else ""

    return {
        "File Name": filename,
        "Invoice Number": invoice_number,
        "Account": account_name,
        "Description": description,
        "Subtotal (INR)": subtotal,
        "Integrated GST (INR)": igst,
        "Total (INR)": total,
    }


# File Uploader supporting up to 500 MB
uploaded_file = st.file_uploader(
    "Choose a ZIP file containing invoices", type=["zip"],
    max_upload_size=500  # Sets the limit to 500 MB for this widget
)

if uploaded_file is not None:
    try:
        with zipfile.ZipFile(uploaded_file, "r") as z:
            # Find all PDF files in archive, including subdirectories (ignoring macOS metadata folders)
            pdf_files = [
                name
                for name in z.namelist()
                if name.lower().endswith(".pdf")
                and not name.startswith("__MACOSX/")
                and not name.startswith(".")
            ]

            if not pdf_files:
                st.warning("No PDF files found inside the uploaded ZIP archive.")
            else:
                st.info(f"Found {len(pdf_files)} PDF invoice(s). Processing...")

                records = []
                progress_bar = st.progress(0)

                for idx, pdf_name in enumerate(pdf_files):
                    pdf_data = z.read(pdf_name)
                    display_name = pdf_name.split("/")[-1]
                    extracted_row = parse_invoice_pdf(pdf_data, display_name)
                    records.append(extracted_row)
                    progress_bar.progress((idx + 1) / len(pdf_files))

                df = pd.DataFrame(records)

                st.success("Extraction complete!")
                st.dataframe(df, use_container_width=True)

                # Export to Excel buffer
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine="openpyxl") as writer:
                    df.to_excel(writer, index=False, sheet_name="Invoices")

                excel_data = output.getvalue()

                st.download_button(
                    label="📥 Download Extracted Data as Excel",
                    data=excel_data,
                    file_name="Google_Invoices_Summary.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

    except zipfile.BadZipFile:
        st.error("The uploaded file is not a valid ZIP archive.")
    except Exception as e:
        st.error(f"An error occurred while processing: {str(e)}")
