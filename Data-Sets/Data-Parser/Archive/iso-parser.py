import pandas as pd
import re
from pypdf import PdfReader

# 1. Configuration and Constants
ISO_PDF_PATH = '/Users/proteu5/Documents/deep/Deep-NIM/Data-Sets/RAW/Compliance/MasteringISCM.epub'  # Placeholder for your ISO document
OUTPUT_CSV_PATH = '/Users/proteu5/Documents/deep/Deep-NIM/Data-Sets/Tabular/ISMS_controls_dataset.csv'

# Regex Explanation for ISO 27001 Controls (e.g., 5.11, 6.2.3):
# Pattern looks for a number (1 or 2 digits), followed by a dot, followed by more digits.
# It assumes the Control ID is at the start of a line or clear text block.
CONTROL_ID_PATTERN = r'\n\s*(\d{1,2}\.\d{1,2}(?:\.\d{1,2})?)\s+' 
# Group 1 captures the Control ID (e.g., 5.11, 6.2)

# 2. PDF Text Extraction (Reusing the function)
def extract_text_from_pdf(pdf_path):
    """Extracts text content from all pages of the PDF."""
    print(f"Loading PDF from {pdf_path}...")
    reader = PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n\n"
    print(f"Total characters extracted: {len(text)}")
    return text

# 3. Structured Parsing and Segmentation
def parse_iso_controls(full_text):
    """
    Parses the text by splitting on the Control ID pattern and restructuring the data.
    """
    controls_data = []
    
    # Split the entire text based on the Control ID pattern.
    # The split function captures the delimiters (the Control IDs).
    segments = re.split(CONTROL_ID_PATTERN, full_text)
    
    # The first element of segments is usually introductory text before the first control ID.
    
    i = 1
    while i < len(segments):
        # Segment at index i is the captured Control ID (e.g., '5.11')
        control_id = segments[i].strip()
        
        # Segment at index i+1 is the descriptive text that immediately follows the Control ID
        if i + 1 < len(segments):
            raw_description = segments[i+1].strip()
            
            # Clean up the raw description: often the ID is followed by the control NAME
            # We look for the first major descriptive sentence/paragraph
            
            # Heuristic cleaning: find the first period or newline to clean up stray headers
            description_lines = raw_description.split('\n')
            
            # Assume the first non-empty line contains the Control Name + Start of Description
            full_description = ' '.join(line.strip() for line in description_lines if line.strip())
            
            # Example filtering based on your provided text structure:
            # "5.11 Return of assets Control Personnel and other interested parties..."
            
            if control_id and full_description:
                
                # Further cleanup: remove potential trailing control IDs if parsing was imprecise
                full_description = re.sub(CONTROL_ID_PATTERN, '', full_description, count=1).strip()
                
                controls_data.append({
                    'Control_ID': control_id,
                    'Control_Description': full_description
                })
        
        i += 2 # Move to the next pair (Control ID and its description)
        
    return controls_data

# 4. Data Structuring and Output
def main():
    try:
        full_document_text = extract_text_from_pdf(ISO_PDF_PATH)
        parsed_data = parse_iso_controls(full_document_text)
        
        df = pd.DataFrame(parsed_data)
        df = df[['Control_ID', 'Control_Description']]
        
        # Save to CSV
        df.to_csv(OUTPUT_CSV_PATH, index=False)
        
        print(f"\nSuccessfully created 2-Column DataSet: {OUTPUT_CSV_PATH}")
        print(f"Total controls extracted: {len(df)}")
        
    except FileNotFoundError:
        print(f"Error: PDF file not found at {ISO_PDF_PATH}. Please ensure the file is correctly placed.")
    except Exception as e:
        print(f"An unexpected error occurred during processing: {e}")

if __name__ == '__main__':
    main()