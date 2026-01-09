import pandas as pd
import io
import re
import json
import os
import streamlit as st
from datetime import datetime

# NOTA: Las equivalencias ahora se pasan dinámicamente, no se cargan aquí globalmente.

@st.cache_data(ttl=3600, show_spinner=False)
def load_data(file):
    try:
        # Si es un objeto UploadedFile de Streamlit, leer bytes
        if hasattr(file, 'getvalue'):
            file.seek(0)
            df = pd.read_excel(file, header=3)
        else:
            df = pd.read_excel(file, header=3)
        return df
    except Exception as e:
        return None

def clean_string(s):
    if pd.isna(s):
        return ""
    return str(s).strip()

import difflib
import unicodedata

def remove_accents(input_str):
    if not isinstance(input_str, str): return str(input_str)
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

def normalize_name(s):
    if pd.isna(s): return ""
    s = remove_accents(str(s).lower())
    # Remove common prefixes/words
    replacements = [
        "club", "badminton", "deportivo", 
        "c.b.", "c.d.", "c.d.b.", "cdb", "cb", "cd",
        "mercapinturas", "recreativo", "ies",
        "asociacion", "agrupacion"
    ]
    for r in replacements:
        s = s.replace(r, "")
    # Remove punctuation and extra spaces
    s = re.sub(r'[^\w\s]', ' ', s) 
    return " ".join(s.split())

def calculate_similarity(a, b):
    norm_a = normalize_name(a)
    norm_b = normalize_name(b)
    
    if not norm_a or not norm_b:
        return 0.0
        
    # Substring check (High confidence)
    if norm_a in norm_b or norm_b in norm_a:
        return 1.0
        
    return difflib.SequenceMatcher(None, norm_a, norm_b).ratio()

def is_cedido(row, equivalences, fuzzy_threshold=0.80):
    club = clean_string(row.get('Club'))
    equipo = clean_string(row.get('Pruebas'))

    if not club or not equipo:
        return False 

    # 1. Exact Match (Fast)
    if club.upper() == equipo.upper():
        return False

    # 2. Fuzzy Match
    similarity = calculate_similarity(club, equipo)
    if similarity >= fuzzy_threshold:
        return False

    found_equivalence = False
    club_upper = club.upper()
    
    # Usar el diccionario de equivalencias inyectado
    if equivalences:
        for key_club, valid_teams in equivalences.items():
            if key_club.upper() == club_upper:
                valid_teams_upper = [t.upper() for t in valid_teams]
                if equipo.upper() in valid_teams_upper:
                    found_equivalence = True
                break
            
    if found_equivalence:
        return False
        
    return True

def is_no_seleccionable(row):
    pais = clean_string(row.get('País'))
    if pais.upper() != 'SPAIN':
        return True
    return False

def check_data_health(row):
    errors = []
    member_id = row.get('Nº.ID')
    if pd.isna(member_id) or str(member_id).strip() == "":
        errors.append("Falta ID")
    
    nombre = row.get('Nombre')
    if pd.isna(nombre) or str(nombre).strip() == "":
        errors.append("Falta Nombre")
        
    return errors

def format_date_for_export(date_val):
    if pd.isna(date_val):
        return ""
    try:
        return pd.to_datetime(date_val).strftime('%d/%m/%Y')
    except:
        return str(date_val)

def format_gender(gender_val):
    g = str(gender_val).upper().strip()
    if g.startswith('F') or g.startswith('M'):
        return g[0]
    return ""

