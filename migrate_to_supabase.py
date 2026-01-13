"""
Script para migrar datos locales a Supabase
Ejecutar una vez para transferir historial_inscripciones.json a la nube
"""
import json
import os
import sys

# Add project to path
sys.path.insert(0, os.path.dirname(__file__))

def migrate_data():
    from supabase import create_client
    
    # Supabase credentials
    url = "https://tivjnlnbdyiekrlzcwvk.supabase.co"
    key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRpdmpubG5iZHlpZWtybHpjd3ZrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njc5MzMwMTAsImV4cCI6MjA4MzUwOTAxMH0.saIaphccwtgjZRmT5mIzkgXwE0rRB5Y67E5qM1Ui8Rg"
    
    client = create_client(url, key)
    
    # Load local data
    local_file = os.path.join(os.path.dirname(__file__), "historial_inscripciones.json")
    
    if not os.path.exists(local_file):
        print("❌ No se encontró historial_inscripciones.json")
        return
    
    with open(local_file, "r", encoding="utf-8") as f:
        history = json.load(f)
    
    print(f"📂 Encontradas {len(history)} sesiones para migrar")
    
    migrated = 0
    for name, session in history.items():
        try:
            # Clean data - replace NaN with None
            data = session.get("data", [])
            for row in data:
                for key_name, value in list(row.items()):
                    if isinstance(value, float) and str(value) == 'nan':
                        row[key_name] = None
            
            # Get columns from first row
            columns = list(data[0].keys()) if data else []
            
            # Upsert to Supabase
            record = {
                "name": name,
                "timestamp": session.get("timestamp"),
                "data": data,
                "columns": columns
            }
            
            client.table("inscripciones").upsert(record, on_conflict="name").execute()
            migrated += 1
            print(f"✅ Migrado: {name}")
            
        except Exception as e:
            print(f"❌ Error migrando {name}: {e}")
    
    print(f"\n🎉 Migración completada: {migrated}/{len(history)} sesiones")

if __name__ == "__main__":
    migrate_data()
