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

# Archivo de persistencia local (Ruta Absoluta)
PERSISTENCE_FILE = os.path.join(BASE_DIR, "historial_inscripciones.json")

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
def load_history():
    if os.path.exists(PERSISTENCE_FILE):
        try:
            with open(PERSISTENCE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

# Custom JSON Encoder for DateTime
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (pd.Timestamp, datetime, pd.Period)):
            return obj.strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(obj, pd.NA):
            return None
        return super().default(obj)

def save_history(history_dict):
    try:
        with open(PERSISTENCE_FILE, 'w', encoding='utf-8') as f:
            json.dump(history_dict, f, indent=4, ensure_ascii=False, cls=DateTimeEncoder)
        return True
    except Exception as e:
        st.error(f"Error guardando historial: {e}")
        return False

def save_current_session(file_name, df):
    history = load_history()
    df_save = df.copy()
    for col in df_save.select_dtypes(include=['datetime64[ns]']).columns:
        df_save[col] = df_save[col].dt.strftime('%Y-%m-%d')
    data_records = df_save.to_dict(orient='records')
    history[file_name] = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data": data_records
    }
    save_history(history)

def delete_session(file_name):
    history = load_history()
    if file_name in history:
        del history[file_name]
        save_history(history)
        return True
    return False

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
                        history[new_name] = history.pop(selected_file)
                        if save_history(history):
                            st.session_state['current_file_key'] = new_name
                            st.success("Renombrado correctamente.")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error("Error al guardar cambios.")

        if col_s1.button("Cargar"):
            st.session_state['current_file_key'] = selected_file
            raw_data = history[selected_file]['data']
            st.session_state['data'] = pd.DataFrame(raw_data)
            st.rerun()
        if col_s2.button("🗑️"):
            delete_session(selected_file)
            st.rerun()

    st.divider()
    st.info("Versión Configurable v2.2")

    # --- ESTADO DEL SISTEMA ---
    with st.sidebar.expander("🖥️ Estado del Sistema", expanded=True):
        # Estado DB Licencias
        if 'license_validator' in st.session_state and st.session_state['license_validator'].licenses_db:
            db_count = len(st.session_state['license_validator'].licenses_db)
            last_upd = st.session_state['license_validator'].last_update_timestamp
            last_upd_str = last_upd.strftime("%d/%m %H:%M") if last_upd else "?"
            st.markdown(f"🟢 **DB Licencias:** Activa ({db_count})")
            st.caption(f"Última act.: {last_upd_str}")
        else:
            st.markdown("🔴 **DB Licencias:** No cargada")
            
        # Estado Reglas
        st.markdown("🟢 **Reglas:** Cargadas")
        
        # Versión
        st.caption("v1.2.0 (Stable)")

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
                    
                    # Verificar si ya existe
                    if not current_df[current_df['Nº.ID'].astype(str) == raw_id].empty:
                        st.warning(f"El jugador con ID {raw_id} ya existe en la lista. Saltando.")
                        continue
                        
                    # Buscar en DB Local
                    try:
                        pid = int(raw_id)
                        info = val_instance.licenses_db.get(pid)
                    except:
                        info = None
                        
                    if info:
                        # Extraer datos
                        nombre_completo = info.get('name', 'Desconocido')
                        # Intentar separar nombre/apellidos (aproximado)
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
                            apellido1 = ""
                            apellido2 = ""
                            
                        # Género y Fecha
                        sexo = info.get('gender', '')
                        dob = info.get('dob', '')
                        club_origen = info.get('club', '')
                        pais = "SPAIN" # Asumir Spain si está en DB nacional
                    else:
                        # No encontrado
                        nombre = f"Manual-{raw_id}"
                        apellido1 = "?"
                        apellido2 = "?"
                        sexo = "?" # Requerirá edición manual
                        dob = "?"
                        club_origen = "?"
                        pais = "?"
                        st.warning(f"ID {raw_id} no encontrado en BBDD. Se añade con datos vacíos para revisión.")

                    # Crear fila
                    new_row = {
                        "Nº.ID": raw_id,
                        "Club": club_origen,
                        "Nombre": apellido1, # Excel suele poner apellido en 'Nombre' y nombre en 'Nombre.1'
                        "2ºNombre": apellido2,
                        "Nombre.1": nombre,
                        "F.Nac": dob,
                        "Género": sexo,
                        "País": pais,
                        "Pruebas": team,
                        "Es_Cedido": False, # Recalculará process_dataframe
                        "No_Seleccionable": False,
                        "Datos_Validos": True,
                        "Errores_Datos": [],
                        "Estado": "Nuevo Manual",
                        "Documentacion_OK": False,
                        "Declaración_Jurada": False,
                        "Documento_Cesión": False,
                        "Notas_Revision": "Añadido Manualmente",
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
                    # Re-procesar para calcular campos calculados (Es_Cedido, etc)
                    current_eq = rules_manager.load_equivalences()
                    # IMPORTANTE: process_dataframe espera columnas específicas, 
                    # pero ya las hemos mapeado manualmente. Solo necesitamos recalcular logica.
                    # Mejor opción: Recalcular lógica sobre todo el DF
                    fuzzy_th = st.session_state.get('fuzzy_threshold', 0.80)
                    current_df = process_dataframe(current_df, equivalences=current_eq, fuzzy_threshold=fuzzy_th)
                if count_added > 0:
                    st.success(f"Añadidos {count_added} jugadores.")
                    # Guardar
                    current_key = st.session_state.get('current_file_key', 'manual')
                    save_current_session(current_key, current_df)
                    st.session_state['manual_add_data'] = pd.DataFrame([{"Nº.ID": "", "Equipo": ""}])
                    time.sleep(1)
                    st.rerun()
                else:
                    st.warning("No se añadieron jugadores (quizás ya existían o no se encontraron en DB).")

    # --- SECCIÓN: IMPORTAR / ACTUALIZAR DESDE EXCEL ---
    with st.expander("📥 Importar / Actualizar desde Excel"):
        st.write("Sube un Excel con nuevos jugadores o cambios de equipo. El sistema fusionará los datos.")
        
        import_file = st.file_uploader("Subir Excel de Actualización", type=["xlsx"], key="import_uploader")
        
        if import_file is not None:
            if st.button("🔄 Procesar Importación"):
                if 'data' not in st.session_state or st.session_state['data'] is None:
                    st.error("Primero carga un archivo base.")
                else:
                    logger.info(f"Importando archivo: {import_file.name}")
                    df_new = load_data(import_file)
                    
                    if df_new is not None:
                        current_df = st.session_state['data']
                        current_eq = rules_manager.load_equivalences()
                        fuzzy_th = st.session_state.get('fuzzy_threshold', 0.80)
                        
                        # Procesar el nuevo DF
                        df_new_processed = process_dataframe(df_new, equivalences=current_eq, fuzzy_threshold=fuzzy_th)
                        
                        # Fusión
                        current_df, merge_logs = merge_dataframes_with_log(current_df, df_new_processed)
                        
                        # Actualizar Estado
                        st.session_state['data'] = current_df
                        current_key = st.session_state.get('current_file_key', 'fusionado')
                        save_current_session(current_key, current_df)
                        
                        # Guardar logs
                        st.session_state['merge_logs'] = merge_logs
                        st.success("Importación completada.")
                        time.sleep(0.5)
                        st.rerun()

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
            logger.info(f"Cargando nuevo archivo: {uploaded_file.name}")
            df_fresh = load_data(uploaded_file)
            
            # VALIDACIÓN DE COLUMNAS CRÍTICAS
            required_cols = ['Nº.ID', 'Nombre', 'Club', 'Pruebas']
            missing = [c for c in required_cols if c not in df_fresh.columns]
            
            if missing:
                st.error(f"❌ El archivo no tiene el formato correcto. Faltan las columnas: {', '.join(missing)}")
                st.stop()
                
            if df_fresh is not None:
                current_eq = rules_manager.load_equivalences()
                fuzzy_th = st.session_state.get('fuzzy_threshold', 0.80)
                df_processed = process_dataframe(df_fresh, equivalences=current_eq, fuzzy_threshold=fuzzy_th)
                if 'Notas_Revision' not in df_processed.columns: df_processed['Notas_Revision'] = ""
                
                save_current_session(uploaded_file.name, df_processed)
                st.session_state['data'] = df_processed
                st.session_state['current_file_key'] = uploaded_file.name
                st.session_state['last_uploaded'] = uploaded_file.name
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
            
            save_current_session(uploaded_file.name, df_processed)
            st.session_state['data'] = df_processed
            st.session_state['current_file_key'] = uploaded_file.name
            st.session_state['last_uploaded'] = uploaded_file.name
            st.rerun()


# Caso B: Trabajo con archivo activo
if 'data' in st.session_state and st.session_state['data'] is not None:
    df = st.session_state['data']
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
            c_f4, c_f5 = st.columns(2)
            sel_cedido = c_f4.selectbox("Filtro Cedidos:", ["Todos", "Sí", "No"])
            sel_no_sel = c_f5.selectbox("Filtro No Seleccionables:", ["Todos", "Sí", "No"])

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

            # DATA EDITOR
            cols_to_show = ['Jugador', 'Pruebas', 'Errores_Normativos', 'Validacion_FESBA', 'Es_Cedido', 'Declaración_Jurada', 'Documento_Cesión', 'Notas_Revision']
            for c in cols_to_show:
                if c not in df.columns: df[c] = None
            
            # Mover Errores_Normativos al principio para visibilidad
            
            edited_df = st.data_editor(
                df.loc[mask, cols_to_show],
                column_config={
                    "Jugador": st.column_config.TextColumn("Jugador", disabled=True),
                    "Pruebas": st.column_config.TextColumn("Equipo", disabled=True),
                    "Errores_Normativos": st.column_config.TextColumn(
                        "⚠️ Incidencias", 
                        disabled=True,
                        width="large",
                        help="Errores detectados automáticamente (Cedidos, Mínimos, etc.)"
                    ),
                    "Validacion_FESBA": st.column_config.TextColumn("Licencia Nacional", disabled=True, width="medium"),
                    "Declaración_Jurada": st.column_config.CheckboxColumn("📄 Dec. Jurada", width="small"),
                    "Documento_Cesión": st.column_config.CheckboxColumn("🔄 Doc. Cesión", width="small"),
                    "Es_Cedido": st.column_config.CheckboxColumn("Cedido", disabled=True, width="small"),
                    "Notas_Revision": st.column_config.TextColumn("Notas Internas", width="large")
                },
                use_container_width=True,
                hide_index=True,
                height=600,
                key="editor_revision"
            )

        with col_rev_right:
            st.write("### Acciones")
            
            # Botón Re-Validación Completa
            if st.button("🔄 Actualizar Estado", help="Recalcula errores si has cambiado documentación"):
                # 1. Actualizar DF con los cambios del editor (checkboxes, notas, etc.)
                df.update(edited_df)
                
                # 2. Volver a procesar (recalcula Es_Cedido, etc. si fuera necesario, y sobre todo lógica interna)
                current_eq = rules_manager.load_equivalences()
                fuzzy_th = st.session_state.get('fuzzy_threshold', 0.80)
                df = process_dataframe(df, equivalences=current_eq, fuzzy_threshold=fuzzy_th)

                # 3. Recalcular Cumplimiento Normativo (Auditoría Dinámica) para limpiar Errores_Normativos
                # Esto es CLAVE: process_dataframe inicializa Errores_Normativos, y apply_comprehensive_check la rellena de nuevo
                # basada en el estado ACTUAL de los checkboxes.
                rules_config = rules_manager.load_rules()
                team_categories = rules_manager.load_team_categories()
                
                # Primero calculamos cumplimiento por equipo (para métricas)
                calculate_team_compliance(df, rules_config, team_categories) 
                
                # Luego aplicamos el chequeo detallado que actualiza la columna 'Errores_Normativos' del DF
                df = apply_comprehensive_check(df, rules_config, team_categories)
                
                # 4. Guardar estado
                st.session_state['data'] = df
                save_current_session(current_name, df)
                
                st.success("Estado actualizado correctamente.")
                time.sleep(0.5)
                st.rerun()

            if st.button("💾 Guardar Notas", type="primary", use_container_width=True):
                df.update(edited_df)
                st.session_state['data'] = df
                save_current_session(current_name, df)
                st.success("Guardado.")

            st.divider()
            
            # --- INTEGRACIÓN DE VALIDACIÓN FESBA ---
            with st.expander("🌐 Validación FESBA", expanded=True):
                if 'license_validator' not in st.session_state:
                    st.session_state['license_validator'] = validator
                val_instance = st.session_state['license_validator']
                
                if st.button("🚀 Comprobar Licencias"):
                    with st.status("Validando con FESBA...", expanded=True):
                        success, msg = val_instance.load_full_db(force_refresh=False)
                        if success:
                            st.write("✅ DB Conectada.")
                            res = val_instance.validate_dataframe(df, search_mode=False)
                            df['Validacion_FESBA'] = res
                            st.session_state['data'] = df
                            save_current_session(current_name, df)
                            st.success("Validación finalizada.")
                            st.rerun()
                        else:
                            st.error(msg)
                
                if st.button("🔄 Forzar Recarga Web"):
                    val_instance.load_full_db(force_refresh=True)
                    st.success("Caché actualizado.")

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
                fuzzy_th = st.session_state.get('fuzzy_threshold', 0.80)
                df = process_dataframe(df, equivalences=new_eq_dict, fuzzy_threshold=fuzzy_th)
                
                # Recalcular Auditoría para reflejar cambios en conteo de cedidos
                compliance_df = calculate_team_compliance(df, rules_config, team_categories)
                df = apply_comprehensive_check(df, rules_config, team_categories)
                
                # Guardar
                st.session_state['data'] = df
                save_current_session(current_name, df)
                
                st.success("Equivalencias actualizadas y aplicadas.")
                time.sleep(0.5)
                st.rerun()

                st.success("Equivalencias actualizadas y aplicadas.")
                time.sleep(0.5)
                st.rerun()

        st.divider()

        # C) CONFIGURACIÓN FUZZY MATCHING (NUEVO)
        st.subheader("3. Detección Inteligente de Cedidos (Fuzzy Match)")
        st.info("Ajusta la sensibilidad para detectar si el Club y el Equipo son el mismo, aunque el nombre varíe ligeramente.")
        
        current_fuzzy = st.session_state.get('fuzzy_threshold', 0.80)
        new_fuzzy = st.slider("Umbral de Similitud (0.0 = Todo es igual, 1.0 = Exacto)", 0.0, 1.0, current_fuzzy, 0.05)
        
        if new_fuzzy != current_fuzzy:
            st.session_state['fuzzy_threshold'] = new_fuzzy
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

else:
    st.markdown("""
    <div style="text-align: center; padding: 50px; color: #666;">
        <h2>👋 Gestor de Expedientes LNC</h2>
        <p>Sube un nuevo archivo Excel o carga uno existente desde el menú lateral.</p>
    </div>
    """, unsafe_allow_html=True)
