"""
Script de corrección de encoding (mojibake) en datos almacenados.
SEGURIDAD: Crea backups antes de cualquier modificación.

Autor: Antigravity Assistant
Fecha: 2026-01-20
"""

import json
import os
import shutil
from datetime import datetime
import sys

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(BASE_DIR, "historial_inscripciones.json")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")

def fix_mojibake(text):
    """Fix double encoding issues (UTF-8 read as Latin-1)."""
    if text is None:
        return text
    if not isinstance(text, str):
        return text
    try:
        # Try to decode: encode as Latin-1, decode as UTF-8
        fixed = text.encode('latin-1').decode('utf-8')
        return fixed
    except (UnicodeDecodeError, UnicodeEncodeError):
        # Already correct or different issue
        return text

def fix_dict_encoding(obj, fields_to_fix=None):
    """Recursively fix encoding in dict/list structures."""
    if fields_to_fix is None:
        fields_to_fix = ['Club', 'Pruebas', 'Nombre', 'Nombre.1', 'País', 'Equipo', 
                         'club', 'pruebas', 'nombre', 'pais', 'equipo']
    
    if isinstance(obj, dict):
        return {k: fix_dict_encoding(v, fields_to_fix) if k in fields_to_fix or isinstance(v, (dict, list)) 
                else (fix_mojibake(v) if k in fields_to_fix else v)
                for k, v in obj.items()}
    elif isinstance(obj, list):
        return [fix_dict_encoding(item, fields_to_fix) for item in obj]
    elif isinstance(obj, str):
        return fix_mojibake(obj)
    else:
        return obj

def create_backup(file_path, backup_dir):
    """Create a timestamped backup of a file."""
    if not os.path.exists(file_path):
        return None
    
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.basename(file_path)
    backup_path = os.path.join(backup_dir, f"{timestamp}_{filename}")
    
    shutil.copy2(file_path, backup_path)
    return backup_path

def count_records(data):
    """Count total records in the JSON structure."""
    total = 0
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, dict) and 'data' in value:
                if isinstance(value['data'], list):
                    total += len(value['data'])
    return total

def find_mojibake_examples(data, max_examples=10):
    """Find examples of mojibake patterns in the data."""
    examples = []
    mojibake_patterns = ['Ã¡', 'Ã©', 'Ã­', 'Ã³', 'Ãº', 'Ã±', 'Ã', 'Â']
    
    def search(obj, path=""):
        if len(examples) >= max_examples:
            return
        if isinstance(obj, dict):
            for k, v in obj.items():
                search(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj[:50]):  # Limit to first 50 items
                search(item, f"{path}[{i}]")
        elif isinstance(obj, str):
            for pattern in mojibake_patterns:
                if pattern in obj:
                    fixed = fix_mojibake(obj)
                    if fixed != obj:
                        examples.append((path, obj, fixed))
                    break
    
    search(data)
    return examples

def main():
    print("=" * 60)
    print("SCRIPT DE CORRECCIÓN DE ENCODING (MOJIBAKE)")
    print("=" * 60)
    print()
    
    # 1. CHECK JSON EXISTS
    if not os.path.exists(JSON_PATH):
        print(f"❌ ERROR: No se encontró el archivo {JSON_PATH}")
        return False
    
    print(f"📁 Archivo encontrado: {JSON_PATH}")
    
    # 2. LOAD JSON
    print("\n📖 Cargando datos...")
    try:
        with open(JSON_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ ERROR al cargar JSON: {e}")
        return False
    
    # 3. COUNT RECORDS BEFORE
    records_before = count_records(data)
    sessions_count = len([k for k in data.keys() if not k.startswith('_')])
    print(f"📊 Sesiones encontradas: {sessions_count}")
    print(f"📊 Registros totales: {records_before}")
    
    # 4. FIND MOJIBAKE EXAMPLES
    print("\n🔍 Buscando ejemplos de encoding corrupto...")
    examples = find_mojibake_examples(data)
    
    if not examples:
        print("✅ No se encontraron problemas de encoding. Los datos están correctos.")
        return True
    
    print(f"⚠️  Encontrados {len(examples)} ejemplos de encoding corrupto:")
    for path, original, fixed in examples[:5]:
        print(f"   '{original}' → '{fixed}'")
    
    # 5. CREATE BACKUP
    print("\n💾 Creando backup de seguridad...")
    backup_path = create_backup(JSON_PATH, BACKUP_DIR)
    if backup_path:
        print(f"✅ Backup creado: {backup_path}")
    else:
        print("❌ ERROR: No se pudo crear backup")
        return False
    
    # 6. FIX ENCODING
    print("\n🔧 Corrigiendo encoding...")
    fixed_data = fix_dict_encoding(data)
    
    # 7. VERIFY RECORD COUNT
    records_after = count_records(fixed_data)
    if records_before != records_after:
        print(f"❌ ERROR: Cantidad de registros cambió! Antes: {records_before}, Después: {records_after}")
        print("   No se guardarán los cambios. Restaura desde el backup si es necesario.")
        return False
    
    print(f"✅ Verificación: {records_after} registros (sin cambios en cantidad)")
    
    # 8. SAVE FIXED JSON
    print("\n💾 Guardando datos corregidos...")
    try:
        with open(JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(fixed_data, f, ensure_ascii=False, indent=2)
        print(f"✅ Archivo guardado: {JSON_PATH}")
    except Exception as e:
        print(f"❌ ERROR al guardar: {e}")
        return False
    
    # 9. VERIFY AFTER SAVE
    print("\n🔍 Verificando corrección...")
    examples_after = find_mojibake_examples(fixed_data)
    if not examples_after:
        print("✅ Todos los problemas de encoding han sido corregidos.")
    else:
        print(f"⚠️  Aún quedan {len(examples_after)} ejemplos. Pueden requerir revisión manual.")
    
    print("\n" + "=" * 60)
    print("✅ CORRECCIÓN COMPLETADA")
    print(f"   Backup disponible en: {backup_path}")
    print("=" * 60)
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
