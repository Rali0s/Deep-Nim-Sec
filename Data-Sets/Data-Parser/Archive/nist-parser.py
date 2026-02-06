import pandas as pd
import re
from pypdf import PdfReader

# 1. Configuration and Constants
NIST_PDF_PATH = '/Users/proteu5/Documents/deep/Deep-NIM/Data-Sets/RAW/Compliance/NIST.SP.800-171r3.pdf'  # Placeholder for your specific NIST document
OUTPUT_CSV_PATH = '/Users/proteu5/Documents/deep/Deep-NIM/Data-Sets/Tabular/nist_800-171_controls_dataset.csv'
CONTROL_ID_PATTERN = r'([A-Z]{2,4}-[0-9]{1,3}(\.\d{1,2})?)\s+([A-Za-z\s]+)' 
# Regex Explanation: Matches 'AA-1' or 'AA-1.1' followed by the Control Name

# 2. PDF Text Extraction
def extract_text_from_pdf(pdf_path):
    """Extracts text content from all pages of the PDF."""
    print(f"Loading PDF from {pdf_path}...")
    reader = PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        # Use page.extract_text() with layout option for better structural integrity
        text += page.extract_text() + "\n\n"
    print(f"Total characters extracted: {len(text)}")
    return text

# 3. Structured Parsing and Segmentation
def parse_nist_controls(full_text):
    """
    Parses the extracted text to identify Control IDs and their associated content.
    This method relies on identifying structural markers (Control IDs).
    """
    controls_data = []
    
    # Split the text by the main control identifiers (e.g., AC-1, CM-3)
    # This creates segments starting with a Control ID.
    segments = re.split(CONTROL_ID_PATTERN, full_text, flags=re.MULTILINE)
    
    # The first element is usually introductory text before the first control, so skip it.
    # The split operation results in groups: (Control ID, Numeric Part, Control Name, Content)
    
    # Re-assemble segments into (ID, Full Description) pairs
    i = 1
    while i < len(segments) - 1:
        
        # segments[i] is the full ID (e.g., AC-1)
        control_id = segments[i]
        
        # segments[i+1] is the optional numeric part (ignore)
        # segments[i+2] is the Control Name (e.g., Account Management)
        
        # The content/description for the current control is usually in the next major chunk
        content_index = i + 3 # Adjust this index based on observed PDF structure
        
        if content_index < len(segments):
            
            # Use the segments until the next potential control ID marker is encountered
            # This is the challenging part: defining the scope of the description.
            
            # For simplicity in this example, we capture the control ID and the name:
            control_name = segments[i+2].strip()
            
            # --- Advanced Segmentation Logic (Requires Manual Tuning) ---
            # To get the full description, we need a method to stop before the next control.
            # Since the text is split, the content of this control is often the block *following* the ID markers.
            
            # Simple approach: grab the next block of text until the next control starts
            description_block = segments[content_index] if content_index < len(segments) else ""
            
            # Clean up the description block (remove headers, excessive whitespace)
            description = description_block.split('\n\n')[0].strip() # Takes only the first paragraph after the ID
            
            if control_id and description and len(description) > 50: # Minimum length filter
                controls_data.append({
                    'Control_ID': control_id,
                    'Control_Description': f"{control_name}: {description}"
                })
        
        i += 4 # Move to the start of the next potential control identifier
        
    return controls_data

# 4. Data Structuring and Output
def main():
    try:
        # Load the text (Requires NIST_SP_800-53_Rev5.pdf to be present)
        full_document_text = extract_text_from_pdf(NIST_PDF_PATH)
        
        # Parse the structured data
        parsed_data = parse_nist_controls(full_document_text)
        
        # Create the DataFrame
        df = pd.DataFrame(parsed_data)

        # Ensure the final structure is 2-column: Control ID | Control Description
        df = df[['Control_ID', 'Control_Description']]
        
        # Save to CSV
        df.to_csv(OUTPUT_CSV_PATH, index=False)
        
        print(f"\nSuccessfully created 2-Column DataSet: {OUTPUT_CSV_PATH}")
        print(f"Total controls extracted: {len(df)}")
        
    except FileNotFoundError:
        print(f"Error: PDF file not found at {NIST_PDF_PATH}. Please ensure the file is correctly placed.")
    except Exception as e:
        print(f"An unexpected error occurred during processing: {e}")

if __name__ == '__main__':
    # NOTE: The effectiveness of the regex parsing (Step 3) is highly dependent on 
    # the exact formatting and layout of the specific NIST PDF version used. 
    # Manual verification and tuning of the regex pattern will be required.
    main()