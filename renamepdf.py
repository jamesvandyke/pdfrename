import os
import re
import shutil
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from openai import OpenAI
from dotenv import load_dotenv


# Create an OpenAI client using the API key provided in the environment.
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CLIENT = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


def sanitize_filename(name: str) -> str:
    """Remove invalid characters from a string to create a safe filename."""
    sanitized = re.sub(r'[\\/:*?"<>|]', '_', name)
    sanitized = re.sub(r'__+', '_', sanitized)
    sanitized = sanitized.strip(' _')
    if len(sanitized) > 200:
        sanitized = sanitized[:200]
    return sanitized


def is_valid_filename(name: str) -> bool:
    """Return True if the name contains only letters, numbers, spaces or underscores."""
    return bool(re.fullmatch(r"[A-Za-z0-9 _]+", name))


def extract_text_from_pdf(pdf_path: str) -> str | None:
    """Read all text from the PDF."""
    try:
        reader = PdfReader(pdf_path)
        text = "".join(page.extract_text() or "" for page in reader.pages)
        return text
    except PdfReadError:
        print(f"  [ERROR] Could not read '{os.path.basename(pdf_path)}'.")
        return None
    except Exception as exc:
        print(f"  [ERROR] Unexpected error reading '{os.path.basename(pdf_path)}': {exc}")
        return None


def get_last_line(text: str) -> str | None:
    """Return the last non-empty line from text."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    return sanitize_filename(lines[-1])


def get_title_via_chatgpt(text: str) -> str | None:
    """Request a short title from ChatGPT using the document text."""
    if not CLIENT:
        print("  [ERROR] OPENAI_API_KEY environment variable not set.")
        return None

    trimmed = text[:4000]
    try:
        response = CLIENT.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": "You generate short and descriptive filenames. Filenames start with the client name, then then project name. Filenames may have spaces but may not have other punctuation. Do not include REES in the name of the file.",
                },
                {
                    "role": "user",
                    "content": f"Provide a short filename for this document:\n{trimmed}",
                },
            ],
            max_tokens=10,
            temperature=0.2,
        )
        title = response.choices[0].message.content.strip()
        return sanitize_filename(title)
    except Exception as exc:
        print(f"  [ERROR] ChatGPT title generation failed: {exc}")
        return None


def rename_pdfs_in_folder(folder_path: str, dry_run: bool = True) -> None:
    if not os.path.isdir(folder_path):
        print(f"Error: Folder not found at '{folder_path}'")
        return

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Processing PDFs in: '{folder_path}'")
    print("------------------------------------------------------------------")

    pdf_files_found = 0
    renamed_count = 0
    skipped_count = 0

    for filename in os.listdir(folder_path):
        if not filename.lower().endswith('.pdf'):
            continue

        pdf_files_found += 1
        old_file_path = os.path.join(folder_path, filename)

        print(f"\nProcessing '{filename}'...")
        text_content = extract_text_from_pdf(old_file_path)

        if not text_content:
            print(f"  Skipping '{filename}' due to extraction error or empty content.")
            skipped_count += 1
            continue

        title = get_title_via_chatgpt(text_content)
        if not title:
            print(f"  Could not determine a new name for '{filename}'. Skipping.")
            skipped_count += 1
            continue

        if not is_valid_filename(title):
            print(f"  Generated title contains unsupported characters. Skipping.")
            skipped_count += 1
            continue

        new_filename = f"{title}.pdf"
        new_file_path = os.path.join(folder_path, new_filename)
        counter = 1
        while os.path.exists(new_file_path) and new_file_path != old_file_path:
            new_filename = f"{title}_{counter}.pdf"
            new_file_path = os.path.join(folder_path, new_filename)
            counter += 1

        if new_file_path == old_file_path:
            print(f"  '{filename}' already has the desired name. No change needed.")
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
                except Exception as exc:
                    print(f"  [ERROR] Failed to rename '{filename}': {exc}")
                    skipped_count += 1

    print("\n------------------------------------------------------------------")
    print("Summary:")
    print(f"  Total PDFs found: {pdf_files_found}")
    print(f"  { '[DRY RUN] ' if dry_run else '' }Files {'would be ' if dry_run else ''}renamed: {renamed_count}")
    print(f"  Files skipped/errors: {skipped_count}")


def move_pdfs_to_folder(src_folder: str, dest_folder: str) -> None:
    """Move all PDF files from src_folder to dest_folder."""
    if not os.path.isdir(dest_folder):
        try:
            os.makedirs(dest_folder, exist_ok=True)
            print(f"Created destination folder: '{dest_folder}'")
        except Exception as exc:
            print(f"  [ERROR] Failed to create destination folder '{dest_folder}': {exc}")
            return

    moved_count = 0
    for filename in os.listdir(src_folder):
        if not filename.lower().endswith('.pdf'):
            continue

        src_path = os.path.join(src_folder, filename)
        dest_path = os.path.join(dest_folder, filename)
        counter = 1
        while os.path.exists(dest_path):
            name, ext = os.path.splitext(filename)
            dest_path = os.path.join(dest_folder, f"{name}_{counter}{ext}")
            counter += 1

        try:
            shutil.move(src_path, dest_path)
            moved_count += 1
        except Exception as exc:
            print(f"  [ERROR] Failed to move '{filename}': {exc}")

    print(f"Moved {moved_count} PDF file(s) to '{dest_folder}'.")


if __name__ == "__main__":
    folder = input("Enter the folder path containing the PDF files: ").strip()

    perform_dry_run = True
    dry_run_choice = input("Perform a dry run first? (y/n, default 'y'): ").strip().lower()
    if dry_run_choice == 'n':
        perform_dry_run = False

    rename_pdfs_in_folder(folder, dry_run=perform_dry_run)

    actually_renamed = False

    if perform_dry_run:
        final_action = input(
            "\nReview the dry run output. Do you want to proceed with actual renaming? (y/n): "
        ).strip().lower()
        if final_action == 'y':
            print("\nStarting actual renaming...")
            rename_pdfs_in_folder(folder, dry_run=False)
            actually_renamed = True
        else:
            print("Operation cancelled. No files were renamed.")
    else:
        actually_renamed = True

    if actually_renamed:
        move_choice = input(
            "\nMove the renamed files to a different folder? (y/n, default 'n'): "
        ).strip().lower()
        if move_choice == 'y':
            destination = input("Enter the destination folder path: ").strip()
            move_pdfs_to_folder(folder, destination)
