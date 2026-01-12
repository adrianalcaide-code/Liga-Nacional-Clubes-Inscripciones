
import json
import os
import difflib

FILE_PATH = "historial_inscripciones.json"
TARGET_NAME = "Jugadores Inscripciones Liga Nacional edición 2025-2026 plazo enero.XLSX"
CLEAN_NAME = "Jugadores LNC 25-26 (Enero).xlsx"

def repair():
    if not os.path.exists(FILE_PATH):
        print("❌ File not found")
        return

    print("--- REPAIRING HISTORY JSON ---")
    try:
        # Load with error ignore to survive bad chars
        with open(FILE_PATH, 'rb') as f:
            raw = f.read()
        
        # Try decoding as utf-8, fallback to latin1
        try:
            content = raw.decode('utf-8')
        except:
            content = raw.decode('latin1')
            
        data = json.loads(content)
        keys = list(data.keys())
        print(f"Loaded {len(keys)} keys")

        # Find match
        matches = difflib.get_close_matches(TARGET_NAME, keys, n=1, cutoff=0.3)
        
        if matches:
            bad_key = matches[0]
            print(f"🔍 Found candidate: {repr(bad_key)}")
            
            if bad_key != CLEAN_NAME:
                print(f"🛠️  Renaming to: {CLEAN_NAME}")
                data[CLEAN_NAME] = data.pop(bad_key)
                
                # Update timestamp if missing
                if 'timestamp' not in data[CLEAN_NAME]:
                    from datetime import datetime
                    data[CLEAN_NAME]['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # Save back with STRICT UTF-8
                with open(FILE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                print("✅ FILE SAVED SUCCESSFULLY")
            else:
                print("✅ Key is already clean.")
        else:
            print("❌ No close match found.")
            
    except Exception as e:
        print(f"❌ ERROR: {e}")

if __name__ == "__main__":
    repair()