@st.cache_data(show_spinner="Procesando datos...", ttl=600)
def process_dataframe(df, equivalences=None, fuzzy_threshold=0.80):
    if df is None: return None
    df = df.copy()
    
    # Normalización básica
    if 'Nº.ID' in df.columns:
        df['Nº.ID'] = pd.to_numeric(df['Nº.ID'], errors='coerce').fillna(0).astype(int)
        
    # Campos calculados
    df['Es_Cedido'] = df.apply(lambda row: is_cedido(row, equivalences, fuzzy_threshold), axis=1)
    df['No_Seleccionable'] = df.apply(is_no_seleccionable, axis=1)
    df['Errores_Datos'] = df.apply(check_data_health, axis=1)
    df['Datos_Validos'] = df['Errores_Datos'].apply(lambda x: len(x) == 0)
    
    # Inicializar columnas de revisión si no existen
    if 'Declaración_Jurada' not in df.columns:
        df['Declaración_Jurada'] = False
    if 'Documento_Cesión' not in df.columns:
        df['Documento_Cesión'] = False
    if 'Errores_Normativos' not in df.columns:
        df['Errores_Normativos'] = ""
    if 'Estado' not in df.columns:
        df['Estado'] = "Pendiente"
    if 'Es_Excluido' not in df.columns:
        df['Es_Excluido'] = False
        
    # Lógica de Estado
    def determine_status(row):
        status = []
        if row['Es_Cedido']: status.append("Cedido")
        if row['No_Seleccionable']: status.append("Extranjero")
        if row['Es_Excluido']: status.append("EXCLUIDO")
        if not row['Datos_Validos']: status.append("Datos Incompletos")
        
        if not status: return "OK"
        return " | ".join(status)

    df['Estado'] = df.apply(determine_status, axis=1)
    
    # Generar columna combinada Jugador
    df['Jugador'] = df['Nombre.1'].fillna('') + ' ' + df['Nombre'].fillna('')
    df['Jugador'] = df['Jugador'].str.strip()
    
    # Normalizar Género
    df['Género_Norm'] = df['Género'].astype(str).str.upper().str.strip()
    
    return df

