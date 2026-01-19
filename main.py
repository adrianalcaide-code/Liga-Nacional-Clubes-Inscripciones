import streamlit as st
import pandas as pd
import io
import os
import json
import plotly.express as px
from datetime import datetime
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode
import time
import importlib
import data_processing
import license_validator
import rules_manager

# FORCE RELOAD to avoid stale code on network drive (since fileWatcher is disabled)
importlib.reload(data_processing)
importlib.reload(license_validator)
importlib.reload(rules_manager)

from data_processing import (
    load_data, 
    process_dataframe, 
    generate_players_csv, 
    generate_team_players_csv,
    calculate_team_compliance,
    apply_comprehensive_check,
    merge_dataframes_with_log
)
from license_validator import validator, FESBA_LOGIN_URL
from rules_manager import RulesManager
import logging
from pathlib import Path

# ==================== CONFIGURACIÓN DE RUTAS ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")

if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# Generar nombre de log con fecha/hora para historial
log_filename = f"validacion_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
LOG_FILE = os.path.join(LOG_DIR, log_filename)

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ],
    force=True
)
logger = logging.getLogger(__name__)

# Inicializar Gestor de Reglas
rules_manager = RulesManager()

# Configuración de la página (Full Screen)
st.set_page_config(
    page_title="LNC Dashboard Pro",
    page_icon="🏸",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS Personalizado para Look & Feel Profesional
st.markdown("""
<style>
    /* Fuente y colores generales */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    /* Encabezado Principal */
    .main-header {
        background: linear-gradient(90deg, #E21E2D 0%, #9D0E1B 100%);
        padding: 1.5rem 2rem;
        border-radius: 10px;
        color: white;
        margin-bottom: 2rem;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .main-header h1 {
        color: white !important;
        margin: 0;
        font-weight: 800;
        font-size: 2.2rem;
    }
    .main-header p {
        color: #f0f0f0;
        margin-top: 0.5rem;
        font-size: 1rem;
    }

    /* Tarjetas de Métricas */
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        padding: 15px;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        transition: transform 0.2s;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    }
    
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: #fff;
        border-radius: 4px 4px 0 0;
        gap: 1px;
        padding-top: 10px;
        padding-bottom: 10px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #fff;
        border-bottom: 3px solid #E21E2D;
        color: #E21E2D;
        font-weight: 600;
    }
    
    /* Alertas Custom */
    .stAlert {
        padding: 0.5rem;
        border-radius: 5px;
    }

</style>
""", unsafe_allow_html=True)

# --- Header Visual ---
st.markdown("""
<div class="main-header">
    <h1>🏸 Liga Nacional de Clubes - Control Integral</h1>
    <p>Plataforma de validación federativa, auditoría normativa y gestión de expedientes.</p>
</div>
""", unsafe_allow_html=True)

# --- Funciones de Utilidad ---
# --- Funciones de Utilidad ---
from modules.state import (
    load_history,
    save_history,
    save_current_session,
    delete_session,
    rename_session,
    rename_session,
    rename_session,
    PERSISTENCE_FILE,
    load_session_data
)
from modules.settings import SettingsManager

# Inicializar Gestor de Configuración
settings_manager = SettingsManager()

# ==================== AUTO-LOAD DEFAULT SESSION ====================
# Automatically load the saved session on startup if no data is loaded
# ==================== AUTO-LOAD LAST SESSION ====================
# Automatically load the most recent session on startup
BACKUP_FILE = os.path.join(BASE_DIR, "backup_session.json")

if 'data' not in st.session_state or st.session_state['data'] is None:
    # 1. Try to load latest from History (Supabase or Local)
    try:
        history = load_history()
        if history:
            # Sort by timestamp descending
            sorted_sessions = sorted(
                history.items(), 
                key=lambda x: x[1].get('timestamp', '') or '', 
                reverse=True
            )
            
            if sorted_sessions:
                latest_name = sorted_sessions[0][0]
                latest_meta = sorted_sessions[0][1]
                logger.info(f"Found latest session: {latest_name} ({latest_meta.get('timestamp')})")
                
                # Load it
                with st.spinner(f"Cargando última sesión: {latest_name}..."):
                    df_loaded = load_session_data(latest_name)
                
                if df_loaded is not None and not df_loaded.empty:
                    # Process and set state
                    df = process_dataframe(df_loaded)
                    
                    # Load rules & calc compliance
                    rules_config = rules_manager.load_rules()
                    team_categories = rules_manager.load_team_categories()
                    calculate_team_compliance(df, rules_config, team_categories) 
                    df = apply_comprehensive_check(df, rules_config, team_categories)
                    
                    st.session_state['data'] = df
                    st.session_state['current_file_key'] = latest_name
                    st.toast(f"✅ Sesión restaurada: {latest_name}", icon="🔄")
                else:
                    st.warning(f"No se pudo restaurar '{latest_name}'. Intentando backup local...")
                    raise Exception("Latest session load failed")
            else:
                 raise Exception("History empty")
        else:
             raise Exception("No history returned")

    except Exception as e:
        logger.warning(f"Auto-load from history failed ({e}). Falling back to backup_session.json")
        
        # 2. Fallback to static backup file
        if os.path.exists(BACKUP_FILE):
            try:
                with open(BACKUP_FILE, 'r', encoding='utf-8') as f:
                    backup_data = json.load(f)
                
                data_list = backup_data.get("data", [])
                if data_list:
                    df = pd.DataFrame(data_list)
                    df = process_dataframe(df)
                    
                    # Logic
                    rules_config = rules_manager.load_rules()
                    team_categories = rules_manager.load_team_categories()
                    calculate_team_compliance(df, rules_config, team_categories)
                    df = apply_comprehensive_check(df, rules_config, team_categories)
                    
                    st.session_state['data'] = df
                    st.session_state['current_file_key'] = "Respaldo_Local"
                    st.toast("⚠️ Restaurado desde copia de seguridad local (Supabase no disponible)", icon="💾")
            except Exception as ex:
                logger.error(f"Critical: Backup file load failed: {ex}")

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_export = df.copy()
        if 'Errores_Datos' in df_export.columns:
             df_export['Errores_Datos'] = df_export['Errores_Datos'].apply(lambda x: ", ".join(x) if isinstance(x, list) else x)
        df_export.to_excel(writer, index=False, sheet_name='Revision')
    processed_data = output.getvalue()
    return processed_data

# --- Sidebar ---
with st.sidebar:
    st.image("https://www.badminton.es/images/style/fesba/logo.png", width=200) 
    st.header("📁 Gestor de Archivos")
    
    uploaded_file = st.file_uploader("Cargar Archivo Excel", type=["xlsx"], help="Sube una inscripción inicial o un archivo adicional para añadir jugadores.")
    
    history = load_history()
    # DEBUG
    # st.write(f"Ruta Historial: {PERSISTENCE_FILE}")
    # st.write(f"Archivos encontrados: {len(history)}")
    
    file_options = list(history.keys())
    selected_file = st.selectbox("🗃️ Archivos Cargados", options=["-- Seleccionar --"] + file_options, index=0)
    
    # LOGICA DE CARGA PRINCIPAL (SOLO BASE)
    if uploaded_file is not None:
        # Si se sube un archivo aquí, se asume que es para CARGAR/REEMPLAZAR la base
        if 'data' in st.session_state and st.session_state['data'] is not None and not st.session_state['data'].empty:
             st.warning("⚠️ Ya hay datos cargados. Si continúas, se reemplazarán.")
             if st.button("🆕 Reemplazar con este archivo"):
                 st.session_state['last_uploaded'] = None 
                 # El bloque principal manejará la carga
                 st.rerun()
        else:
            pass # Pasa al bloque principal de carga

    col_s1, col_s2 = st.columns(2)
    if selected_file != "-- Seleccionar --":
        # --- RENOMBRAR ARCHIVO ---
        with st.expander("✏️ Renombrar Archivo"):
            new_name = st.text_input("Nuevo nombre:", value=selected_file)
            if st.button("Guardar Nombre"):
                if new_name and new_name != selected_file:
                    if new_name in history:
                        st.error("Ya existe un archivo con ese nombre.")
                    else:
                        # Renombrar en historial
                        if rename_session(selected_file, new_name):
                            st.session_state['current_file_key'] = new_name
                            st.success("Renombrado correctamente.")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error("Error al guardar cambios.")

        if col_s1.button("Cargar"):
            st.session_state['current_file_key'] = selected_file
            # Usar load_session_data para soportar modo Cloud (lazy loading)
            with st.spinner("Cargando archivo..."):
                df_loaded = load_session_data(selected_file)
                
            if df_loaded is not None and not df_loaded.empty:
                st.session_state['data'] = df_loaded
                st.toast(f"✅ Archivo '{selected_file}' cargado", icon="📂")
                time.sleep(0.5)
                st.rerun()
            else:
                if df_loaded is None:
                    st.error("Error: El sistema devolvió 'None' (Archivo corrupto o clave no encontrada).")
                    st.code(f"DEBUG INFO: File='{selected_file}'")
                elif df_loaded.empty:
                     st.error("Error: El archivo está vacío (0 filas explícitas).")
                else:
                    st.error("Error desconocido al cargar.")
        if col_s2.button("🗑️"):
            delete_session(selected_file)
            st.rerun()

    st.divider()
    
    # --- MODO DE ALMACENAMIENTO ---
    try:
        from modules.state import get_storage_mode
        storage_mode = get_storage_mode()
    except:
        storage_mode = "💾 Local"
    st.info(f"**Modo:** {storage_mode} | v3.0")

    # --- ESTADO DEL SISTEMA ---
    with st.sidebar.expander("🖥️ Estado del Sistema", expanded=True):
        # Modo de almacenamiento
        st.markdown(f"**Almacenamiento:** {storage_mode}")
        st.divider()
        
        # Estado DB Licencias
        if 'license_validator' in st.session_state and st.session_state['license_validator'].licenses_db:
            db_count = len(st.session_state['license_validator'].licenses_db)
            last_upd = st.session_state['license_validator'].last_update_timestamp
            last_upd_str = last_upd.strftime("%d/%m %H:%M") if last_upd else "?"
            st.markdown(f"🟢 **DB Licencias:** {db_count} registros")
            st.caption(f"Actualizado: {last_upd_str}")
        else:
            st.markdown("🔴 **DB Licencias:** Desconectada")
            
        # Configuración Actual
        current_fuzzy = settings_manager.get("fuzzy_threshold", 0.80)
        st.markdown(f"⚙️ **Fuzzy Threshold:** {current_fuzzy}")
        
        # Cache
        if st.button("🧹 Limpiar Caché", help="Si notas datos antiguos, pulsa aquí"):
            st.cache_data.clear()
            st.success("Caché limpiado")
            time.sleep(1)
            st.rerun()
        
        # Versión
        st.divider()
        st.caption("LNC Pro v3.0 Cloud | © 2025-2026")

    st.sidebar.divider()
    



    # --- SECCIÓN: AÑADIR JUGADOR MANUAL ---
    with st.expander("➕ Añadir Jugadores Manualmente"):
        st.write("Introduce el Nº ID y Equipo. Los datos se completarán automáticamente desde la base de datos de licencias cargada.")
        
        # Formulario dinámico (Data Editor)
        if 'manual_add_data' not in st.session_state:
            st.session_state['manual_add_data'] = pd.DataFrame([{"Nº.ID": "", "Equipo": ""}])
            
        manual_df = st.data_editor(
            st.session_state['manual_add_data'],
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Nº.ID": st.column_config.TextColumn("Nº Licencia (ID)", required=True),
                "Equipo": st.column_config.TextColumn("Equipo Destino", required=True)
            },
            key="manual_editor"
        )
        
        if st.button("Procesar Añadidos"):
            if 'data' not in st.session_state or st.session_state['data'] is None:
                st.error("Primero carga un archivo base o crea uno vacío.")
            else:
                current_df = st.session_state['data']
                # Acceder al validador para buscar datos
                if 'license_validator' not in st.session_state:
                    st.session_state['license_validator'] = validator
                val_instance = st.session_state['license_validator']
                
                count_added = 0
                new_rows = []
                
                for _, row in manual_df.iterrows():
                    raw_id = str(row.get("Nº.ID", "")).strip()
                    team = str(row.get("Equipo", "")).strip()
                    
                    if not raw_id or not team: continue
                    
                    # 0. BUSCAR INFO EN DB (Siempre)
                    info = None
                    try:
                        pid = int(raw_id)
                        info = val_instance.licenses_db.get(pid)
                    except:
                        pass # info stays None

                    # Datos extraídos o placeholders
                    is_foreign = False
                    if info:
                        nombre_completo = info.get('name', 'Desconocido')
                        parts = nombre_completo.split()
                        if len(parts) >= 3:
                            nombre = parts[0]
                            apellido1 = parts[1]
                            apellido2 = " ".join(parts[2:])
                        elif len(parts) == 2:
                            nombre = parts[0]
                            apellido1 = parts[1]
                            apellido2 = ""
                        else:
                            nombre = nombre_completo
                            apellido1, apellido2 = "", ""
                            
                        sexo = info.get('gender', '')
                        dob = info.get('dob', '')
                        club_origen = info.get('club', '')
                        # Get country from DB (defaults to España if not set)
                        pais = info.get('country', 'España')
                        # Check if foreign (not Spain/España)
                        pais_upper = pais.upper().strip()
                        is_foreign = pais_upper not in ['SPAIN', 'ESPAÑA', 'ESP', 'ES', '']
                        data_source = "FESBA DB"
                    else:
                        nombre = f"Manual-{raw_id}"
                        apellido1, apellido2, nombre_completo = "?", "?", "?"
                        sexo, dob, club_origen, pais = "?", "?", "?", "?"
                        data_source = "MANUAL (NO DB)"
                        if not info: st.warning(f"⚠️ ID {raw_id} no encontrado en BBDD FESBA. Se usarán datos vacíos.")

                    # 1. VERIFICAR SI YA EXISTE (UPDATE)
                    existing_mask = current_df['Nº.ID'].astype(str) == raw_id
                    if existing_mask.any():
                        idx = current_df[existing_mask].index[0]
                        
                        # Update Personal Info (Always refresh from DB)
                        if info:
                            current_df.at[idx, 'Nombre'] = apellido1
                            current_df.at[idx, '2ºNombre'] = apellido2
                            current_df.at[idx, 'Nombre.1'] = nombre
                            current_df.at[idx, 'F.Nac'] = dob
                            current_df.at[idx, 'Género'] = sexo
                            current_df.at[idx, 'País'] = pais
                            current_df.at[idx, 'Club'] = club_origen

                        current_team = str(current_df.at[idx, 'Pruebas']).strip()
                        current_notes = str(current_df.at[idx, 'Notas_Revision'] if 'Notas_Revision' in current_df.columns else "")
                        
                        # Update Team
                        note_parts = []
                        if current_team != team:
                            current_df.at[idx, 'Pruebas'] = team
                            note_parts.append(f"Cambio Equipo: {current_team}->{team}")
                            st.toast(f"✅ Jugador {raw_id}: Equipo actualizado a {team}")
                        
                        if info:
                            note_parts.append("Datos frescos de FESBA")
                            st.toast(f"✅ Jugador {raw_id}: Datos personales actualizados")

                        # Append notes
                        if note_parts:
                            new_note_text = " | ".join(note_parts)
                            if current_notes and current_notes != "nan":
                                final_note = f"{current_notes} | {new_note_text}" 
                            else:
                                final_note = new_note_text
                            current_df.at[idx, 'Notas_Revision'] = final_note
                            
                        count_added += 1 # Count update as processed
                        continue

                    # 2. CREAR NUEVO (INSERT)
                    new_row = {
                        "Nº.ID": raw_id,
                        "Club": club_origen,
                        "Nombre": apellido1,
                        "2ºNombre": apellido2,
                        "Nombre.1": nombre,
                        "F.Nac": dob,
                        "Género": sexo,
                        "País": pais,
                        "Pruebas": team,
                        "Es_Cedido": False,
                        "No_Seleccionable": is_foreign,  # Auto-mark if foreign
                        "Datos_Validos": True,
                        "Errores_Datos": [],
                        "Estado": "Nuevo Manual" + (" (Extranjero)" if is_foreign else ""),
                        "Documentacion_OK": False,
                        "Declaración_Jurada": False,
                        "Documento_Cesión": False,
                        "Notas_Revision": f"Añadido Manualmente ({data_source})" + (f" | País: {pais}" if is_foreign else ""),
                        "Errores_Normativos": "",
                        "Validacion_FESBA": ""
                    }
                    new_rows.append(new_row)
                    count_added += 1
                
                if new_rows:
                    # Convertir a DF y procesar
                    df_new_manual = pd.DataFrame(new_rows)
                    # Fusionar
                    current_df = pd.concat([current_df, df_new_manual], ignore_index=True)
                
                # RECALCULAR SIEMPRE si hubo cambios (insert o update)
                if count_added > 0:
                    st.write("🔄 Recalculando estado y validaciones...")
                    # Re-procesar para calcular campos calculados
                    current_eq = rules_manager.load_equivalences()
                    fuzzy_th = settings_manager.get("fuzzy_threshold", 0.80)
                    current_df = process_dataframe(current_df, equivalences=current_eq, fuzzy_threshold=fuzzy_th)

                    st.success(f"Procesados {count_added} cambios (Añadidos/Actualizados).")
                    
                    # CRITICAL: Update session_state with new data BEFORE saving
                    st.session_state['data'] = current_df
                    
                    # Guardar
                    current_key = st.session_state.get('current_file_key', 'manual')
                    success, msg = save_current_session(current_key, current_df)
                    if success:
                        st.session_state['manual_add_data'] = pd.DataFrame([{"Nº.ID": "", "Equipo": ""}])
                        # Force widget reset
                        if 'manual_editor' in st.session_state:
                            del st.session_state['manual_editor']
                        
                        st.toast(f"✅ {count_added} jugador(es) añadido(s)/actualizado(s)")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(f"Error al guardar: {msg}")
                else:
                    st.warning("No se detectaron cambios (quizás ya existían sin modificación).")

    # --- SECCIÓN: IMPORTAR / ACTUALIZAR DESDE EXCEL ---
    with st.expander("📥 Importar / Actualizar desde Excel"):
        st.write("Sube un Excel con nuevos jugadores o cambios de equipo. El sistema fusionará los datos.")
        
        import_file = st.file_uploader("Subir Excel de Actualización", type=["xlsx"], key="import_uploader")
        
        if import_file is not None:
            if st.button("🔄 Procesar Importación"):
                if 'data' not in st.session_state or st.session_state['data'] is None:
                    st.error("Primero carga un archivo base.")
                else:
                    with st.status("Procesando importación...", expanded=True) as status:
                        st.write("📂 Leyendo archivo Excel...")
                        logger.info(f"Importando archivo: {import_file.name}")
                        df_new = load_data(import_file)
                        
                        if df_new is not None:
                            st.write("🧠 Aplicando lógica de negocio...")
                            current_df = st.session_state['data']
                            current_eq = rules_manager.load_equivalences()
                            fuzzy_th = settings_manager.get("fuzzy_threshold", 0.80)
                            
                            # Procesar el nuevo DF
                            df_new_processed = process_dataframe(df_new, equivalences=current_eq, fuzzy_threshold=fuzzy_th)
                            
                            st.write("🔄 Fusionando datos...")
                            # Fusión
                            current_df, merge_logs = merge_dataframes_with_log(current_df, df_new_processed)
                            
                            # Actualizar Estado
                            st.session_state['data'] = current_df
                            current_key = st.session_state.get('current_file_key', 'fusionado')
                            
                            success, error_msg = save_current_session(current_key, current_df)
                            
                            if success:
                                # Guardar logs
                                st.session_state['merge_logs'] = merge_logs
                                status.update(label="¡Importación y Guardado Completados!", state="complete", expanded=False)
                                st.success(f"Datos fusionados y guardados correctamente en: {current_key}")
                                time.sleep(1)
                                st.rerun()
                            else:
                                status.update(label="Error al Guardar", state="error")
                                st.error(f"❌ Error al guardar datos en Supabase: {error_msg}")
                                logger.error(f"Fallo guardado datos: {error_msg}")

        # MOSTRAR LOGS DE FUSIÓN SI EXISTEN (Aquí es el mejor sitio)
        if 'merge_logs' in st.session_state and st.session_state['merge_logs']:
            st.divider()
            st.markdown("##### 📜 Informe de Última Importación")
            for log in st.session_state['merge_logs']:
                st.markdown(log)
            if st.button("Limpiar Informe", key="clean_logs_btn"):
                del st.session_state['merge_logs']
                st.rerun()


