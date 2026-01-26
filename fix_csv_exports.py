import pandas as pd
import re
import os

files = [
    r"g:\Mi unidad\Automatizaciones\Revisión LNC\Exportaciones app\import_players_Primera_BRONCE (3).csv",
    r"g:\Mi unidad\Automatizaciones\Revisión LNC\Exportaciones app\import_players_Primera_ORO (7).csv",
    r"g:\Mi unidad\Automatizaciones\Revisión LNC\Exportaciones app\import_players_Primera_PLATA (2).csv",
    r"g:\Mi unidad\Automatizaciones\Revisión LNC\Exportaciones app\import_players_Segunda_ORO (4).csv"
]

def clean_lastname(val):
    if not isinstance(val, str):
        return val
    # Remove content in parenthesis including the parenthesis
    # Handle multiple parentheses e.g. "(Baja) (HN-p)"
    # Strategy: Remove all (XYZ) patterns.
    clean = re.sub(r'\s*\(.*?\)', '', val)
    return clean.strip()

for file_path in files:
    if os.path.exists(file_path):
        try:
            # Try reading with different encodings
            try:
                df = pd.read_csv(file_path, sep=';', encoding='utf-8')
            except UnicodeDecodeError:
                df = pd.read_csv(file_path, sep=';', encoding='latin-1')
            
            if 'lastname' in df.columns:
                print(f"Cleaning {os.path.basename(file_path)}...")
                original_count = len(df)
                
                # Show examples before
                print("Examples before:", df['lastname'].iloc[14:17].tolist())
                
                df['lastname'] = df['lastname'].apply(clean_lastname)
                
                # Show examples after
                print("Examples after: ", df['lastname'].iloc[14:17].tolist())
                
                # Save back with same format
                # Pandas to_csv with sep=';' usually works fine.
                # Encoding: Excel likes utf-8-sig or latin-1. I'll use utf-8-sig (BOM) to be safe for special chars.
                df.to_csv(file_path, sep=';', index=False, encoding='utf-8-sig')
                print("Saved.")
            else:
                print(f"Skipping {file_path} (no lastname column)")
                
        except Exception as e:
            print(f"Error processing {file_path}: {e}")
    else:
        print(f"File not found: {file_path}")
