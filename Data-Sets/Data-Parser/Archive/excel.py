import pandas as pd
import os

def combine_text(row, columns):
    """Concatenate specified columns into a single string."""
    values = []
    for col in columns:
        val = row.get(col)
        if pd.isnull(val) or str(val).strip() == '':
            continue
        # Flatten list-like entries and remove line breaks
        text = (
            val if not isinstance(val, list) 
            else ", ".join(str(item) for item in val)
        )
        text = str(text).replace('\n', ' ').strip()
        if text:
            # Prefix with column name to provide context
            values.append(f"{col}: {text}")
    return " | ".join(values)

def build_two_column_dataset(excel_path: str, output_csv: str):
    """
    Read the ATT&CK Excel workbook, extract relevant text fields from each sheet,
    and build a two-column dataset (target and input_feature).
    
    Parameters:
        excel_path (str): path to the Enterprise ATT&CK v17.1 Excel file.
        output_csv (str): path where the resulting two-column CSV will be saved.
    """
    # Mapping of each sheet to the columns to include in the input_feature
    sheet_configs = {
        "techniques": [
            "name", "description", "tactics", "detection", "platforms",
            "data sources", "contributors"
        ],
        "software": [
            "name", "description", "platforms", "aliases", "type", "contributors"
        ],
        "groups": [
            "name", "description", "associated groups", "contributors"
        ],
        "campaigns": [
            "name", "description", "first seen", "last seen", "contributors"
        ],
        "mitigations": [
            "name", "description"
        ],
        "datasources": [
            "name", "description", "collection layers", "platforms"
        ],
        "tactics": [
            "name", "description"
        ],
    }

    combined_rows = []

    # Iterate through sheets and build the two-column dataset
    for sheet_name, columns in sheet_configs.items():
        try:
            df = pd.read_excel(excel_path, sheet_name=sheet_name)
        except Exception as e:
            print(f"Skipping sheet {sheet_name}: {e}")
            continue

        # Create a 'target' column based on the sheet name
        df["target"] = sheet_name

        # Create the 'input_feature' by concatenating selected columns
        df["input_feature"] = df.apply(lambda row: combine_text(row, columns), axis=1)

        # Keep only rows with non-empty input_feature
        df_two_col = df[["target", "input_feature"]].copy()
        df_two_col = df_two_col[df_two_col["input_feature"].str.strip() != ""]

        combined_rows.append(df_two_col)

    # Concatenate all sheets into a single DataFrame
    dataset = pd.concat(combined_rows, ignore_index=True)

    # Drop any potential duplicates
    dataset = dataset.drop_duplicates()

    # Save to CSV with UTF-8 encoding
    dataset.to_csv(output_csv, index=False, encoding="utf-8")
    print(f"Dataset saved to {output_csv} with {len(dataset)} rows.")

if __name__ == "__main__":
    # Example usage
    input_excel = "/Users/proteu5/Documents/deep/Deep-NIM/Data-Sets/TXT/mobile-attack-v17.1.xlsx"
    output_dataset_csv = "/Users/proteu5/Documents/deep/Deep-NIM/Data-Sets/TXT/mobile-attack-v17.1.csv"
    
    # Ensure the input file exists
    if not os.path.isfile(input_excel):
        raise FileNotFoundError(f"Excel file not found: {input_excel}")    
    build_two_column_dataset(input_excel, output_dataset_csv)
