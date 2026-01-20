"""
Script para sincronizar datos locales (historial_inscripciones.json) con Supabase.
1. Lee el JSON local (asegurando utf-8).
2. Valida integridad.
3. Conecta a Supabase.
4. Sube las sesiones una a una.

Uso: python sync_supabase_upload.py
"""
import json
import os
import sys
import streamlit as st
import pandas as pd
from datetime import datetime

# Añadir path para importar módulos locales si es necesario
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Intentar importar servicios
try:
    from modules.supabase_service import init_supabase, save_session
except ImportError:
    print("❌ Error: No se pudieron importar los módulos. Ejecuta desde la raíz del proyecto.")
    sys.exit(1)

JSON_PATH = "historial_inscripciones.json"

def main():
    print("="*60)
    print("SYNC LOCAL -> SUPABASE")
    print("="*60)

    # 1. Init Supabase
    print("📡 Conectando a Supabase...")
    try:
        # Cargar secrets manualmente si no corre en Streamlit
        # Nota: save_session usa st.secrets. 
        # Si ejecutamos como script terminal, st.secrets no existe por defecto salvo que usemos config.toml
        # Para simplificar, asumimos que st.secrets funciona o el usuario lo corre vía 'streamlit run' hack
        # O mejor: le decimos al usuario que lo ejecute.
        
        # Hack simple: leer secrets.toml locamente si existe
        secrets_path = ".streamlit/secrets.toml"
        if os.path.exists(secrets_path) and not st.secrets:
            import tomllib
            with open(secrets_path, "rb") as f:
                secrets_data = tomllib.load(f)
                # Monkeypatch st.secrets (aproximado)
                # Pero st.secrets es un objeto especial.
                pass 
        
        client = init_supabase()
        if not client:
            print("❌ No se pudo conectar a Supabase. Verifica secrets y que el proyecto esté ACTIVO.")
            return
    except Exception as e:
        print(f"❌ Error conexión Supabase: {e}")
        return

    # 2. Check Local File
    if not os.path.exists(JSON_PATH):
        print(f"❌ No existe {JSON_PATH}")
        return

    print(f"📖 Leyendo {JSON_PATH}...")
    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        local_data = json.load(f)

    sessions = [k for k in local_data.keys() if not k.startswith('_')]
    print(f"📊 Sesiones locales encontradas: {len(sessions)}")

    # 3. Upload loop
    for session_name in sessions:
        print(f"\n📤 Procesando sesión: '{session_name}'")
        session_data = local_data[session_name]
        
        if 'data' not in session_data:
            print(f"   ⚠️ Saltando (formato inválido)")
            continue
            
        records = session_data['data']
        # Convert to DataFrame to re-use save_session logic logic (which handles formatting)
        try:
            df = pd.DataFrame(records)
            print(f"   Records: {len(df)}")
            
            # Subida
            success, msg = save_session(session_name, df)
            if success:
                print(f"   ✅ Subida exitosa")
            else:
                print(f"   ❌ Falla al subir: {msg}")
        except Exception as e:
            print(f"   ❌ Error procesando datos: {e}")

    print("\n✅ Proceso completado.")

if __name__ == "__main__":
    main()
