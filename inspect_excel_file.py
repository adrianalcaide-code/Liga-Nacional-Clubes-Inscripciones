import pandas as pd
import json

try:
    file_path = r'g:\Mi unidad\Automatizaciones\Revisión LNC\FESBA Jugadores Inscripciones Liga Nacional edición 2025-2026.XLSX'
    df = pd.read_excel(file_path, header=None)
    
    print("FIRST 15 ROWS (Raw):")
    print(df.head(15).to_string())
    
    # Try to find a row that contains 'Nombre' or 'Club'
    for idx, row in df.head(15).iterrows():
        row_str = row.astype(str).str.lower().tolist()
        if any('nombre' in s for s in row_str) and any('club' in s for s in row_str):
            print(f"\nPotential HEADER detected at row index: {idx}")
            print(row.tolist())
        
except Exception as e:
    print(f"Error: {e}")
