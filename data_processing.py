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
        # 1. DYNAMIC HEADER DETECTION
        if hasattr(file, 'seek'): file.seek(0)
        
        # Read first few rows to find header
        # Using header=None to look for keywords
        temp_df = pd.read_excel(file, header=None, nrows=20)
        header_row_idx = 0
        found_header = False
        
        # Keywords to identify header row
        keywords = ['nombre', 'club', 'equipo', 'licencia', 'n.']
        
        for idx, row in temp_df.iterrows():
            row_str = row.astype(str).str.lower().tolist()
            matches = sum(1 for k in keywords if any(k in s for s in row_str))
            # If we match at least 2 distinct keywords (e.g. Nombre AND Club)
            if matches >= 2:
                header_row_idx = idx
                found_header = True
                break
        
        # Reload with correct header
        if hasattr(file, 'seek'): file.seek(0)
        
        if found_header:
            df = pd.read_excel(file, header=header_row_idx)
        else:
            # Fallback
            df = pd.read_excel(file, header=3) 

        # 0. BACKUP DETECTION / SYSTEM RESTORE
        # Si el archivo tiene las columnas internas del sistema (backup completo),
        # asumimos que es correcto y saltamos el mapeo difuso para evitar re-iniciar columnas.
        system_cols = ['Nº.ID', 'Nombre', 'Pruebas', 'Estado', 'Notas_Revision', 'Declaración_Jurada', 'Es_Excluido']
        # Comprobar si están presentes las columnas clave (headers exactos)
        present_cols = [c for c in system_cols if c in df.columns]
        is_backup = len(present_cols) >= len(system_cols) - 1
        
        if is_backup:
            # FORCE TYPES FOR BACKUP RESTORE
            # 1. Clean IDs
            if 'Nº.ID' in df.columns:
                 df['Nº.ID'] = df['Nº.ID'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
            
            # 2. Ensure Booleans are actual bools (Excel saves them as TRUE/FALSE strings usually)
            bool_cols = ['Declaración_Jurada', 'Documento_Cesión', 'Es_Excluido', 'Es_Cedido', 'No_Seleccionable', 'Datos_Validos', 'Licencia_Subsanada']
            for c in bool_cols:
                if c in df.columns:
                    # Convertir valores mixtos a booleano real
                    def strict_bool(x):
                        s = str(x).upper().strip()
                        return s in ['TRUE', '1', 'YES', 'SI']
                    
                    df[c] = df[c].apply(strict_bool)
            
            # Devolvemos el DF tal cual, confiando en su estructura
            return df

        # 2. STANDARD COLUMN MAPPING (Strict)
        col_map = {}
        cols = df.columns.tolist()
        
        for col in cols:
            c_str = str(col).strip()
            c_lower = c_str.lower()
            
            # EXPLICIT: Ignore "N." (Row Counter - first column)
            if c_str == "N.":
                continue
            
            # MATCH LICENSE ID
            # Pattern: ends with ".ID" or ".id" (case insensitive)
            # Covers: "Nº.ID", "N║.ID", "N.ID", "Licencia", etc.
            is_id_col = False
            
            # Check if column ends with ".id" (most reliable pattern)
            if c_lower.endswith('.id'):
                is_id_col = True
            # Check for "licencia" anywhere in the name
            elif 'licencia' in c_lower:
                is_id_col = True
            # Check for "memberid" or similar
            elif 'memberid' in c_lower.replace(' ', '').replace('_', ''):
                is_id_col = True
                
            if is_id_col:
                col_map[col] = 'Nº.ID'
                continue
            
            # MATCH CLUB (Keep as Club)
            if 'club' in c_lower:
                col_map[col] = 'Club'
                continue
                
            # MATCH TEAM/PRUEBAS (Usually "Pruebas" or "Equipo")
            if 'equipo' in c_lower:
                col_map[col] = 'Pruebas'
                continue
                 
        # Safety: If multiple columns mapped to 'Nº.ID'
        mapped_ids = [k for k,v in col_map.items() if v == 'Nº.ID']
        if len(mapped_ids) > 1:
            best = max(mapped_ids, key=len)
            for k in mapped_ids:
                if k != best: del col_map[k]
                
        df.rename(columns=col_map, inplace=True)

        # 2b. FORCE ID TO STRING (Support Alphanumeric)
        if 'Nº.ID' in df.columns:
            df['Nº.ID'] = df['Nº.ID'].astype(str).str.strip()
            # Remove potential .0 from float conversion of integers
            df['Nº.ID'] = df['Nº.ID'].apply(lambda x: x.replace('.0', '') if x.endswith('.0') else x)

        # 3. TRANSFER DETECTION (Multi-Club)
        if 'Estado_Transferencia' not in df.columns:
                df['Estado_Transferencia'] = None
        
        if 'Equipo' in df.columns:
            mask_transfer = df['Equipo'].astype(str).str.contains(',', na=False)
            df.loc[mask_transfer, 'Estado_Transferencia'] = '⚠️ MULTI-CLUB / TRANSFER'
        
        # 4. SMART ENCODING FIX (Detect mojibake from bad imports)
        def smart_fix_encoding(text):
            """
            Fixes text that looks like UTF-8 decoded as Latin-1 (Mojibake).
            Example: 'AlfajarÃn' -> 'Alfajarín'
            """
            if pd.isna(text): 
                return text
            text_str = str(text)
            
            # Optimization: Only try invalid sequences containing 'Ã' (common in UTF-8 mojibake)
            if 'Ã' in text_str:
                try:
                    # Attempt to reversible fix
                    fixed = text_str.encode('latin-1').decode('utf-8')
                    return fixed
                except (UnicodeDecodeError, UnicodeEncodeError):
                    # Not actually encoded that way, return original
                    return text_str
            return text_str

        # Apply to crucial text columns
        text_cols = ['Club', 'Pruebas', 'Nombre', 'Nombre.1', 'País', 'Equipo']
        for col in text_cols:
            if col in df.columns:
                df[col] = df[col].apply(smart_fix_encoding)
            
        return df
    except Exception as e:
        print(f"Error loading data: {e}")
        return None

def identify_best_id_column(df):
    """
    Analyzes columns to find the most likely 'License ID'.
    Candidates: 'N.', 'Nº.ID', '*ID*', '*Licencia*'.
    Criteria:
    - Numeric content
    - Not a sequential row counter (1, 2, 3...)
    - Values in plausible range (e.g., > 1000)
    """
    best_col = None
    best_score = -1
    
    import re
    id_pattern = re.compile(r'n[º°\?║\.]*.id', re.IGNORECASE)
    
    for col in df.columns:
        name = str(col).strip()
        lower_name = name.lower()
        score = 0
        
        # 1. NAME CHECK
        is_candidate = False
        if name == 'N.' or id_pattern.search(name) or 'licencia' in lower_name or 'id' in lower_name:
            is_candidate = True
            
        if not is_candidate:
            continue
            
        # 2. CONTENT CHECK
        # Sample non-null values
        series = df[col].dropna()
        if len(series) == 0:
            continue
            
        try:
            nums = pd.to_numeric(series, errors='coerce').dropna()
            if len(nums) == 0: continue
            
            mean_val = nums.mean()
            min_val = nums.min()
            
            # CHECK SEQUENTIAL (Row Counter)
            is_sequential = False
            if len(nums) > 10:
                sample = nums.iloc[:10].tolist()
                diffs = [sample[i+1]-sample[i] for i in range(len(sample)-1)]
                # If mostly 1s and starts low
                if all(d == 1 for d in diffs) and min_val <= 1:
                    is_sequential = True
            
            if is_sequential: 
                score -= 50 # Strong penalty for row counters
            
            # CHECK RANGE
            # Licenses usually 4-6 digits (1000 - 999999)
            if 1000 <= mean_val <= 900000:
                score += 20
            elif mean_val < 100:
                score -= 10 # Likely too small to be a license ID
                
            # NAME BONUSES
            if 'id' in lower_name and 'n.' in lower_name: score += 10 # e.g. "Nº.ID"
            if name == 'N.': score += 5 # Neutral/Positive if data matches
            
            if score > best_score:
                best_score = score
                best_col = col
                
        except:
            continue
            
    return best_col

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
    if 'Licencia_Subsanada' not in df.columns:
        df['Licencia_Subsanada'] = False
        
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
    
    # Ensure required columns exist before creating Jugador
    if 'Nombre.1' not in df.columns:
        df['Nombre.1'] = ''
    if 'Nombre' not in df.columns:
        df['Nombre'] = ''
    
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
        category = _get_category_robust(team_name, team_categories)
        rules = rules_config.get(category, {})
        
        team_errors = []
        
        # 0. Filtrar Excluidos para cálculos de equipo
        # Los excluidos NO cuentan para totales, ni ratios, ni nada.
        es_excluido = group['Es_Excluido'].fillna(False).astype(bool)
        active_group = group[~es_excluido]

        if not rules:
            if category == "Sin Asignar":
                team_errors.append("Equipo sin categoría asignada")
        else:
            # 1. Validación de Totales (Afecta a todo el equipo)
            n_total = len(active_group)
            n_hombres = len(active_group[active_group['Género_Norm'] == 'M'])
            n_mujeres = len(active_group[active_group['Género_Norm'] == 'F'])
            
            es_cedido_active = active_group['Es_Cedido'].fillna(False).astype(bool)
            cedidos_h = len(active_group[(active_group['Género_Norm'] == 'M') & es_cedido_active])
            cedidos_m = len(active_group[(active_group['Género_Norm'] == 'F') & es_cedido_active])

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
                    (df['País'].astype(str).str.upper() != 'ESPAÑA') &
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
                df.loc[non_sel_mask, 'Errores_Normativos'] = df.loc[non_sel_mask, 'Errores_Normativos'].apply(lambda x: f"{x} | ⚠️ No Seleccionable NO permitido" if x else "⚠️ No Seleccionable NO permitido")
            
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

                    # D) Validación FESBA Check
                    if 'Validacion_FESBA' in row:
                        val_status = str(row['Validacion_FESBA']).upper()
                        current_err = str(df.at[idx, 'Errores_Normativos']) if pd.notna(df.at[idx, 'Errores_Normativos']) else ""
                        
                        fesba_err = None
                        if "NO ENCONTRADO" in val_status or "FICHA NO ENCONTRADA" in val_status:
                             fesba_err = "HN-p" # Homologación Nacional pendiente
                        elif '❌' in val_status:
                             fesba_err = "⛔ Incidencia FESBA"
                        
                        if fesba_err:
                             # Avoid duplicates
                             if fesba_err not in current_err:
                                 new_val = f"{current_err} | {fesba_err}" if current_err else fesba_err
                                 df.at[idx, 'Errores_Normativos'] = new_val

            # E) Plazo de Inscripción (Licencia Nacional)
            reg_deadline_str = rules.get('registration_deadline')
            check_dates = bool(reg_deadline_str and 'Fecha_Inicio_Licencia' in df.columns)
            
            if check_dates:
                try:
                    deadline_dt = datetime.strptime(reg_deadline_str, "%Y-%m-%d")
                    # Validar solo filas de este grupo (equipo) que no estén excluidas
                    # Y que si existe columna Subsanada, sea False
                    check_mask = (df['Pruebas'] == team_name) & (df['Es_Excluido'] == False)
                    if 'Licencia_Subsanada' in df.columns:
                        check_mask = check_mask & (df['Licencia_Subsanada'] == False)
                    
                    target_indices = df[check_mask].index
                    
                    for idx in target_indices:
                        val_fesba = str(df.at[idx, 'Validacion_FESBA']) if 'Validacion_FESBA' in df.columns else ""
                        # Solo afecta a licencias Nacionales/Homologadas
                        if "Nacional" in val_fesba or "HN" in val_fesba or "Homologada" in val_fesba:
                            start_str = str(df.at[idx, 'Fecha_Inicio_Licencia'])
                            # Formato esperado DD/MM/YYYY
                            if start_str and start_str.lower() not in ['nan', 'none', '', '?']:
                                try:
                                    lic_dt = datetime.strptime(start_str, "%d/%m/%Y")
                                    if lic_dt > deadline_dt:
                                        err = f"⛔ Fuera de Plazo ({start_str})"
                                        curr = df.at[idx, 'Errores_Normativos']
                                        df.at[idx, 'Errores_Normativos'] = f"{curr} | {err}" if curr else err
                                except:
                                    pass
                except:
                    pass

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

# Helper para búsqueda robusta de categorías
def _get_category_robust(team_name, team_categories):
    team_name = str(team_name)
    # 1. Exact Match
    if team_name in team_categories:
        return team_categories[team_name]
    
    # 2. Stripped Match
    if team_name.strip() in team_categories:
        return team_categories[team_name.strip()]
        
    # 3. Normalized Match (Ignoring case and accents)
    norm_target = normalize_name(team_name).lower()
    for cat_team, cat_val in team_categories.items():
        if normalize_name(cat_team).lower() == norm_target:
            return cat_val
            
    return "Sin Asignar"

# --- LÓGICA DE AUDITORÍA DINÁMICA (V2.0) ---
def calculate_team_compliance(df, rules_config, team_categories):
    """
    Genera un DataFrame resumen con el cumplimiento normativo por equipo,
    aplicando las reglas específicas de la categoría asignada a cada equipo.
    """
    teams_data = []
    
    for team_name, group in df.groupby('Pruebas'):
        # 1. Identificar Reglas
        category = _get_category_robust(team_name, team_categories)
        rules = rules_config.get(category, {})
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
        # Ensure Es_Excluido is boolean
        es_excluido = group['Es_Excluido'].fillna(False).astype(bool)
        active_group = group[~es_excluido]
        
        n_total = len(active_group)
        n_hombres = len(active_group[active_group['Género_Norm'] == 'M'])
        n_mujeres = len(active_group[active_group['Género_Norm'] == 'F'])
        
        es_cedido_grp = active_group['Es_Cedido'].fillna(False).astype(bool)
        cedidos_h = len(active_group[(active_group['Género_Norm'] == 'M') & es_cedido_grp])
        cedidos_m = len(active_group[(active_group['Género_Norm'] == 'F') & es_cedido_grp])
        
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
            # Solo contar jugadores extranjeros (no españoles) que faltan Dec. Jurada
            if 'País' in group.columns:
                extranjeros = group[group['País'].astype(str).str.lower().str.strip() != 'spain']
                missing_decl = len(extranjeros[~extranjeros['Declaración_Jurada']])
            else:
                missing_decl = 0  # Sin columna País, no podemos verificar
            if missing_decl > 0: issues.append(f"Faltan {missing_decl} Dec. Juradas (extranjeros)")
            
        if rules.get('require_loan_doc', False):
            es_cedido_bool = group['Es_Cedido'].fillna(False).astype(bool)
            doc_cesion_bool = group['Documento_Cesión'].fillna(False).astype(bool)
            missing_loan = len(group[es_cedido_bool & ~doc_cesion_bool])
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

def load_club_ids_mapping():
    """Load ClubName -> ClubNumber mapping from config."""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config', 'club_ids.json')
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def load_team_clubid_overrides():
    """Load manual Team -> ClubID overrides."""
    override_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config', 'team_clubid_override.json')
    if os.path.exists(override_path):
        try:
            with open(override_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def get_clubid_for_team(team_name, club_ids_mapping):
    """
    Get ClubNumber for a team name using fuzzy matching.
    The clubid is determined by the TEAM (Pruebas) where the player competes,
    NOT by the player's origin club. This applies to both own players and loaned players.
    """
    if not team_name or pd.isna(team_name):
        return ""
    
    team_str = str(team_name).strip()
    
    # 1. Exact match
    if team_str in club_ids_mapping:
        return club_ids_mapping[team_str]
    
    # 2. Case-insensitive match
    for club_name, club_id in club_ids_mapping.items():
        if club_name.upper() == team_str.upper():
            return club_id
    
    # 3. Normalized/fuzzy match
    norm_team = normalize_name(team_str)
    for club_name, club_id in club_ids_mapping.items():
        norm_club = normalize_name(club_name)
        # Substring check
        if norm_team in norm_club or norm_club in norm_team:
            return club_id
        # Similarity check
        if calculate_similarity(team_str, club_name) >= 0.85:
            return club_id
    
    return ""  # Not found

def generate_players_csv(df):
    valid_df = df[df['Datos_Validos']].copy()
    
    # FILTERS REVERTED per user request ("ponerlo igual").
    # Exporting raw valid data without excluding specific normative errors.
    
    # Load club IDs mapping (auto) and manual overrides
    club_ids_mapping = load_club_ids_mapping()
    team_overrides = load_team_clubid_overrides()
    
    def get_final_clubid(team_name):
        """Get ClubID: first check manual override, then auto-detect."""
        if not team_name or pd.isna(team_name):
            return ""
        team_str = str(team_name).strip()
        
        # 1. Check manual override first (highest priority)
        if team_str in team_overrides:
            return team_overrides[team_str]
        
        # 2. Case-insensitive override check
        for override_team, override_id in team_overrides.items():
            if override_team.upper() == team_str.upper():
                return override_id
        
        # 3. Fall back to auto-detection
        return get_clubid_for_team(team_str, club_ids_mapping)
    
    def build_lastname_with_markers(row):
        """
        Build lastname with status markers:
        - (C) = Cedido (loaned player)
        - (DJ-p) = Declaración Jurada pendiente
        - (HN-p) = Homologación Nacional pendiente (no active national license)
        """
        lastname = str(row.get('Nombre', '')).strip()
        if pd.isna(lastname) or lastname.lower() == 'nan':
            lastname = ""
        
        markers = []
        
        # Check if Cedido
        es_cedido = row.get('Es_Cedido', False)
        if es_cedido == True:
            markers.append("C")
        
        # Check if missing Declaración Jurada (only for non-Spanish players)
        pais = str(row.get('País', '')).upper().strip()
        decl_jurada = row.get('Declaración_Jurada', False)
        if pais != 'SPAIN' and pais != 'ESPAÑA' and not decl_jurada:
            markers.append("DJ-p")
        
        # Check if missing Homologación Nacional (national license)
        # This is determined by Validacion_FESBA column
        validacion = str(row.get('Validacion_FESBA', '')).upper()
        has_national_license = False
        if '✅' in validacion and ('NACIONAL' in validacion or 'HN' in validacion or 'HOMOLOGADA' in validacion):
            has_national_license = True
        
        if not has_national_license:
            # Also check if it says "NO ENCONTRADO" or has error
            if 'NO ENCONTRADO' in validacion or '❌' in validacion or not validacion.strip():
                markers.append("HN-p")
            elif 'NO NAC' in validacion or 'AUTONÓMICA' in validacion or 'PROVINCIAL' in validacion:
                # Has license but not national
                markers.append("HN-p")
        
        # Build final lastname
        if markers:
            lastname = f"{lastname} ({', '.join(markers)})"
        
        return lastname
    
    def normalize_text_for_export(text):
        """Clean text for CSV export - just strip whitespace, data is already correct."""
        if pd.isna(text):
            return ""
        return str(text).strip()
    
    export_df = pd.DataFrame()
    export_df['memberid'] = valid_df['Nº.ID'].astype(str).str.replace(r'\.0$', '', regex=True)
    
    # ClubID is determined by the TEAM (Pruebas) where the player competes
    # This applies to BOTH own players AND loaned players
    export_df['clubid'] = valid_df['Pruebas'].apply(get_final_clubid)
    
    # Build lastname with status markers and normalize
    export_df['lastname'] = valid_df.apply(build_lastname_with_markers, axis=1).apply(normalize_text_for_export)
    export_df['firstname'] = valid_df['Nombre.1'].apply(normalize_text_for_export)
    export_df['dob'] = valid_df['F.Nac'].apply(format_date_for_export)
    export_df['gender'] = valid_df['Género'].apply(format_gender)
    
    # Convert country names to IOC codes
    def country_to_ioc_code(country):
        """Convert country name to IOC/ISO 3-letter code."""
        if pd.isna(country):
            return ""
        country_str = str(country).strip().upper()
        
        # Comprehensive mapping of country names to IOC codes
        ioc_mapping = {
            # Spanish variants
            'SPAIN': 'ESP', 'ESPAÑA': 'ESP', 'ESPANA': 'ESP',
            # Common countries
            'FRANCE': 'FRA', 'FRANCIA': 'FRA',
            'GERMANY': 'GER', 'ALEMANIA': 'GER', 'DEUTSCHLAND': 'GER',
            'ITALY': 'ITA', 'ITALIA': 'ITA',
            'PORTUGAL': 'POR',
            'UNITED KINGDOM': 'GBR', 'UK': 'GBR', 'GREAT BRITAIN': 'GBR', 'REINO UNIDO': 'GBR', 'ENGLAND': 'GBR',
            'UNITED STATES': 'USA', 'USA': 'USA', 'ESTADOS UNIDOS': 'USA', 'EE.UU.': 'USA',
            'NETHERLANDS': 'NED', 'HOLANDA': 'NED', 'PAISES BAJOS': 'NED', 'PAÍSES BAJOS': 'NED',
            'BELGIUM': 'BEL', 'BELGICA': 'BEL', 'BÉLGICA': 'BEL',
            'SWITZERLAND': 'SUI', 'SUIZA': 'SUI',
            'AUSTRIA': 'AUT',
            'POLAND': 'POL', 'POLONIA': 'POL',
            'RUSSIA': 'RUS', 'RUSIA': 'RUS',
            'CHINA': 'CHN',
            'JAPAN': 'JPN', 'JAPON': 'JPN', 'JAPÓN': 'JPN',
            'SOUTH KOREA': 'KOR', 'KOREA': 'KOR', 'COREA': 'KOR', 'COREA DEL SUR': 'KOR',
            'INDIA': 'IND',
            'BRAZIL': 'BRA', 'BRASIL': 'BRA',
            'ARGENTINA': 'ARG',
            'MEXICO': 'MEX', 'MÉXICO': 'MEX',
            'COLOMBIA': 'COL',
            'CHILE': 'CHI',
            'PERU': 'PER', 'PERÚ': 'PER',
            'VENEZUELA': 'VEN',
            'ECUADOR': 'ECU',
            'CUBA': 'CUB',
            'DOMINICAN REPUBLIC': 'DOM', 'REPUBLICA DOMINICANA': 'DOM', 'REPÚBLICA DOMINICANA': 'DOM',
            'CANADA': 'CAN', 'CANADÁ': 'CAN',
            'AUSTRALIA': 'AUS',
            'NEW ZEALAND': 'NZL', 'NUEVA ZELANDA': 'NZL',
            'SWEDEN': 'SWE', 'SUECIA': 'SWE',
            'NORWAY': 'NOR', 'NORUEGA': 'NOR',
            'DENMARK': 'DEN', 'DINAMARCA': 'DEN',
            'FINLAND': 'FIN', 'FINLANDIA': 'FIN',
            'IRELAND': 'IRL', 'IRLANDA': 'IRL',
            'CZECH REPUBLIC': 'CZE', 'CHEQUIA': 'CZE', 'REPUBLICA CHECA': 'CZE',
            'ROMANIA': 'ROU', 'RUMANIA': 'ROU', 'RUMANÍA': 'ROU',
            'HUNGARY': 'HUN', 'HUNGRIA': 'HUN', 'HUNGRÍA': 'HUN',
            'UKRAINE': 'UKR', 'UCRANIA': 'UKR',
            'GREECE': 'GRE', 'GRECIA': 'GRE',
            'TURKEY': 'TUR', 'TURQUIA': 'TUR', 'TURQUÍA': 'TUR',
            'MOROCCO': 'MAR', 'MARRUECOS': 'MAR',
            'EGYPT': 'EGY', 'EGIPTO': 'EGY',
            'SOUTH AFRICA': 'RSA', 'SUDAFRICA': 'RSA', 'SUDÁFRICA': 'RSA',
            'NIGERIA': 'NGR',
            'INDONESIA': 'INA',
            'MALAYSIA': 'MAS', 'MALASIA': 'MAS',
            'THAILAND': 'THA', 'TAILANDIA': 'THA',
            'VIETNAM': 'VIE',
            'PHILIPPINES': 'PHI', 'FILIPINAS': 'PHI',
            'SINGAPORE': 'SGP', 'SINGAPUR': 'SGP',
            'TAIWAN': 'TPE',
            'HONG KONG': 'HKG',
            'PAKISTAN': 'PAK', 'PAKISTÁN': 'PAK',
            'BANGLADESH': 'BAN',
            'SRI LANKA': 'SRI',
            'NEPAL': 'NEP',
            'IRAN': 'IRI', 'IRÁN': 'IRI',
            'IRAQ': 'IRQ',
            'ISRAEL': 'ISR',
            'LEBANON': 'LBN', 'LIBANO': 'LBN', 'LÍBANO': 'LBN',
            'SAUDI ARABIA': 'KSA', 'ARABIA SAUDITA': 'KSA', 'ARABIA SAUDÍ': 'KSA',
            'UNITED ARAB EMIRATES': 'UAE', 'EAU': 'UAE', 'EMIRATOS ARABES': 'UAE',
            'BULGARIA': 'BUL',
            'CROATIA': 'CRO', 'CROACIA': 'CRO',
            'SERBIA': 'SRB',
            'SLOVENIA': 'SLO', 'ESLOVENIA': 'SLO',
            'SLOVAKIA': 'SVK', 'ESLOVAQUIA': 'SVK',
            'LITHUANIA': 'LTU', 'LITUANIA': 'LTU',
            'LATVIA': 'LAT', 'LETONIA': 'LAT',
            'ESTONIA': 'EST',
            'ANDORRA': 'AND',
            'LUXEMBOURG': 'LUX', 'LUXEMBURGO': 'LUX',
            'ICELAND': 'ISL', 'ISLANDIA': 'ISL',
            'CYPRUS': 'CYP', 'CHIPRE': 'CYP',
            'MALTA': 'MLT',
            'MONACO': 'MON', 'MÓNACO': 'MON',
            'LIECHTENSTEIN': 'LIE',
            'BOLIVIA': 'BOL',
            'PARAGUAY': 'PAR',
            'URUGUAY': 'URU',
            'COSTA RICA': 'CRC',
            'PANAMA': 'PAN', 'PANAMÁ': 'PAN',
            'GUATEMALA': 'GUA',
            'HONDURAS': 'HON',
            'EL SALVADOR': 'ESA',
            'NICARAGUA': 'NCA',
            'PUERTO RICO': 'PUR',
        }
        
        # Check if already a 3-letter code
        if len(country_str) == 3:
            return country_str
        
        # Look up in mapping
        if country_str in ioc_mapping:
            return ioc_mapping[country_str]
        
        # If not found, return first 3 chars as fallback
        return country_str[:3] if len(country_str) >= 3 else country_str
    
    export_df['country'] = valid_df['País'].apply(country_to_ioc_code)
    
    return export_df.to_csv(index=False, encoding='utf-8-sig', sep=';')

def generate_team_players_csv(df):
    valid_df = df[df['Datos_Validos']].copy()
    
    export_df = pd.DataFrame()
    export_df['Team'] = valid_df['Pruebas'].astype(str).str.strip()
    export_df['Lidnummer'] = valid_df['Nº.ID'].astype(str).str.replace(r'\.0$', '', regex=True)
    export_df['Positie'] = 0
    return export_df.to_csv(index=False, encoding='utf-8-sig', sep=';')

def generate_tournament_planner_xlsx(df):
    """
    Generates an Excel file (.xlsx) with fields matching Tournament Planner import format.
    Fields: Member ID, Name, First name, Middle name, Gender, Club, Club-ID, Country,
            Date of birth, Mobile, Email, Team ID, Team, Position, Level Singles, Level Doubles
    """
    import io
    
    # Filter valid data or use all if no filter column
    if 'Datos_Validos' in df.columns:
        valid_df = df[df['Datos_Validos']].copy()
    else:
        valid_df = df.copy()
    
    # Load Club-ID mappings (same as CSV exports)
    club_ids_mapping = load_club_ids_mapping()
    team_overrides = load_team_clubid_overrides()
    
    def get_final_clubid(team_name):
        """Get ClubID: first check manual override, then auto-detect."""
        if not team_name or pd.isna(team_name):
            return ""
        team_str = str(team_name).strip()
        
        # 1. Check manual override first (highest priority)
        if team_str in team_overrides:
            return team_overrides[team_str]
        
        # 2. Case-insensitive override check
        for override_team, override_id in team_overrides.items():
            if override_team.upper() == team_str.upper():
                return override_id
        
        # 3. Fall back to auto-detection
        return get_clubid_for_team(team_str, club_ids_mapping)
    
    def format_date_for_tp(date_val):
        """Format date as DD/MM/YYYY for Tournament Planner."""
        if pd.isna(date_val):
            return ""
        date_str = str(date_val).strip()
        if not date_str or date_str.lower() in ['nan', 'none', 'nat']:
            return ""
        
        # Handle ISO datetime format (e.g., 1982-04-22T00:00:00.000)
        if 'T' in date_str:
            date_str = date_str.split('T')[0]
        
        # Remove time component if present (space separator)
        if ' ' in date_str:
            date_str = date_str.split(' ')[0]
        
        # Try parsing different formats
        for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y']:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime('%d/%m/%Y')
            except:
                continue
        return date_str
    
    def format_gender_tp(gender_val):
        """Format gender as M/F for Tournament Planner."""
        if pd.isna(gender_val):
            return ""
        g = str(gender_val).upper().strip()
        if g in ['M', 'MASCULINO', 'MALE', 'H', 'HOMBRE']:
            return "M"
        elif g in ['F', 'FEMENINO', 'FEMALE', 'MUJER']:
            return "F"
        return g[:1] if g else ""
    
    def get_club_name(row):
        """Get club name - use origin club for non-loaned, current team for loaned."""
        club = str(row.get('Club', '')).strip()
        if pd.isna(club) or club.lower() == 'nan':
            club = str(row.get('Pruebas', '')).strip()
        return club
    
    def clean_val(val):
        """Clean value for export."""
        if pd.isna(val):
            return ""
        s = str(val).strip()
        return "" if s.lower() in ['nan', 'none'] else s
    
    # Load Teams/Clubs mapping from Excel file
    teams_mapping = {}
    teams_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Teams y clubs Liga Nacional de Clubes edición 2025-2026.XLSX')
    if os.path.exists(teams_file):
        try:
            teams_df = pd.read_excel(teams_file)
            for _, row in teams_df.iterrows():
                team_name = str(row.get('Team', '')).strip()
                if team_name and team_name.lower() not in ['nan', 'none', '']:
                    teams_mapping[team_name.upper()] = {
                        'team_id': str(row.get('Team-ID', '')).strip(),
                        'club_id': str(row.get('Club-ID', '')).strip(),
                        'club_name': str(row.get('Club', '')).strip()
                    }
        except Exception as e:
            print(f"Warning: Could not load teams mapping: {e}")
    
    def get_team_info(team_name, field):
        """Get Team-ID, Club-ID or Club name from mapping."""
        if not team_name or pd.isna(team_name):
            return ""
        team_str = str(team_name).strip().upper()
        
        # Direct match
        if team_str in teams_mapping:
            return teams_mapping[team_str].get(field, "")
        
        # Partial match (for slight variations)
        for mapped_team, info in teams_mapping.items():
            if team_str in mapped_team or mapped_team in team_str:
                return info.get(field, "")
        
        # Use similarity matching
        for mapped_team, info in teams_mapping.items():
            if calculate_similarity(team_str, mapped_team) >= 0.85:
                return info.get(field, "")
        
        return ""
    
    # Build export dataframe with TP fields
    export_df = pd.DataFrame()
    
    # Member ID
    export_df['Member ID'] = valid_df['Nº.ID'].astype(str).str.replace(r'\.0$', '', regex=True)
    
    # Name (Last Name - Apellido 1) - Add (C) marker for loaned players
    def build_name_with_cedido(row):
        name = clean_val(row.get('Nombre', ''))
        if row.get('Es_Cedido', False) == True:
            name = f"{name} (C)"
        return name
    
    export_df['Name'] = valid_df.apply(build_name_with_cedido, axis=1)
    
    # First name (Nombre.1)
    export_df['First name'] = valid_df['Nombre.1'].apply(clean_val)
    
    # Middle name (2ºNombre / Apellido 2)
    if '2ºNombre' in valid_df.columns:
        export_df['Middle name'] = valid_df['2ºNombre'].apply(clean_val)
    else:
        export_df['Middle name'] = ""
    
    # Gender
    export_df['Gender'] = valid_df['Género'].apply(format_gender_tp)
    
    # Club (from mapping if available, else from data)
    def get_club_for_export(row):
        team = str(row.get('Pruebas', '')).strip()
        mapped_club = get_team_info(team, 'club_name')
        if mapped_club:
            return mapped_club
        # Fallback
        club = str(row.get('Club', '')).strip()
        if pd.isna(club) or club.lower() == 'nan':
            club = team
        return club
    
    export_df['Club'] = valid_df.apply(get_club_for_export, axis=1)
    
    # Club-ID (from mapping)
    export_df['Club-ID'] = valid_df['Pruebas'].apply(lambda x: get_team_info(x, 'club_id') or get_final_clubid(x))
    
    # Country
    export_df['Country'] = valid_df['País'].apply(clean_val)
    
    # Date of birth
    export_df['Date of birth'] = valid_df['F.Nac'].apply(format_date_for_tp)
    
    # Mobile (if available)
    if 'Telefono' in valid_df.columns:
        export_df['Mobile'] = valid_df['Telefono'].apply(clean_val)
    elif 'Móvil' in valid_df.columns:
        export_df['Mobile'] = valid_df['Móvil'].apply(clean_val)
    else:
        export_df['Mobile'] = ""
    
    # Email (if available)
    if 'Email' in valid_df.columns:
        export_df['Email'] = valid_df['Email'].apply(clean_val)
    elif 'Correo' in valid_df.columns:
        export_df['Email'] = valid_df['Correo'].apply(clean_val)
    else:
        export_df['Email'] = ""
    
    # Team ID (from mapping)
    export_df['Team ID'] = valid_df['Pruebas'].apply(lambda x: get_team_info(x, 'team_id'))
    
    # Team (Current team)
    export_df['Team'] = valid_df['Pruebas'].apply(clean_val)
    
    # Position
    export_df['Position'] = ""
    
    # Level Singles / Level Doubles (if available)
    if 'Nivel_Singles' in valid_df.columns:
        export_df['Level Singles'] = valid_df['Nivel_Singles'].apply(clean_val)
    else:
        export_df['Level Singles'] = ""
    
    if 'Nivel_Dobles' in valid_df.columns:
        export_df['Level Doubles'] = valid_df['Nivel_Dobles'].apply(clean_val)
    else:
        export_df['Level Doubles'] = ""
    
    # Write to Excel bytes
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        export_df.to_excel(writer, index=False, sheet_name='Players')
    
    return output.getvalue()

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
        new_team_raw = str(row['Pruebas']).strip()
        
        old_club = str(df_current.at[idx, 'Club']).strip()
        new_club_raw = str(row['Club']).strip()
        
        changes = []
        
        # --- LÓGICA DE TRANSFERENCIA AUTOMÁTICA (Equipo) ---
        final_team = new_team_raw
        transfer_note = ""
        
        # Si el nuevo dato tiene coma (ej: "Astures, RSL Tenerife")
        if ',' in new_team_raw:
            parts = [p.strip() for p in new_team_raw.split(',') if p.strip()]
            # Normalizar para comparar
            old_norm = normalize_name(old_team)
            
            match_found = False
            candidate_team = None
            
            for p in parts:
                p_norm = normalize_name(p)
                # Usar calculate_similarity para ser robustos o igualdad simple de normalizados
                # Asumimos que normalize_name quita "C.B.", "Club", etc.
                if p_norm == old_norm or calculate_similarity(p, old_team) > 0.9:
                    match_found = True
                else:
                    candidate_team = p # El que NO coincide es el nuevo destino
            
            # Si encontramos el equipo antiguo en la lista Y hay un candidato diferente
            if match_found and candidate_team:
                final_team = candidate_team
                transfer_note = " (Transferencia Detectada)"
        
        # Aplicar cambio de equipo
        if final_team.lower() == 'nan' or not final_team:
            pass 
        elif old_team != final_team:
            # Caso especial: Si antes era "Astures" y ahora es "RSL Tenerife" (por la lógica de arriba)
            df_current.at[idx, 'Pruebas'] = final_team
            changes.append(f"Equipo: '{old_team}' ➡️ '{final_team}'{transfer_note}")

        # --- LÓGICA CLUB (Similar o directa) ---
        # A veces cambia el Club pero el Equipo (Pruebas) se mantiene igual o viceversa.
        # Por simplicidad, aplicamos directo, pero podríamos usar la misma lógica si 'Club' trae doble nombre.
        if new_club_raw.lower() == 'nan' or not new_club_raw:
            pass
        elif old_club != new_club_raw:
            df_current.at[idx, 'Club'] = new_club_raw
            changes.append(f"Club: '{old_club}' ➡️ '{new_club_raw}'")
            
        if changes:
            updates_count += 1
            # Añadir nota interna
            current_note = str(df_current.at[idx, 'Notas_Revision'])
            change_note = f" [MOD: {', '.join(changes)}]"
            
            # Evitar duplicar notas
            if change_note not in current_note:
                 # Limpiar 'nan' si existía
                 if current_note.lower() == 'nan': current_note = ""
                 df_current.at[idx, 'Notas_Revision'] = (current_note + change_note).strip()
                
            logs.append(f"✏️ **ACTUALIZADO {transfer_note}:** {row['Nombre']} ({pid}): {', '.join(changes)}")

    # 3. Concatenar
    if not df_new_players.empty:
        df_merged = pd.concat([df_current, df_new_players], ignore_index=True)
    else:
        df_merged = df_current
        
    summary = f"✅ **RESUMEN:** {len(df_new_players)} añadidos, {updates_count} actualizados."
    logs.insert(0, summary)
    
    return df_merged, logs
