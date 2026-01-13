
import json
import os

FILE_PATH = "historial_inscripciones.json"

def inspect():
    if not os.path.exists(FILE_PATH):
        print("❌ FILE MISSING")
        return

    try:
        with open(FILE_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        print(f"✅ Loaded JSON. Keys found: {list(data.keys())}")
        
        for k, v in data.items():
            count = len(v.get('data', []))
            ts = v.get('timestamp', 'No TS')
            print(f" - '{k}': {count} records ({ts})")
            
    except Exception as e:
        print(f"❌ ERROR LOADING JSON: {e}")

if __name__ == "__main__":
    inspect()