# --- Lógica Principal ---

# Caso A: Subida de NUEVO archivo (Reemplazo o Carga Inicial)
if uploaded_file is not None:
    # Solo cargar si no hay datos O si se forzó el reemplazo (last_uploaded borrado)
    should_load = 'last_uploaded' not in st.session_state or st.session_state['last_uploaded'] != uploaded_file.name
    # Y ademas si NO estamos en modo fusión (si hay datos y no se dio click a nada, esperamos)
    # Simplificación: Si no hay datos en session, cargamos.
    if 'data' not in st.session_state or st.session_state['data'] is None or st.session_state['data'].empty:
        if should_load:
            with st.status("Cargando archivo...", expanded=True) as status:
                logger.info(f"Cargando nuevo archivo: {uploaded_file.name}")
                st.write("📂 Leyendo Excel...")
                df_fresh = load_data(uploaded_file)
                
                # VALIDACIÓN DE COLUMNAS CRÍTICAS
                required_cols = ['Nº.ID', 'Nombre', 'Club', 'Pruebas']
                missing = [c for c in required_cols if c not in df_fresh.columns]
                
                if missing:
                    status.update(label="Error de formato", state="error")
                    st.error(f"❌ El archivo no tiene el formato correcto. Faltan las columnas: {', '.join(missing)}")
                    st.stop()
                    
                if df_fresh is not None:
                    st.write("⚙️ Procesando reglas y normativa...")
                    current_eq = rules_manager.load_equivalences()
                    # Usar valor guardado en settings
                    fuzzy_th = settings_manager.get("fuzzy_threshold", 0.80)
                    st.session_state['fuzzy_threshold'] = fuzzy_th
                    
                    df_processed = process_dataframe(df_fresh, equivalences=current_eq, fuzzy_threshold=fuzzy_th)
                    if 'Notas_Revision' not in df_processed.columns: df_processed['Notas_Revision'] = ""
                    
                    st.write("💾 Guardando sesión...")
                    success, msg = save_current_session(uploaded_file.name, df_processed)
                    if not success:
                        st.error(f"Error al guardar en Supabase: {msg}")
                        st.stop()
                    st.session_state['data'] = df_processed
                    st.session_state['current_file_key'] = uploaded_file.name
                    st.session_state['last_uploaded'] = uploaded_file.name
                    
                    status.update(label="¡Carga completada!", state="complete", expanded=False)
                    time.sleep(0.5)
                    st.rerun()
    elif should_load and st.session_state.get('last_uploaded') is None: 
         # Caso Reemplazo forzado desde sidebar
         logger.info(f"Reemplazando con archivo: {uploaded_file.name}")
         df_fresh = load_data(uploaded_file)
         if df_fresh is not None:
            current_eq = rules_manager.load_equivalences()
            fuzzy_th = st.session_state.get('fuzzy_threshold', 0.80)
            df_processed = process_dataframe(df_fresh, equivalences=current_eq, fuzzy_threshold=fuzzy_th)
            if 'Notas_Revision' not in df_processed.columns: df_processed['Notas_Revision'] = ""
            
            success, msg = save_current_session(uploaded_file.name, df_processed)
            if not success: st.error(f"Error al reemplazar: {msg}")
            st.session_state['data'] = df_processed
            st.session_state['current_file_key'] = uploaded_file.name
            st.session_state['last_uploaded'] = uploaded_file.name
            st.rerun()


