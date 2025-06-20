import os
import re
from pypdf import PdfReader
from pypdf.errors import PdfReadError

def sanitize_filename(name):
    """Removes invalid characters from a string to make it a valid filename."""
    # Replace common invalid characters with an underscore
    sanitized = re.sub(r'[\\/:*?"<>|]', '_', name)
    # Replace multiple underscores with a single one
    sanitized = re.sub(r'__+', '_', sanitized)
    # Trim leading/trailing underscores and spaces
    sanitized = sanitized.strip(' _')
    # Limit filename length (optional, but good practice)
    if len(sanitized) > 200:
        sanitized = sanitized[:200]
    return sanitized

def extract_text_from_pdf(pdf_path):
    """Extracts text from a PDF file."""
    try:
        reader = PdfReader(pdf_path)
        text = ""
        # You might limit the number of pages to scan for performance
        # For typical documents, the first few pages are usually enough
        for i, page in enumerate(reader.pages):
            text += page.extract_text() or ""
            if i >= 5:  # Limit reading to first 6 pages to speed things up
                break
        return text
    except PdfReadError:
        print(f"  [ERROR] Could not read PDF structure for '{os.path.basename(pdf_path)}'. It might be corrupted or encrypted.")
        return None
    except Exception as e:
        print(f"  [ERROR] An unexpected error occurred while reading '{os.path.basename(pdf_path)}': {e}")
        return None

def generate_new_name_from_content(text_content):
    """
    Analyzes the text content and suggests a new filename.
    You can customize the patterns below based on your document types.
    """
    if not text_content:
        return None

    new_name_parts = []

    # --- Common Patterns (add/modify as needed) ---

    # 1. Invoice/Order/PO Numbers (often the most important)
    # Example: "Invoice #12345", "INV-2023-001", "PO-XYZ-987"
    invoice_patterns = [
        # (regex_pattern, name_prefix)
        (r'(?:invoice|inv)\s*[#:]?\s*([A-Za-z0-9-]+)', 'Invoice'),
        (r'(?:order|po)\s*[#:]?\s*([A-Za-z0-9-]+)', 'Order'),
        (r'Ref[#:]?\s*([A-Za-z0-9-]+)', 'Ref') # Generic reference
    ]
    for pattern, prefix in invoice_patterns:
        match = re.search(pattern, text_content, re.IGNORECASE)
        if match:
            part = match.group(1).strip()
            # Ensure the extracted part isn't too short or generic (like just a year)
            if len(part) > 3 and not re.fullmatch(r'\d{4}', part):
                new_name_parts.append(f"{prefix}-{part}")
                break # Assume one main identifier is enough

    # 2. Dates
    # Prioritize YYYY-MM-DD, then MM/DD/YYYY, DD-MM-YYYY
    date_patterns = [
        r'\b(\d{4}[-./]\d{1,2}[-./]\d{1,2})\b',              # YYYY-MM-DD or YYYY.MM.DD
        r'\b(\d{1,2}[-./]\d{1,2}[-./]\d{2,4})\b',            # MM/DD/YY or MM.DD.YYYY
        r'\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},\s+\d{4}\b' # Month DD, YYYY
    ]
    found_date = None
    for pattern in date_patterns:
        match = re.search(pattern, text_content)
        if match:
            # Attempt to normalize date format to YYYY-MM-DD for consistency
            try:
                # This is a bit complex for all formats, simple example:
                from datetime import datetime
                if '-' in match.group(1) or '.' in match.group(1): # YYYY-MM-DD or MM-DD-YYYY
                    if len(match.group(1).split('-')[0]) == 4: # Assuming it's YYYY-MM-DD
                        dt_obj = datetime.strptime(match.group(1), '%Y-%m-%d')
                    else: # Assuming it's MM-DD-YYYY or DD-MM-YYYY
                         try: dt_obj = datetime.strptime(match.group(1), '%m-%d-%Y')
                         except ValueError: dt_obj = datetime.strptime(match.group(1), '%d-%m-%Y')
                elif ',' in match.group(0): # Month DD, YYYY
                    dt_obj = datetime.strptime(match.group(0), '%B %d, %Y')
                else: # Fallback to original match if normalization fails
                    dt_obj = None

                if dt_obj:
                    found_date = dt_obj.strftime('%Y-%m-%d')
                else:
                    found_date = match.group(0).replace('/', '-').replace('.', '-') # Basic conversion
                break
            except Exception:
                found_date = match.group(0).replace('/', '-').replace('.', '-') # Fallback if datetime conversion fails

    if found_date:
        new_name_parts.append(found_date)

    # 3. Customer/Company Name (more complex, requires specific entity extraction)
    # This is highly dependent on your documents. Often seen near "Bill to", "Sold to".
    # For a general script, this is harder without specific examples.
    # Example: Look for a line starting with "Customer Name:" or similar.
    # cust_match = re.search(r'(?:Customer|Client)\s*(?:Name)?:?\s*([A-Za-z\s.,-]+)', text_content, re.IGNORECASE)
    # if cust_match:
    #     customer_name = cust_match.group(1).strip()
    #     if customer_name and len(customer_name) > 3:
    #         new_name_parts.append(customer_name)

    # --- Fallback if no specific patterns found ---
    if not new_name_parts:
        # Try to find some generic title or first few words
        first_line = text_content.strip().split('\n')[0]
        if first_line:
            # Take a reasonable chunk of the first line
            generic_title = first_line[:50].strip()
            if generic_title:
                new_name_parts.append(generic_title)
        else:
            return None # Couldn't find anything useful

    # Combine parts into a single string
    base_name = "_".join(new_name_parts).replace(' ', '_')
    return sanitize_filename(base_name)