def apply_comprehensive_check(df, rules_config, team_categories):
    """
    Aplica reglas de validación a nivel de equipo e individual y puebla la columna 'Errores_Normativos'.
    """
    df['Errores_Normativos'] = "" # Resetear errores previos
    
    # Iterar por equipos para aplicar reglas de conjunto
    for team_name, group in df.groupby('Pruebas'):
        category = team_categories.get(team_name, "Sin Asignar")
        rules = rules_config.get(category, {})
        
        team_errors = []
        
        # 0. Filtrar Excluidos para cálculos de equipo
        # Los excluidos NO cuentan para totales, ni ratios, ni nada.
        active_group = group[~group['Es_Excluido']]

        if not rules:
            if category == "Sin Asignar":
                team_errors.append("Equipo sin categoría asignada")
        else:
            # 1. Validación de Totales (Afecta a todo el equipo)
            n_total = len(active_group)
            n_hombres = len(active_group[active_group['Género_Norm'] == 'M'])
            n_mujeres = len(active_group[active_group['Género_Norm'] == 'F'])
            
            cedidos_h = len(active_group[(active_group['Género_Norm'] == 'M') & (active_group['Es_Cedido'])])
            cedidos_m = len(active_group[(active_group['Género_Norm'] == 'F') & (active_group['Es_Cedido'])])

            min_total = rules.get('min_total', 0)
            max_total = rules.get('max_total', 999)
            
            if n_total < min_total: team_errors.append(f"Mínimo total no cumplido ({n_total}/{min_total})")
            if n_total > max_total: team_errors.append(f"Máximo total excedido ({n_total}/{max_total})")
            
            min_gender = rules.get('min_gender', 0)
            if n_hombres < min_gender: team_errors.append(f"Mínimo Hombres no cumplido ({n_hombres}/{min_gender})")
            if n_mujeres < min_gender: team_errors.append(f"Mínimo Mujeres no cumplido ({n_mujeres}/{min_gender})")

            # 2. Validación Ratios Cedidos (Afecta a todo el equipo)
            # Primero verificar si se permiten cedidos en esta categoría
            allow_loaned = rules.get('allow_loaned_players', True)
            
            if not allow_loaned:
                 if cedidos_h > 0 or cedidos_m > 0:
                     team_errors.append("⛔ NO SE PERMITEN CEDIDOS en esta categoría")
            else:
                ratio_table = rules.get('ratio_table', [])
                
                def check_ratio_limit(total, cedidos, table):
                    limit = 0
                    sorted_table = sorted(table, key=lambda x: x['total'])
                    found = False
                    for rule in sorted_table:
                        if total == rule['total']:
                            limit = rule['max_cedidos']
                            found = True
                            break
                        elif rule == sorted_table[-1] and total > rule['total']:
                            limit = rule['max_cedidos']
                            found = True
                    
                    if not found and sorted_table and total < sorted_table[0]['total']:
                         limit = 0 # Menos que el mínimo de la tabla -> 0 cedidos

                    return cedidos <= limit, limit

                ok_h, max_h = check_ratio_limit(n_hombres, cedidos_h, ratio_table)
                ok_m, max_m = check_ratio_limit(n_mujeres, cedidos_m, ratio_table)
                
                if not ok_h: team_errors.append(f"Exceso Cedidos H ({cedidos_h}/{max_h})")
                if not ok_m: team_errors.append(f"Exceso Cedidos M ({cedidos_m}/{max_m})")

            # 3. Validación Documentación INDIVIDUAL (Afecta solo al jugador)
            # Se aplica actualizando el dataframe original directamente en los índices correspondientes
            
            # A) Declaración Jurada
            if rules.get('require_declaration', False):
                # Jugadores del grupo que NO tienen dec. jurada Y NO son de España
                # (Solo se requiere para extranjeros)
                missing_decl_mask = (
                    (df['Pruebas'] == team_name) & 
                    (df['Declaración_Jurada'] == False) & 
                    (df['País'].astype(str).str.upper() != 'SPAIN') &
                    (df['Es_Excluido'] == False)
                )
                df.loc[missing_decl_mask, 'Errores_Normativos'] = df.loc[missing_decl_mask, 'Errores_Normativos'].apply(lambda x: f"{x} | ⚠️ Falta Dec. Jurada" if x else "⚠️ Falta Dec. Jurada")

            # B) Documento Cesión
            if rules.get('require_loan_doc', False):
                # Jugadores CEDIDOS del grupo que NO tienen doc. cesión
                missing_loan_mask = (df['Pruebas'] == team_name) & (df['Es_Cedido'] == True) & (df['Documento_Cesión'] == False) & (df['Es_Excluido'] == False)
                df.loc[missing_loan_mask, 'Errores_Normativos'] = df.loc[missing_loan_mask, 'Errores_Normativos'].apply(lambda x: f"{x} | ⚠️ Falta Doc. Cesión" if x else "⚠️ Falta Doc. Cesión")

            # C) No Seleccionables (NUEVO)
            allow_non_sel = rules.get('allow_non_selectable', True)
            minors_only = rules.get('non_selectable_minors_only', False)

            if not allow_non_sel:
                # Marcar error a todos los no seleccionables del equipo
                non_sel_mask = (df['Pruebas'] == team_name) & (df['No_Seleccionable'] == True) & (df['Es_Excluido'] == False)
                df.loc[non_sel_mask, 'Errores_Normativos'] = df.loc[non_sel_mask, 'Errores_Normativos'].apply(lambda x: f"{x} | ⛔ No Seleccionable NO permitido" if x else "⛔ No Seleccionable NO permitido")
            
            elif minors_only:
                # Permitidos pero SOLO MENORES
                # Calcular edad. Asumimos F.Nac es datetime o string parseable.
                # Necesitamos año actual o fecha referencia. Usaremos 1 Enero del año actual o similar.
                # Mejor: Calcular edad a 31/12 del año actual (standard BWF/FESBA?)
                # Simplificación: Menor de 18 años.
                
                current_year = datetime.now().year
                
                def is_adult(dob_val):
                    try:
                        dob = pd.to_datetime(dob_val)
                        age = current_year - dob.year
                        return age >= 18
                    except:
                        return True # Ante la duda, es adulto (error safe)

                # Identificar No Seleccionables que son Adultos
                # Iteramos sobre el grupo activo para chequear edad
                for idx, row in active_group.iterrows():
                    if row['No_Seleccionable']:
                        if is_adult(row['F.Nac']):
                            # Marcar error en DF principal
                            current_err = df.at[idx, 'Errores_Normativos']
                            new_err = "⛔ No Seleccionable Mayor de Edad"
                            df.at[idx, 'Errores_Normativos'] = f"{current_err} | {new_err}" if current_err else new_err

        # Aplicar errores de EQUIPO a TODOS los miembros (NO EXCLUIDOS)
        if team_errors:
            error_str = " | ".join([f"⛔ EQUIPO: {e}" for e in team_errors])
            # Solo aplicar a las filas de este equipo QUE NO ESTÉN EXCLUIDAS
            group_indices = df[(df['Pruebas'] == team_name) & (df['Es_Excluido'] == False)].index
            df.loc[group_indices, 'Errores_Normativos'] = df.loc[group_indices, 'Errores_Normativos'].apply(lambda x: f"{x} | {error_str}" if x else error_str)

    # Validaciones Individuales Globales (No dependen de reglas de categoría por ahora)
    # No Seleccionable: Ya no se considera error normativo per se, solo si falta documentación.
    # mask_extranjero = df['No_Seleccionable'] == True
    # df.loc[mask_extranjero, 'Errores_Normativos'] = df.loc[mask_extranjero, 'Errores_Normativos'].apply(lambda x: f"{x} | ⚠️ JUGADOR: No Seleccionable" if x else "⚠️ JUGADOR: No Seleccionable")

    return df

