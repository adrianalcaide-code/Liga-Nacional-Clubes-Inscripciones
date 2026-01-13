
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules.state import load_session_data, load_history
import traceback
import pandas as pd

print("--- REPRODUCE CRASH ---")
history = load_history()
if history:
    # Sort to get latest
    sorted_sessions = sorted(
        history.items(), 
        key=lambda x: x[1].get('timestamp', '') or '', 
        reverse=True
    )
    latest = sorted_sessions[0][0]
    print(f"Target Session: {latest}")
    
    try:
        # Load data
        df = load_session_data(latest)
        print(f"Loaded Shape: {df.shape}")
        
        # Check for unhashable columns
        print("Checking hashability of columns...")
        for col in df.columns:
            # We suspect keys used for grouping/factorizing: Club, Pruebas, Entity...
            try:
                # factorize is what failed in the log
                pd.factorize(df[col]) 
            except TypeError as Te:
                if "unhashable" in str(Te):
                    print(f"❌ '{col}' IS UNHASHABLE (List?!). Sample: {df[col].iloc[0]}")
                else:
                    print(f"⚠️ '{col}' raised other TypeError: {Te}")
            except Exception as e:
                 print(f"⚠️ '{col}' raised {type(e).__name__}: {e}")
                 
        print("Done.")

    except Exception as e:
        print("CRITICAL CRASH during load:")
        traceback.print_exc()
else:
    print("No history found.")