def rename_pdf_files_in_folder(folder_path, dry_run=True):
    """
    Iterates through PDF files in a folder and renames them based on content.
    """
    if not os.path.isdir(folder_path):
        print(f"Error: Folder not found at '{folder_path}'")
        return

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Processing PDFs in: '{folder_path}'")
    print("------------------------------------------------------------------")

    pdf_files_found = 0
    renamed_count = 0
    skipped_count = 0

    for filename in os.listdir(folder_path):
        if filename.lower().endswith('.pdf'):
            pdf_files_found += 1
            old_file_path = os.path.join(folder_path, filename)

            print(f"\nProcessing '{filename}'...")
            text_content = extract_text_from_pdf(old_file_path)

            if text_content is None:
                print(f"  Skipping '{filename}' due to extraction error or empty content.")
                skipped_count += 1
                continue

            new_name_base = generate_new_name_from_content(text_content)

            if new_name_base is None:
                print(f"  Could not determine a meaningful new name for '{filename}'. Skipping.")
                skipped_count += 1
                continue

            # Ensure unique filename if it conflicts
            original_new_name_base = new_name_base
            counter = 1
            new_filename = f"{new_name_base}.pdf"
            new_file_path = os.path.join(folder_path, new_filename)

            while os.path.exists(new_file_path) and new_file_path != old_file_path:
                new_name_base = f"{original_new_name_base}_{counter}"
                new_filename = f"{new_name_base}.pdf"
                new_file_path = os.path.join(folder_path, new_filename)
                counter += 1

            if new_file_path == old_file_path:
                print(f"  '{filename}' already has an ideal name. No change needed.")
                skipped_count += 1
            else:
                if dry_run:
                    print(f"  [DRY RUN] Would rename to: '{new_filename}'")
                    renamed_count += 1
                else:
                    try:
                        os.rename(old_file_path, new_file_path)
                        print(f"  Renamed '{filename}' to '{new_filename}'")
                        renamed_count += 1
                    except OSError as e:
                        print(f"  [ERROR] Failed to rename '{filename}' to '{new_filename}': {e}")
                        skipped_count += 1
                    except Exception as e:
                        print(f"  [ERROR] An unexpected error occurred renaming '{filename}': {e}")
                        skipped_count += 1

    print("\n------------------------------------------------------------------")
    print(f"Summary:")
    print(f"  Total PDFs found: {pdf_files_found}")
    print(f"  { '[DRY RUN] ' if dry_run else '' }Files {'would be ' if dry_run else ''}renamed: {renamed_count}")
    print(f"  Files skipped/errors: {skipped_count}")
    if dry_run:
        print("\nThis was a DRY RUN. No files were actually renamed.")
        print("To perform the actual renaming, run the script again and choose 'n' at the dry run prompt.")


if __name__ == "__main__":
    folder = input("Enter the folder path containing the PDF files: ").strip()

    perform_dry_run = True
    dry_run_choice = input("Perform a dry run first? (y/n, default 'y'): ").strip().lower()
    if dry_run_choice == 'n':
        perform_dry_run = False

    rename_pdf_files_in_folder(folder, dry_run=perform_dry_run)

    if perform_dry_run:
        final_action = input("\nReview the dry run output. Do you want to proceed with actual renaming? (y/n): ").strip().lower()
        if final_action == 'y':
            print("\nStarting actual renaming...")
            rename_pdf_files_in_folder(folder, dry_run=False)
        else:
            print("Operation cancelled. No files were renamed.")