# --- LÓGICA DE AUDITORÍA DINÁMICA (V2.0) ---
def calculate_team_compliance(df, rules_config, team_categories):
    """
    Genera un DataFrame resumen con el cumplimiento normativo por equipo,
    aplicando las reglas específicas de la categoría asignada a cada equipo.
    """
    teams_data = []
    
    for team_name, group in df.groupby('Pruebas'):
        # 1. Identificar Reglas
        category = team_categories.get(team_name, "Sin Asignar")
        rules = rules_config.get(category, {})
        
        # Ensure Es_Excluido exists (backward compatibility)
        if 'Es_Excluido' not in group.columns:
            group = group.copy()
            group['Es_Excluido'] = False
        
        # Si no hay reglas para la categoría (ej: Sin Asignar), saltar validación estricta
        if not rules:
            teams_data.append({
                "Equipo": team_name,
                "Categoría": category,
                "Total J.": len(group),
                "Hombres": len(group[group['Género_Norm'] == 'M']),
                "Mujeres": len(group[group['Género_Norm'] == 'F']),
                "Cedidos H": f"{len(group[(group['Género_Norm'] == 'M') & (group['Es_Cedido'])])} (?)",
                "Cedidos M": f"{len(group[(group['Género_Norm'] == 'F') & (group['Es_Cedido'])])} (?)",
                "Estado General": "⚠️ Config. Pendiente",
                "Detalles": "Categoría no asignada o sin reglas definidas. Ve a Configuración."
            })
            continue

        # 2. Calcular Totales (Ignorando Excluidos)
        active_group = group[~group['Es_Excluido']]
        
        n_total = len(active_group)
        n_hombres = len(active_group[active_group['Género_Norm'] == 'M'])
        n_mujeres = len(active_group[active_group['Género_Norm'] == 'F'])
        
        cedidos_h = len(active_group[(active_group['Género_Norm'] == 'M') & (active_group['Es_Cedido'])])
        cedidos_m = len(active_group[(active_group['Género_Norm'] == 'F') & (active_group['Es_Cedido'])])
        
        propios_h = n_hombres - cedidos_h
        propios_m = n_mujeres - cedidos_m
        
        # 3. Validar contra Reglas (Dynamic)
        issues = []
        
        # A) Mínimos y Máximos Totales
        min_total = rules.get('min_total', 0)
        max_total = rules.get('max_total', 999)
        if n_total < min_total: issues.append(f"Min {min_total} jugadores")
        if n_total > max_total: issues.append(f"Max {max_total} jugadores")
        
        # B) Mínimos Género
        min_gender = rules.get('min_gender', 0)
        if n_hombres < min_gender: issues.append(f"Min {min_gender} Hombres")
        if n_mujeres < min_gender: issues.append(f"Min {min_gender} Mujeres")
        
        # C) Ratio Cedidos (Tabla Dinámica)
        ratio_table = rules.get('ratio_table', [])
        
        def check_ratio_dynamic(total_g, cedidos_g, table):
            # Buscar la regla en la tabla que corresponda al total
            # La tabla suele ser [{"total": 4, "max_cedidos": 1}, ...]
            # Si no encuentra exacto, buscar el más cercano inferior o superior según lógica.
            # Asumiremos "rango" o exact match. En la tabla 9.1, "10 o más" implica lógica >=.
            
            allowed = 0
            found_rule = False
            
            # Ordenar tabla por total ascendente para evaluar >=
            sorted_table = sorted(table, key=lambda x: x['total'])
            
            for rule in sorted_table:
                if total_g == rule['total']:
                    allowed = rule['max_cedidos']
                    found_rule = True
                    break
                elif rule == sorted_table[-1] and total_g > rule['total']:
                     # Caso "10 o más" -> aplica la última regla
                     allowed = rule['max_cedidos']
                     found_rule = True
            
            # Si tiene menos jugadores que el mínimo de la tabla (ej < 4), 
            # asumimos 0 cedidos permitidos o permitimos 0.
            if not found_rule:
                if sorted_table and total_g < sorted_table[0]['total']:
                    allowed = 0 # Muy pocos jugadores para tener cedidos
                else:
                    allowed = 0 # Fallback
            
            return cedidos_g <= allowed, allowed

        ratio_h_ok, max_h = check_ratio_dynamic(n_hombres, cedidos_h, ratio_table)
        ratio_m_ok, max_m = check_ratio_dynamic(n_mujeres, cedidos_m, ratio_table)
        
        if not ratio_h_ok: issues.append(f"Exceso Cedidos H ({cedidos_h}/{max_h})")
        if not ratio_m_ok: issues.append(f"Exceso Cedidos M ({cedidos_m}/{max_m})")

        # D) Documentación (Si las reglas lo exigen)
        # Por ahora es un check visual, no bloqueante 'NO APTO' estricto salvo configuración.
        if rules.get('require_declaration', False):
            missing_decl = len(group[~group['Declaración_Jurada']])
            if missing_decl > 0: issues.append(f"Faltan {missing_decl} Dec. Juradas")
            
        if rules.get('require_loan_doc', False):
            missing_loan = len(group[group['Es_Cedido'] & ~group['Documento_Cesión']])
            if missing_loan > 0: issues.append(f"Faltan {missing_loan} Doc. Cesión")

        # Estado General
        is_clean = len(issues) == 0
        
        teams_data.append({
            "Equipo": team_name,
            "Categoría": category,
            "Total J.": n_total,
            "Hombres": n_hombres,
            "Mujeres": n_mujeres,
            "Cedidos H": f"{cedidos_h} (Max {max_h})",
            "Cedidos M": f"{cedidos_m} (Max {max_m})",
            "Estado General": "✅ APTO" if is_clean else "❌ NO APTO",
            "Detalles": ", ".join(issues) if issues else "Cumple Normativa"
        })
        
    return pd.DataFrame(teams_data)

