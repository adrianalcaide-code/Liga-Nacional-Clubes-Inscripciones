"""
Diagnostic script to trace save/load flow and identify issues.
Run from project root: python _debug_tools/trace_save.py
"""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.state import (
    load_history, 
    load_session_data, 
    save_current_session, 
    is_cloud_mode,
    init_db,
    DB_AVAILABLE
)
import pandas as pd
from datetime import datetime

print("=" * 60)
print("DIAGNÓSTICO DE PERSISTENCIA - FLUJO COMPLETO")
print("=" * 60)

# 1. Check Cloud Mode
print("\n[1] VERIFICANDO MODO DE ALMACENAMIENTO...")
if DB_AVAILABLE:
    init_db()
    cloud = is_cloud_mode()
    print(f"   ✅ DB_AVAILABLE = True")
    print(f"   ☁️ is_cloud_mode() = {cloud}")
else:
    print(f"   ❌ DB_AVAILABLE = False (operando en modo LOCAL)")

# 2. Load History
print("\n[2] CARGANDO HISTORIAL...")
history = load_history()
if history:
    print(f"   ✅ {len(history)} sesiones encontradas:")
    sorted_sessions = sorted(
        history.items(), 
        key=lambda x: x[1].get('timestamp', '') or '', 
        reverse=True
    )
    for name, meta in sorted_sessions[:5]:
        ts = meta.get('timestamp', '?')
        count = meta.get('count', '?')
        print(f"      - '{name}' | {ts} | {count} filas")
    
    # 3. Load latest session
    print("\n[3] CARGANDO SESIÓN MÁS RECIENTE...")
    latest_name = sorted_sessions[0][0]
    df = load_session_data(latest_name)
    if df is not None and not df.empty:
        print(f"   ✅ Sesión '{latest_name}' cargada: {len(df)} filas")
        
        # 4. Test SAVE
        print("\n[4] PROBANDO GUARDADO...")
        test_session_name = f"_diag_test_{datetime.now().strftime('%H%M%S')}"
        
        # Create a tiny test DF
        test_df = pd.DataFrame([{"Nº.ID": 99999, "Jugador": "TEST_PLAYER", "Pruebas": "TEST_TEAM"}])
        
        success, msg = save_current_session(test_session_name, test_df)
        print(f"   save_current_session('{test_session_name}', df)")
        print(f"   Resultado: success={success}, msg='{msg}'")
        
        # 5. Verify it was saved
        print("\n[5] VERIFICANDO GUARDADO...")
        history_after = load_history()
        if test_session_name in history_after:
            print(f"   ✅ La sesión '{test_session_name}' ESTÁ en el historial")
            
            # 6. Load it back
            df_reloaded = load_session_data(test_session_name)
            if df_reloaded is not None and not df_reloaded.empty:
                print(f"   ✅ Sesión recargada: {len(df_reloaded)} filas")
                if "TEST_PLAYER" in str(df_reloaded['Jugador'].values):
                    print(f"   ✅ Datos COINCIDEN (TEST_PLAYER encontrado)")
                else:
                    print(f"   ❌ Datos NO coinciden!")
                    print(f"      Esperado: TEST_PLAYER")
                    print(f"      Encontrado: {df_reloaded['Jugador'].values}")
            else:
                print(f"   ❌ ERROR: Sesión recargada está vacía o es None")
        else:
            print(f"   ❌ La sesión '{test_session_name}' NO está en el historial!")
            print(f"      Claves disponibles: {list(history_after.keys())}")
    else:
        print(f"   ❌ ERROR al cargar '{latest_name}'")
else:
    print(f"   ⚠️ Historial vacío - no hay sesiones guardadas")

print("\n" + "=" * 60)
print("FIN DEL DIAGNÓSTICO")
print("=" * 60)