# Caso B: Trabajo con archivo activo
if 'data' in st.session_state and st.session_state['data'] is not None:
    df = st.session_state['data']
    
    # Backward compatibility: Ensure new columns exist
    if 'Es_Excluido' not in df.columns:
        df['Es_Excluido'] = False
    if 'Errores_Normativos' not in df.columns:
        df['Errores_Normativos'] = ""
    current_name = st.session_state.get('current_file_key', 'Sin Título')
    
    # Cargar configuraciones globales
    rules_config = rules_manager.load_rules()
    equivalences = rules_manager.load_equivalences()
    team_categories = rules_manager.load_team_categories()
    LIGA_CATEGORIES = rules_manager.get_categories_list()
    
    # Detectar nuevos equipos
    all_teams = sorted(df['Pruebas'].dropna().astype(str).unique())
    new_teams = False
    for team in all_teams:
        if team not in team_categories:
            team_categories[team] = "Sin Asignar"
            new_teams = True
    if new_teams:
        rules_manager.save_team_categories(team_categories)

    # Calcular Cumplimiento (Auditoría Dinámica)
    compliance_df = calculate_team_compliance(df, rules_config, team_categories)

    # Aplicar Chequeo Individual Exhaustivo (Para poblar columna 'Errores_Normativos')
    # Esto asegura que el sombreado/error aparezca
    df = apply_comprehensive_check(df, rules_config, team_categories)

    st.caption(f"Editando: **{current_name}**")

    # --- DASHBOARD DE MÉTRICAS ---
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total Inscritos", len(df), "Jugadores")
    m2.metric("Equipos", df['Pruebas'].nunique(), "Clubes")
    m3.metric("Cedidos", int(float(df['Es_Cedido'].sum())), "Alertas", delta_color="off")
    
    # Errores Normativos Totales (Cualquier fila con texto en Errores_Normativos)
    normative_errors = int((df['Errores_Normativos'] != "").sum())
    m4.metric("Incidencias Normativas", normative_errors, "Jugadores Afectados", delta_color="inverse" if normative_errors > 0 else "normal")
    
    data_errors = int((~df['Datos_Validos']).sum())
    m5.metric("Errores Datos", data_errors, "Datos Faltantes", delta_color="inverse" if data_errors > 0 else "normal")
    st.divider()

    # --- PESTAÑAS ---
    tab_revision, tab_config, tab_incidencias, tab_export = st.tabs([
        "🔍 Centro de Revisión Integral", 
        "⚙️ Configuración Avanzada",
        "⚠️ Incidencias", 
        "📤 Exportar"
    ])

    # 1. CENTRO DE REVISIÓN INTEGRAL
    with tab_revision:
        col_rev_left, col_rev_right = st.columns([3, 1])
        
        with col_rev_left:
            st.subheader("Gestión de Licencias y Normativa")
            
            # BUSCADOR GENERAL
            search_query = st.text_input("🔍 Buscar por Nombre, Equipo o ID:", placeholder="Escribe para buscar...").strip()
            
            # FILTROS
            c_f1, c_f2, c_f3 = st.columns(3)
            cats_avail = ["Todas"] + LIGA_CATEGORIES + ["Sin Asignar"]
            sel_cat = c_f1.selectbox("Filtrar por Categoría:", cats_avail)
            
            if sel_cat != "Todas":
                teams_in_cat = [t for t, c in team_categories.items() if c == sel_cat and t in all_teams]
            else:
                teams_in_cat = all_teams
            sel_team = c_f2.selectbox("Filtrar por Equipo:", ["Todos"] + teams_in_cat)
            
            lic_status_opts = ["Todos", "✅ Licencia OK", "❌ Licencia Incorrecta", "Pendiente de Revisión", "⛔ Con Incidencias"]
            sel_lic_status = c_f3.selectbox("Estado Licencia/Normativa:", lic_status_opts)
            
            # NUEVOS FILTROS (Cedidos y No Seleccionables)
            c_f4, c_f5, c_f6 = st.columns(3)
            sel_cedido = c_f4.selectbox("Filtro Cedidos:", ["Todos", "Sí", "No"])
            sel_no_sel = c_f5.selectbox("Filtro No Seleccionables:", ["Todos", "Sí", "No"])
            sel_excluido = c_f6.selectbox("Filtro Excluidos:", ["Ocultar Excluidos", "Ver Todos", "Solo Excluidos"])

            # --- RESUMEN DE EQUIPO SELECCIONADO (AUDITORÍA EN CONTEXTO) ---
            if sel_team != "Todos":
                team_audit_rows = compliance_df[compliance_df['Equipo'] == sel_team]
                if not team_audit_rows.empty:
                    team_audit = team_audit_rows.iloc[0]
                    audit_color = "success" if team_audit['Estado General'] == '✅ APTO' else "error"
                    with st.container():
                        st.markdown(f"""
                        <div style="padding: 1rem; border: 1px solid #ddd; border-radius: 8px; background-color: #f8f9fa; margin-bottom: 1rem;">
                            <h4 style="margin:0;">Resumen Equipo: {sel_team} ({team_audit['Categoría']})</h4>
                            <div style="display: flex; gap: 20px; margin-top: 10px;">
                                <span><b>Estado:</b> <span style="color: {'green' if audit_color=='success' else 'red'}">{team_audit['Estado General']}</span></span>
                                <span><b>Jugadores:</b> {team_audit['Total J.']} ({team_audit['Hombres']}M / {team_audit['Mujeres']}F)</span>
                                <span><b>Cedidos:</b> H: {team_audit['Cedidos H']} | M: {team_audit['Cedidos M']}</span>
                            </div>
                            <div style="margin-top: 5px; font-size: 0.9em; color: #666;">
                                <b>Detalles:</b> {team_audit['Detalles']}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

            # MÁSCARA DE FILTRADO
            mask = pd.Series([True] * len(df))
            if sel_team != "Todos":
                mask = mask & (df['Pruebas'] == sel_team)
            elif sel_cat != "Todas":
                mask = mask & (df['Pruebas'].isin(teams_in_cat))
                
            if sel_lic_status == "⛔ Con Incidencias":
                mask = mask & (df['Errores_Normativos'] != "")
            elif 'Validacion_FESBA' in df.columns and sel_lic_status != "Todos":
                if sel_lic_status == "✅ Licencia OK":
                    mask = mask & (df['Validacion_FESBA'].str.contains("✅", na=False))
                elif sel_lic_status == "❌ Licencia Incorrecta":
                    mask = mask & (df['Validacion_FESBA'].str.contains("❌", na=False))
                elif sel_lic_status == "Pendiente de Revisión":
                    mask = mask & (df['Validacion_FESBA'].isna())

            # Aplicar Filtro Cedidos
            if sel_cedido == "Sí":
                mask = mask & (df['Es_Cedido'] == True)
            elif sel_cedido == "No":
                mask = mask & (df['Es_Cedido'] == False)

            # Aplicar Filtro No Seleccionables
            if sel_no_sel == "Sí":
                mask = mask & (df['No_Seleccionable'] == True)
            elif sel_no_sel == "No":
                mask = mask & (df['No_Seleccionable'] == False)

            # Aplicar Filtro Excluidos
            if sel_excluido == "Ocultar Excluidos":
                mask = mask & (df['Es_Excluido'] == False)
            elif sel_excluido == "Solo Excluidos":
                mask = mask & (df['Es_Excluido'] == True)
            
            # Aplicar Buscador de Texto (General)
            if search_query:
                # Normalizar a string y buscar
                q = search_query.lower()
                text_mask = (
                    df['Jugador'].astype(str).str.lower().str.contains(q, na=False) |
                    df['Pruebas'].astype(str).str.lower().str.contains(q, na=False) |
                    df['Nº.ID'].astype(str).str.contains(q, na=False)
                )
                mask = mask & text_mask

            # DATA EDITOR
            # Create status indicator column for visual row highlighting
            # Logic: Show ⚠️ if there are Normative Errors OR FESBA Validation issues (Not Found/Error)
            mask_normative = df['Errores_Normativos'].notna() & (df['Errores_Normativos'].astype(str).str.strip() != '')
            mask_fesba = df['Validacion_FESBA'].astype(str).str.upper().str.contains('NO ENCONTRADO|❌', na=False)
            
            df['_Estado_Fila'] = '✅'
            df.loc[mask_normative | mask_fesba, '_Estado_Fila'] = '⚠️'
            
            # Selector de Columnas Visibles (REMOVED per user request)
            # Default columns (hardcoded)
            cols_to_show = ['_Estado_Fila', 'Nº.ID', 'Jugador', 'Género', 'País', 'Estado_Transferencia', 'Pruebas', 'Errores_Normativos', 'Validacion_FESBA', 'Es_Cedido', 'Es_Excluido', 'Declaración_Jurada', 'Documento_Cesión', 'Notas_Revision']
            
            for c in cols_to_show:
                if c not in df.columns: df[c] = None
            
        # --- LAYOUT PRINCIPAL (DIVISIÓN GLOBAL) ---
        # 77% Tabla (Izquierda) | 23% Acciones (Derecha)
        col_main_left, col_main_right = st.columns([0.77, 0.23], gap="medium")
        
        # --- COLUMNA IZQUIERDA: TABLA Y EDICIÓN ---
        with col_main_left:
            st.subheader(f"📋 Listado de Jugadores ({len(df[mask])})")
            
            # FORMULARIO DE EDICIÓN
            with st.form("editor_batch_form", border=False):
                # Convert ID to string for editing (supports alphanumeric IDs)
                display_df = df.loc[mask, cols_to_show].copy()
                display_df['Nº.ID'] = display_df['Nº.ID'].astype(str)
                
                edited_df = st.data_editor(
                    display_df,
                    column_config={
                        "_Estado_Fila": st.column_config.TextColumn("❗", disabled=True, width="small", help="⚠️ = Tiene incidencias | ✅ = OK"),
                        "Nº.ID": st.column_config.TextColumn("Nº Licencia", disabled=False, width="small"),
                        "Jugador": st.column_config.TextColumn("Jugador", disabled=True),
                        "Género": st.column_config.TextColumn("Género", disabled=False, width="small"),
                        "País": st.column_config.TextColumn("País", disabled=False, width="small"),
                        "Estado_Transferencia": st.column_config.TextColumn("🔄 Doble Club", disabled=True, width="small"),
                        "Pruebas": st.column_config.TextColumn("Equipo", disabled=False),
                        "Errores_Normativos": st.column_config.TextColumn(
                            "⚠️ Incidencias", 
                            disabled=True,
                            width="large",
                            help="Errores detectados automáticamente (Cedidos, Mínimos, etc.)"
                        ),
                        "Validacion_FESBA": st.column_config.TextColumn("Estado FESBA", disabled=True, width="medium"),
                        "Declaración_Jurada": st.column_config.CheckboxColumn("📄 Dec. Jurada", width="small"),
                        "Documento_Cesión": st.column_config.CheckboxColumn("🔄 Doc. Cesión", width="small"),
                        "Es_Cedido": st.column_config.CheckboxColumn("Cedido", disabled=True, width="small"),
                        "Es_Excluido": st.column_config.CheckboxColumn("Excluido", width="small", help="Marcar para ignorar en cálculos de equipo"),
                        "Notas_Revision": st.column_config.TextColumn("Notas Internas", width="large")
                    },
                    use_container_width=True,
                    hide_index=True,
                    height=850, # Altura aumentada
                    key="editor_revision"
                )
                
                # BARRA DE GUARDADO FLOATING ESTILO
                st.write("") # Spacer
                col_sub_1, col_sub_2 = st.columns([1, 2])
                with col_sub_1:
                    submitted = st.form_submit_button(
                        "💾 GUARDAR CAMBIOS", 
                        type="primary", 
                        use_container_width=True,
                        help="Confirma todos los cambios realizados en la tabla"
                    )
                with col_sub_2:
                    if submitted:
                        st.caption("✅ Procesando cambios...")
                    else:
                        st.caption("ℹ️ Edita libremente. Pulsa guardar al terminar.")

        # --- LÓGICA DE GUARDADO (POST-SUBMIT) ---
        if submitted:
            # 1. Update main DF with changes
            # CRITICAL FIX: st.data_editor returns a DF with reset indices (0, 1, 2...)
            # but df.update() needs the ORIGINAL indices to match rows correctly.
            editable_cols = ['Nº.ID', 'Declaración_Jurada', 'Documento_Cesión', 'Es_Excluido', 'Notas_Revision', 'Pruebas', 'Género', 'País']
            original_indices = df.loc[mask].index  # Preserve original indices
            original_slice = df.loc[mask, editable_cols].copy()
            
            # Restore original index to edited_df so df.update() works correctly
            edited_df_indexed = edited_df.copy()
            edited_df_indexed.index = original_indices
            edited_slice = edited_df_indexed[editable_cols].copy()
            
            df.update(edited_df_indexed)
            
            # 2. Trigger Full Recalculation
            current_eq = rules_manager.load_equivalences()
            fuzzy_th = settings_manager.get("fuzzy_threshold", 0.80)
            df = process_dataframe(df, equivalences=current_eq, fuzzy_threshold=fuzzy_th)

            # 3. Re-run Validation Checks
            rules_config = rules_manager.load_rules()
            team_categories = rules_manager.load_team_categories()
            calculate_team_compliance(df, rules_config, team_categories) 
            df = apply_comprehensive_check(df, rules_config, team_categories)
            
            # 4. Save to Session & DB
            st.session_state['data'] = df
            success, msg = save_current_session(current_name, df)
            
            if success:
                st.toast("✅ Guardado y Recalculado con Éxito", icon="⚡")
                
                # LOG CHANGES
                if 'change_log' not in st.session_state: st.session_state['change_log'] = []
                timestamp = datetime.now().strftime("%H:%M:%S")
                
                for idx in original_slice.index:
                    for col in editable_cols:
                        try:
                            val_old = original_slice.at[idx, col]
                            val_new = edited_slice.at[idx, col]
                            if str(val_old) != str(val_new):
                                if pd.isna(val_old) and pd.isna(val_new): continue
                                player_name = str(df.at[idx, 'Jugador'])[:25]
                                col_map = {'Nº.ID':'ID', 'Declaración_Jurada':'DJ', 'Documento_Cesión':'DocCes', 'Es_Excluido':'Excl', 'Notas_Revision':'Notas', 'Pruebas':'Equipo', 'Género':'Gén', 'País':'País'}
                                col_short = col_map.get(col, col)
                                val_old_fmt = '✓' if val_old is True else '✗' if val_old is False else str(val_old)[:15]
                                val_new_fmt = '✓' if val_new is True else '✗' if val_new is False else str(val_new)[:15]
                                log_entry = f"[{timestamp}] ✏️ {player_name} | {col_short}: {val_old_fmt} → {val_new_fmt}"
                                st.session_state['change_log'].insert(0, log_entry)
                        except: pass
                
                time.sleep(0.5)
                st.rerun()
            else:
                st.error(f"Error al guardar: {msg}")

        # --- COLUMNA DERECHA: ACCIONES ---
        with col_main_right:
            st.write("### ⚙️ Panel de Control")
            
            # 1. HISTORIAL
            with st.expander("📜 Historial", expanded=True):
                if st.button("🗑️", key="limpiar_hist", help="Limpiar Historial"):
                     st.session_state['change_log'] = []
                     st.rerun()
                
                if 'change_log' in st.session_state and st.session_state['change_log']:
                    # Scrollable container for logs
                    hist_container = st.container(height=200)
                    with hist_container:
                        for log in st.session_state['change_log'][:50]:
                            if "🗑️" in log: st.error(log, icon="🗑️")
                            elif "✏️" in log: st.info(log, icon="✏️")
                            elif "➕" in log: st.success(log, icon="➕")
                            else: st.text(log)
                else:
                    st.caption("Sin cambios recientes.")

            # 2. VALIDACIÓN FESBA
            with st.expander("🌐 FESBA", expanded=True):
                if 'license_validator' not in st.session_state:
                    st.session_state['license_validator'] = validator
                val_instance = st.session_state['license_validator']
                st.caption(f"Modo: {val_instance.get_storage_mode() if hasattr(val_instance, 'get_storage_mode') else 'Local'}")
                
                if st.button("🚀 Comprobar Licencias", use_container_width=True):
                    with st.status("Validando...", expanded=True):
                         # ... (Lógica FESBA Original simplificada para brevedad en replace, pero mantenemos la llamada)
                         # NOTA: Por limitación de replace, asumo que la lógica FESBA se mantiene similar o la reinserto 
                         pass # En realidad el replace debe contener todo. Voy a incluir la lógica completa abajo.

            # REINSERCIÓN LÓGICA FESBA COMPLETA (Para no romper el código)
            # (El usuario quiere acciones a la derecha. Aquí va el bloque FESBA completo) --
            # Como el bloque original era largo, lo reescribo comprimido pero funcional.
            
                # ... continuación botón FESBA ...
                    try:
                        success, msg = val_instance.load_full_db(force_refresh=True)
                        if success:
                            res = val_instance.validate_dataframe(df, search_mode=False)
                            df['Validacion_FESBA'] = res
                            df, updated_count = val_instance.update_player_data_from_db(df)
                            if updated_count > 0: st.write(f"🔄 {updated_count} actualizados")
                            st.session_state['data'] = df
                            success, msg = save_current_session(current_name, df)
                            if success:
                                st.success("Validado!")
                                st.rerun()
                            else:
                                st.error(f"Error al guardar validación: {msg}")
                        else: st.error(msg)
                    except Exception as e:
                        st.error(f"Error: {e}")
            
                st.caption("Utilidades FESBA")
                csv_file = st.file_uploader("Subir CSV", type=["csv"], key="csv_licenses_upload_right", label_visibility="collapsed")
                if csv_file is not None:
                    if st.button("Importar CSV", use_container_width=True):
                        with st.spinner("Importando licencias..."):
                            success, msg = val_instance.import_from_csv(csv_file)
                            if success:
                                st.success(msg)
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error(msg)
                
                if st.button("🔄 Forzar Recarga (Solo Local)", help="Requiere Chrome instalado", use_container_width=True):
                    with st.spinner("Actualizando desde web FESBA..."):
                        success, msg = val_instance.load_full_db(force_refresh=True)
                        if success:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.warning(msg)

            # 3. ELIMINAR JUGADORES
            with st.expander("🗑️ Eliminar Jugadores"):
                st.caption("Borrar jugadores por Nº ID")
                ids_input = st.text_area("IDs (uno por línea o separados por comas):", height=68, key="del_input_right")
                
                if st.button("Eliminar Seleccionados", type="primary", use_container_width=True, key="btn_del_right"):
                    if ids_input:
                        # Parse IDs
                        import re
                        raw_ids = re.split(r'[,\n\t\s]+', ids_input)
                        ids_to_remove = [x.strip() for x in raw_ids if x.strip()]
                        
                        if ids_to_remove:
                            initial_count = len(df)
                            # Convert IDs to string for comparison
                            df_ids = df['Nº.ID'].astype(str)
                            
                            # Filter
                            df = df[~df_ids.isin(ids_to_remove)]
                            final_count = len(df)
                            removed = initial_count - final_count
                            
                            if removed > 0:
                                # Save & Recalc
                                current_eq = rules_manager.load_equivalences()
                                fuzzy_th = settings_manager.get("fuzzy_threshold", 0.80)
                                df = process_dataframe(df, equivalences=current_eq, fuzzy_threshold=fuzzy_th)
                                
                                # Re-run Validation
                                rules_config = rules_manager.load_rules()
                                team_categories = rules_manager.load_team_categories()
                                calculate_team_compliance(df, rules_config, team_categories) 
                                df = apply_comprehensive_check(df, rules_config, team_categories)
                                
                                st.session_state['data'] = df
                                success, msg = save_current_session(current_name, df)
                                
                                if success:
                                    st.toast(f"🗑️ Eliminados {removed} jugadores", icon="✅")
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error(f"Error al guardar: {msg}")
                            else:
                                st.warning("No se encontraron coincidencias para eliminar.")

    # 2. CONFIGURACIÓN AVANZADA (NUEVO)
    with tab_config:
        st.header("⚙️ Panel de Control Total")
        
        c_conf1, c_conf2 = st.columns([1, 1])
        
        # A) ASIGNACIÓN DE CATEGORÍAS A EQUIPOS
        with c_conf1:
            st.subheader("1. Asignación de Equipos")
            st.info("Asocia cada equipo del Excel a una categoría de competición.")
            cat_df = pd.DataFrame(list(team_categories.items()), columns=['Equipo', 'Categoría'])
            edited_cat_df = st.data_editor(
                cat_df,
                column_config={
                    "Equipo": st.column_config.TextColumn("Equipo", disabled=True),
                    "Categoría": st.column_config.SelectboxColumn("Categoría", options=LIGA_CATEGORIES + ["Sin Asignar"], required=True)
                },
                use_container_width=True,
                height=300,
                key="team_cat_editor"
            )
            
            # --- NUEVO: IMPORTACIÓN MASIVA ---
            with st.expander("📋 Importación Masiva / Pegar desde Excel"):
                st.caption("⚡ **Truco Pro:** Copia dos columnas en tu Excel (**Equipo** y **Categoría**) y pégalas aquí para asignar 100+ equipos de golpe.")
                bulk_input = st.text_area("Pegar datos (Formato: Equipo [TAB] Categoría)", height=150, help="Excel usa TAB como separador por defecto al copiar.")
                
                if st.button("🚀 Procesar Lista Masiva"):
                    updates_count = 0
                    if bulk_input:
                        lines = bulk_input.strip().split('\n')
                        for line in lines:
                            # Detectar separador: Tab (Excel) o ; o ,
                            if '\t' in line:
                                parts = line.split('\t')
                            elif ';' in line:
                                parts = line.split(';')
                            elif ',' in line:
                                parts = line.split(',')
                            else:
                                continue
                                
                            if len(parts) >= 2:
                                team_name = parts[0].strip()
                                category = parts[1].strip()
                                
                                # Limpieza básica de comillas si viene de CSV
                                team_name = team_name.strip('"').strip("'")
                                category = category.strip('"').strip("'")
                                
                                # Verificar validez
                                if category in LIGA_CATEGORIES or category == "Sin Asignar":
                                    # Fuzzy Match simple o Exacto para el nombre del equipo
                                    # Intentamos match exacto primero
                                    if team_name in team_categories:
                                        team_categories[team_name] = category
                                        updates_count += 1
                                    else:
                                        # Intento de búsqueda flexible
                                        # (Opcional: implementar fuzzy matching aquí si es crítico)
                                        pass
                        
                        if updates_count > 0:
                            rules_manager.save_team_categories(team_categories)
                            st.success(f"✅ Actualizados {updates_count} equipos.")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.warning("No se encontraron coincidencias de equipos o categorías válidas.")

            if st.button("Guardar Asignaciones"):
                new_cats = dict(zip(edited_cat_df['Equipo'], edited_cat_df['Categoría']))
                rules_manager.save_team_categories(new_cats)
                
                # Recargar y recalcular todo automáticamente
                team_categories = rules_manager.load_team_categories()
                
                # Compliance check usa categorías, así que se actualiza solo con st.rerun()
                # Pero apply_comprehensive_check también se llama en main loop
                
                st.success("Asignaciones guardadas y aplicadas.")
                time.sleep(0.5)
                st.rerun()

        # B) GESTIÓN DE EQUIVALENCIAS (FILIALES)
        with c_conf2:
            st.subheader("2. Clubes Filiales (Equivalencias)")
            st.info("Define qué clubes son filiales para no contarlos como cedidos.")
            
            # Convertir dict a DF plano para editar: Club Madre | Filial
            eq_rows = []
            for madre, filiales in equivalences.items():
                for f in filiales:
                    eq_rows.append({"Club Principal": madre, "Club Filial": f})
            eq_df = pd.DataFrame(eq_rows)
            
            edited_eq_df = st.data_editor(
                eq_df,
                num_rows="dynamic",
                use_container_width=True,
                height=300,
                key="eq_editor"
            )
            
            if st.button("Guardar Equivalencias"):
                # Reconstruir diccionario
                new_eq_dict = {}
                for idx, row in edited_eq_df.iterrows():
                    madre = row['Club Principal']
                    filial = row['Club Filial']
                    if madre and filial:
                        if madre not in new_eq_dict: new_eq_dict[madre] = []
                        new_eq_dict[madre].append(filial)
                rules_manager.save_equivalences(new_eq_dict)
                
                # Recalcular Es_Cedido inmediatamente
                fuzzy_th = settings_manager.get("fuzzy_threshold", 0.80)
                df = process_dataframe(df, equivalences=new_eq_dict, fuzzy_threshold=fuzzy_th)
                
                st.success("Equivalencias guardadas.")
                time.sleep(0.5)
                st.rerun()

        st.divider()

        # C) CONFIGURACIÓN DE REGLAS POR CATEGORÍA (NUEVO)
        st.subheader("3. Configuración de Reglas por Categoría")
        st.info("Define los límites y permisos para cada categoría de competición.")
        
        # Preparar datos para editor
        # Convertir el dict de reglas a un DF plano
        rules_rows = []
        for cat, r in rules_config.items():
            row = r.copy()
            row['Categoría'] = cat
            # Aplanar ratio table? No, mejor dejarlo fuera o simplificar.
            # Por ahora solo editamos los campos escalares
            if 'ratio_table' in row: del row['ratio_table'] 
            rules_rows.append(row)
            
        rules_df = pd.DataFrame(rules_rows)
        
        # Reordenar columnas
        cols_order = ['Categoría', 'min_total', 'max_total', 'min_gender', 'allow_loaned_players', 'allow_non_selectable', 'non_selectable_minors_only', 'require_loan_doc', 'require_declaration']
        # Asegurar que existan todas
        for c in cols_order:
            if c not in rules_df.columns: rules_df[c] = None
            
        edited_rules = st.data_editor(
            rules_df[cols_order],
            column_config={
                "Categoría": st.column_config.TextColumn("Categoría", disabled=True),
                "min_total": st.column_config.NumberColumn("Min. Total", min_value=0, step=1),
                "max_total": st.column_config.NumberColumn("Max. Total", min_value=0, step=1),
                "min_gender": st.column_config.NumberColumn("Min. Género", min_value=0, step=1),
                "allow_loaned_players": st.column_config.CheckboxColumn("Permitir Cedidos"),
                "allow_non_selectable": st.column_config.CheckboxColumn("Permitir No Seleccionables"),
                "non_selectable_minors_only": st.column_config.CheckboxColumn("Solo Menores (No Sel.)", help="Si se permiten No Seleccionables, restringir solo a menores de edad"),
                "require_loan_doc": st.column_config.CheckboxColumn("Exigir Doc. Cesión"),
                "require_declaration": st.column_config.CheckboxColumn("Exigir Dec. Jurada")
            },
            use_container_width=True,
            key="rules_editor"
        )
        
        if st.button("Guardar Reglas de Competición"):
            # Reconstruir diccionario de configuración
            new_rules_config = rules_config.copy()
            
            for _, row in edited_rules.iterrows():
                cat = row['Categoría']
                if cat in new_rules_config:
                    # Actualizar campos escalares
                    new_rules_config[cat]['min_total'] = int(row['min_total'])
                    new_rules_config[cat]['max_total'] = int(row['max_total'])
                    new_rules_config[cat]['min_gender'] = int(row['min_gender'])
                    new_rules_config[cat]['allow_loaned_players'] = bool(row['allow_loaned_players'])
                    new_rules_config[cat]['allow_non_selectable'] = bool(row['allow_non_selectable'])
                    new_rules_config[cat]['non_selectable_minors_only'] = bool(row['non_selectable_minors_only'])
                    new_rules_config[cat]['require_loan_doc'] = bool(row['require_loan_doc'])
                    new_rules_config[cat]['require_declaration'] = bool(row['require_declaration'])
                    
            rules_manager.save_rules(new_rules_config)
            st.success("Reglas actualizadas correctamente.")
            time.sleep(0.5)
            st.rerun()


        st.divider()

        # C) CONFIGURACIÓN FUZZY MATCHING (NUEVO)
        st.subheader("3. Detección Inteligente de Cedidos (Fuzzy Match)")
        st.info("Ajusta la sensibilidad para detectar si el Club y el Equipo son el mismo, aunque el nombre varíe ligeramente.")
        
        # Cargar de settings o session state
        saved_fuzzy = settings_manager.get("fuzzy_threshold", 0.80)
        current_fuzzy = st.session_state.get('fuzzy_threshold', saved_fuzzy)
        
        new_fuzzy = st.slider("Umbral de Similitud (0.0 = Todo es igual, 1.0 = Exacto)", 0.0, 1.0, current_fuzzy, 0.05)
        
        if new_fuzzy != current_fuzzy:
            st.session_state['fuzzy_threshold'] = new_fuzzy
            settings_manager.set("fuzzy_threshold", new_fuzzy)
            # Recalcular
            if 'data' in st.session_state and st.session_state['data'] is not None:
                df = st.session_state['data']
                current_eq = rules_manager.load_equivalences()
                # Re-procesar con nuevo umbral
                df = process_dataframe(df, equivalences=current_eq, fuzzy_threshold=new_fuzzy)
                
                # Recalcular Auditoría
                compliance_df = calculate_team_compliance(df, rules_config, team_categories)
                df = apply_comprehensive_check(df, rules_config, team_categories)
                
                st.session_state['data'] = df
                save_current_session(current_name, df)
                st.rerun()

        st.divider()

        # C) EDITOR DE REGLAS DE COMPETICIÓN
        st.subheader("3. Reglas de Competición")
        
        col_rules_sel, col_rules_edit = st.columns([1, 2])
        
        with col_rules_sel:
            sel_rule_cat = st.selectbox("Editar Reglas de:", LIGA_CATEGORIES)
            
            # Botón para añadir nueva categoría
            new_cat_name = st.text_input("Nueva Categoría:")
            if st.button("➕ Crear Categoría"):
                if new_cat_name and new_cat_name not in rules_config:
                    # Clonar default
                    rules_config[new_cat_name] = rules_config["División de Honor"].copy()
                    rules_manager.save_rules(rules_config)
                    st.success(f"Creada {new_cat_name}")
                    st.rerun()

        with col_rules_edit:
            if sel_rule_cat:
                rule_data = rules_config[sel_rule_cat]
                
                with st.form(f"form_rules_{sel_rule_cat}"):
                    c_r1, c_r2, c_r3 = st.columns(3)
                    new_min_total = c_r1.number_input("Mínimo Jugadores", value=rule_data.get('min_total', 10))
                    new_max_total = c_r2.number_input("Máximo Jugadores", value=rule_data.get('max_total', 20))
                    new_min_gender = c_r3.number_input("Mínimo por Género", value=rule_data.get('min_gender', 5))
                    
                    c_r4, c_r5 = st.columns(2)
                    req_loan = c_r4.checkbox("Exigir Doc. Cesión", value=rule_data.get('require_loan_doc', True))
                    req_decl = c_r5.checkbox("Exigir Dec. Jurada", value=rule_data.get('require_declaration', True))
                    
                    st.write("**Tabla de Ratios (Total vs Máx Cedidos)**")
                    # Tabla editable de ratios
                    ratio_df = pd.DataFrame(rule_data.get('ratio_table', []))
                    edited_ratio_df = st.data_editor(ratio_df, num_rows="dynamic", use_container_width=True)
                    
                    if st.form_submit_button("💾 Guardar Reglas"):
                        # Actualizar objeto
                        rules_config[sel_rule_cat]['min_total'] = new_min_total
                        rules_config[sel_rule_cat]['max_total'] = new_max_total
                        rules_config[sel_rule_cat]['min_gender'] = new_min_gender
                        rules_config[sel_rule_cat]['require_loan_doc'] = req_loan
                        rules_config[sel_rule_cat]['require_declaration'] = req_decl
                        # Guardar tabla de ratios (convertir a lista de dicts)
                        rules_config[sel_rule_cat]['ratio_table'] = edited_ratio_df.to_dict(orient='records')
                        
                        rules_manager.save_rules(rules_config)
                        st.success(f"Reglas actualizadas para {sel_rule_cat}")
                        time.sleep(1)
                        st.rerun()

                        rules_manager.save_rules(rules_config)
                        st.success(f"Reglas actualizadas para {sel_rule_cat}")
                        time.sleep(1)
                        st.rerun()

        st.divider()

        # D) GESTIÓN DE CONTACTOS (NUEVO)
        st.subheader("4. Gestión de Contactos")
        st.info("Edita los correos electrónicos de los equipos para el envío automático.")
        
        try:
            from email_generator import load_contacts_from_csv, save_contacts_to_csv
            contacts_path = os.path.join(BASE_DIR, "Correos", "Contactos.csv")
            
            # Cargar
            current_contacts = load_contacts_from_csv(contacts_path)
            
            # Convertir a DF para editor
            contacts_data = [{"Equipo": k, "Emails": v} for k, v in current_contacts.items()]
            # Asegurar que todos los equipos de la base actual estén presentes
            all_teams = list(team_categories.keys())
            existing_teams_in_contacts = set(current_contacts.keys())
            
            for t in all_teams:
                if t not in existing_teams_in_contacts and t != "Sin Asignar":
                     contacts_data.append({"Equipo": t, "Emails": ""})
            
            contacts_df = pd.DataFrame(contacts_data)
            
            edited_contacts_df = st.data_editor(
                contacts_df,
                use_container_width=True,
                num_rows="dynamic",
                key="contacts_editor",
                column_config={
                    "Equipo": st.column_config.TextColumn("Equipo", disabled=False),
                    "Emails": st.column_config.TextColumn("Emails (separados por ;)", width="large")
                }
            )
            
            if st.button("💾 Guardar Contactos"):
                # Reconstruir dict
                new_contacts_map = {}
                for _, row in edited_contacts_df.iterrows():
                    t = str(row['Equipo']).strip()
                    e = str(row['Emails']).strip()
                    if t:
                        new_contacts_map[t] = e
                
                if save_contacts_to_csv(new_contacts_map, contacts_path):
                    st.success("Contactos guardados exitosamente.")
                else:
                    st.error("Error guardando contactos.")
                    
        except Exception as e:
            st.error(f"Error en gestor de contactos: {e}")

        st.divider()

        # E) TÉCNICOS Y DELEGADOS (NUEVO)
        st.subheader("5. Control de Técnicos y Delegados")
        st.info("Marca qué equipos han entregado correctamente el 'Impreso de Técnicos y Delegados'.")
        
        tech_status_path = os.path.join(BASE_DIR, "data", "technicians_status.json")
        os.makedirs(os.path.dirname(tech_status_path), exist_ok=True)
        
        # Cargar estado actual
        tech_status = {}
        if os.path.exists(tech_status_path):
            with open(tech_status_path, 'r', encoding='utf-8') as f:
                try: tab_status = json.load(f)
                except: tab_status = {}
        else:
            tab_status = {}

        # Preparar datos para tabla
        tech_rows = []
        # Usar team_categories como fuente de verdad de equipos
        for team, cat in team_categories.items():
            if team == "Sin Asignar": continue
            is_delivered = tab_status.get(team, False)
            tech_rows.append({
                "Equipo": team,
                "Categoría": cat,
                "Entregado": is_delivered
            })
            
        tech_df = pd.DataFrame(tech_rows)
        
        # Filtros
        col_tf1, col_tf2 = st.columns([1, 2])
        filter_cat_tech = col_tf1.selectbox("Filtrar Categoría:", ["Todas"] + LIGA_CATEGORIES, key="tech_cat_filter")
        search_tech = col_tf2.text_input("Buscar Equipo:", key="tech_search")
        
        # Aplicar filtros
        filtered_tech_df = tech_df.copy()
        if filter_cat_tech != "Todas":
            filtered_tech_df = filtered_tech_df[filtered_tech_df['Categoría'] == filter_cat_tech]
        if search_tech:
            filtered_tech_df = filtered_tech_df[filtered_tech_df['Equipo'].str.contains(search_tech, case=False, na=False)]
            
        # Editor
        edited_tech_df = st.data_editor(
            filtered_tech_df,
            column_config={
                "Equipo": st.column_config.TextColumn("Equipo", disabled=True),
                "Categoría": st.column_config.TextColumn("Categoría", disabled=True),
                "Entregado": st.column_config.CheckboxColumn("Impreso Entregado", help="Marcar si han entregado el documento oficial")
            },
            use_container_width=True,
            hide_index=True,
            key="tech_editor"
        )
        
        if st.button("💾 Guardar Estado Técnicos"):
            # Actualizar dict principal con los cambios filtrados
            # OJO: data_editor solo devuelve lo que se ve si se filtra? NO, devuelve el DF editado pero si filtramos antes?
            # Si filtramos, edited_tech_df solo tiene los filtrados.
            # Necesitamos mergear con el estado global.
            
            updates = 0
            for _, row in edited_tech_df.iterrows():
                team_name = row['Equipo']
                new_status = row['Entregado']
                
                # Check if changed
                if tab_status.get(team_name) != new_status:
                    tab_status[team_name] = new_status
                    updates += 1
            
            # Guardar
            with open(tech_status_path, 'w', encoding='utf-8') as f:
                json.dump(tab_status, f, indent=4)
                
            st.success(f"Estado actualizado ({updates} cambios).")
            time.sleep(1)
            st.rerun()

    # 3. INCIDENCIAS (Cambio de Nombre)
    with tab_incidencias:
        st.subheader("⚠️ Listado de Incidencias Normativas")
        
        incidencias_df = df[df['Errores_Normativos'] != ""]
        
        if incidencias_df.empty:
             st.success("✅ **¡Felicidades! No se detectan infracciones normativas.**")
        else:
             st.error(f"❌ **Se han detectado {len(incidencias_df)} irregularidades.**")
             st.dataframe(
                 incidencias_df[['Pruebas', 'Jugador', 'Errores_Normativos']], 
                 use_container_width=True,
                 hide_index=True
             )

    # 4. EXPORTAR
    with tab_export:
        st.subheader("Generación de Ficheros Oficiales")
        c_dl1, c_dl2, c_dl3 = st.columns(3)
        with c_dl1:
            st.download_button("Descargar Informe Excel", data=to_excel(df), file_name=f"Informe_{current_name}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        with c_dl2:
            st.download_button("CSV Jugadores", data=generate_players_csv(df), file_name="import_players.csv", mime="text/csv", use_container_width=True, disabled=bool(data_errors > 0))
        with c_dl3:
            st.download_button("CSV Alineaciones", data=generate_team_players_csv(df), file_name="import_team_players.csv", mime="text/csv", use_container_width=True, disabled=bool(data_errors > 0))

        st.divider()
        st.subheader("📧 Generación de Correos (v2.0)")
        
        col_email_1, col_email_2 = st.columns([1, 2])
        with col_email_1:
            st.info("Genera borradores de correo (.eml) para enviar a los clubes con el estado de su inscripción.")
        
        with col_email_2:
            # Mode Selector
            gen_mode = st.radio("Modo de Generación:", ["Por Categoría (Masivo)", "Por Club (Individual)"], horizontal=True, key="gen_mode_selector_v2")
            
            if gen_mode == "Por Categoría (Masivo)":
                # Selector de Categoría
                cat_options = ["Todas"] + LIGA_CATEGORIES
                sel_email_cat = st.selectbox("Filtrar por Categoría:", cat_options, key="email_cat_filter")
                
                if st.button("📧 Generar Correos (Masivo)", use_container_width=True, type="primary"):
                    with st.spinner(f"Generando correos para: {sel_email_cat}..."):
                        try:
                            # 1. Preparar directorio temporal
                            import tempfile
                            import shutil
                            import importlib
                            import email_generator
                            importlib.reload(email_generator)
                            from email_generator import generate_all_emails, load_contacts_from_csv
                            
                            tmp_dir = tempfile.mkdtemp()
                            output_dir = os.path.join(tmp_dir, "correos_generados")
                            os.makedirs(output_dir, exist_ok=True)
                            
                            # 2. Cargar contactos
                            contacts_path = os.path.join(BASE_DIR, "Correos", "Contactos.csv")
                            contacts_map = load_contacts_from_csv(contacts_path)
                            
                            # 3. Cargar estado técnicos
                            tech_status_path = os.path.join(BASE_DIR, "data", "technicians_status.json")
                            tech_status_map = {}
                            if os.path.exists(tech_status_path):
                                with open(tech_status_path, 'r', encoding='utf-8') as f:
                                    tech_status_map = json.load(f)

                            # 4. Generar EMLs
                            generated_files = generate_all_emails(
                                df, 
                                rules_config, 
                                team_categories, 
                                output_dir, 
                                category_filter=sel_email_cat,
                                contacts_map=contacts_map,
                                tech_status_map=tech_status_map
                            )
                            
                            if generated_files:
                                # 3. ZIP folder
                                zip_path = os.path.join(tmp_dir, "correos_lnc")
                                shutil.make_archive(zip_path, 'zip', output_dir)
                                
                                # 4. Read ZIP for download
                                with open(f"{zip_path}.zip", "rb") as f:
                                    zip_data = f.read()
                                    
                                st.success(f"✅ Se han generado {len(generated_files)} correos.")
                                st.download_button(
                                    label="📥 Descargar Correos (.zip)",
                                    data=zip_data,
                                    file_name=f"correos_lnc_{sel_email_cat.replace(' ', '_')}.zip",
                                    mime="application/zip",
                                    use_container_width=True
                                )
                            else:
                                st.warning("⚠️ No se generaron correos (verifica asignación de equipos/categorías).")
                                
                        except Exception as e:
                            st.error(f"Error generando correos: {e}")
                            logger.error(f"Email gen error: {e}")
            
            else: # INDIVIDUAL MODE
                teams = df['Pruebas'].dropna().unique().tolist()
                teams = sorted([t for t in teams if t and t != 'Sin Asignar'])
                
                sel_team = st.selectbox("Seleccionar Equipo:", teams, key="single_email_team_sel")
                
                if st.button("📤 Generar Correo Individual", use_container_width=True):
                    if sel_team:
                        import tempfile
                        import importlib
                        import email_generator
                        importlib.reload(email_generator)
                        from email_generator import generate_team_email, generate_eml_file, load_contacts_from_csv
                        
                        try:
                            # Load needed data
                            team_df = df[df['Pruebas'] == sel_team]
                            category = team_categories.get(sel_team, "Sin Asignar")
                            
                            contacts_path = os.path.join(BASE_DIR, "Correos", "Contactos.csv")
                            contacts_map = load_contacts_from_csv(contacts_path)
                            email_addr = contacts_map.get(sel_team, "")
                            
                            # Load Tech Status
                            tech_status_path = os.path.join(BASE_DIR, "data", "technicians_status.json")
                            tech_status_map = {}
                            if os.path.exists(tech_status_path):
                                with open(tech_status_path, 'r', encoding='utf-8') as f:
                                    tech_status_map = json.load(f)

                            # Generate
                            html = generate_team_email(sel_team, team_df, category, rules_config, tech_status_map=tech_status_map)
                            
                            # Save to temp
                            tmp_dir = tempfile.mkdtemp()
                            output_dir = os.path.join(tmp_dir, "correos_individual")
                            os.makedirs(output_dir, exist_ok=True)
                            
                            filepath = generate_eml_file(sel_team, html, output_dir, team_email=email_addr)
                            
                            with open(filepath, "rb") as f:
                                file_data = f.read()
                                
                            st.success(f"✅ Correo generado para **{sel_team}**")
                            st.download_button(
                                label=f"📥 Descargar {os.path.basename(filepath)}",
                                data=file_data,
                                file_name=os.path.basename(filepath),
                                mime="message/rfc822",
                                use_container_width=True
                            )
                            
                        except Exception as e:
                            st.error(f"Error: {e}")

else:
    st.markdown("""
    <div style="text-align: center; padding: 50px; color: #666;">
        <h2>👋 Gestor de Expedientes LNC</h2>
        <p>Sube un nuevo archivo Excel o carga uno existente desde el menú lateral.</p>
    </div>
    """, unsafe_allow_html=True)