def generate_players_csv(df):
    valid_df = df[df['Datos_Validos']].copy()
    export_df = pd.DataFrame()
    export_df['memberid'] = valid_df['Nº.ID'].astype(str).str.replace(r'\.0$', '', regex=True)
    export_df['clubid'] = valid_df['Club']
    export_df['lastname'] = valid_df['Nombre']
    export_df['firstname'] = valid_df['Nombre.1']
    export_df['dob'] = valid_df['F.Nac'].apply(format_date_for_export)
    export_df['gender'] = valid_df['Género'].apply(format_gender)
    export_df['country'] = valid_df['País']
    return export_df.to_csv(index=False)

def generate_team_players_csv(df):
    valid_df = df[df['Datos_Validos']].copy()
    export_df = pd.DataFrame()
    export_df['Team'] = valid_df['Pruebas']
    export_df['Lidnummer'] = valid_df['Nº.ID'].astype(str).str.replace(r'\.0$', '', regex=True)
    export_df['Positie'] = 0
    return export_df.to_csv(index=False)

def merge_dataframes_with_log(df_current, df_new):
    """
    Fusiona df_new sobre df_current.
    - Añade jugadores nuevos (por ID).
    - Actualiza jugadores existentes si cambia Equipo o Club.
    - Retorna: (df_merged, log_messages_list)
    """
    logs = []
    
    # Asegurar tipos
    df_current['Nº.ID'] = df_current['Nº.ID'].astype(str).str.strip()
    df_new['Nº.ID'] = df_new['Nº.ID'].astype(str).str.strip()
    
    existing_ids = set(df_current['Nº.ID'].dropna())
    
    # 1. Separar Nuevos
    df_new_players = df_new[~df_new['Nº.ID'].isin(existing_ids)].copy()
    if not df_new_players.empty:
        logs.append(f"➕ **AÑADIDOS {len(df_new_players)} JUGADORES NUEVOS:**")
        for _, row in df_new_players.iterrows():
            logs.append(f"- {row['Nombre']} ({row['Nº.ID']}) -> {row['Pruebas']}")
    
    # 2. Procesar Actualizaciones
    df_updates = df_new[df_new['Nº.ID'].isin(existing_ids)].copy()
    updates_count = 0
    
    if not df_updates.empty:
        logs.append(f"🔄 **REVISANDO {len(df_updates)} JUGADORES EXISTENTES...**")
        
    for _, row in df_updates.iterrows():
        pid = row['Nº.ID']
        # Buscar índice en original
        mask = df_current['Nº.ID'] == pid
        if not mask.any(): continue
        
        idx = df_current[mask].index[0]
        
        # Comparar Campos Clave
        old_team = str(df_current.at[idx, 'Pruebas']).strip()
        new_team = str(row['Pruebas']).strip()
        
        old_club = str(df_current.at[idx, 'Club']).strip()
        new_club = str(row['Club']).strip()
        
        changes = []
        
        # Ignorar actualizaciones si el nuevo valor es 'nan' o vacío
        if new_team.lower() == 'nan' or not new_team:
            pass # No actualizar equipo si viene vacío
        elif old_team != new_team:
            df_current.at[idx, 'Pruebas'] = new_team
            changes.append(f"Equipo: '{old_team}' ➡️ '{new_team}'")
            
        if new_club.lower() == 'nan' or not new_club:
            pass
        elif old_club != new_club:
            df_current.at[idx, 'Club'] = new_club
            changes.append(f"Club: '{old_club}' ➡️ '{new_club}'")
            
        if changes:
            updates_count += 1
            # Añadir nota interna
            current_note = str(df_current.at[idx, 'Notas_Revision'])
            change_note = f" [MOD: {', '.join(changes)}]"
            if change_note not in current_note:
                df_current.at[idx, 'Notas_Revision'] = current_note + change_note
                
            logs.append(f"✏️ **ACTUALIZADO:** {row['Nombre']} ({pid}): {', '.join(changes)}")

    # 3. Concatenar
    if not df_new_players.empty:
        df_merged = pd.concat([df_current, df_new_players], ignore_index=True)
    else:
        df_merged = df_current
        
    summary = f"✅ **RESUMEN:** {len(df_new_players)} añadidos, {updates_count} actualizados."
    logs.insert(0, summary)
    
    return df_merged, logs
