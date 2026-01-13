
import json
import os
import sys

# Force output encoding
sys.stdout.reconfigure(encoding='utf-8')

FILE_PATH = "historial_inscripciones.json"

if not os.path.exists(FILE_PATH):
    print("❌ FILE NOT FOUND")
    exit()

try:
    with open(FILE_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    print(f"Total entries: {len(data)}")
    print("Available Keys:")
    for k in data.keys():
        print(f" - {k}")

except Exception as e:
    print(f"Error: {e}")
